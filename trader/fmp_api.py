import requests
import pandas as pd
from django.conf import settings
from typing import Dict, List
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


class FMPAPI:
    """Financial Modeling Prep API client for fetching daily market data"""
    
    def __init__(self):
        self.api_key = getattr(settings, 'FMP_API_KEY', '')
        self.base_url = "https://financialmodelingprep.com/api/v3"
        
        if not self.api_key:
            logger.warning("FMP API key not found in settings. Please add FMP_API_KEY to your settings.")
    
    def _make_request(self, endpoint: str, params: Dict) -> Dict:
        """Make a request to the FMP API"""
        params['apikey'] = self.api_key
        
        try:
            response = requests.get(f"{self.base_url}{endpoint}", params=params, timeout=30)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Error making request to FMP API: {e}")
            raise
    
    def get_historical_price(self, ticker: str, start_date: str, end_date: str) -> pd.DataFrame:
        """Get historical daily price data from FMP"""
        endpoint = f"/historical-price-full/{ticker.upper()}"
        
        params = {
            'from': start_date,
            'to': end_date
        }
        
        try:
            logger.info(f"Fetching FMP data for {ticker} from {start_date} to {end_date}")
            data = self._make_request(endpoint, params)
            
            if not isinstance(data, dict) or 'historical' not in data:
                logger.warning(f"No data returned from FMP for {ticker}")
                return pd.DataFrame()
            
            historical_data = data.get('historical', [])
            if not historical_data:
                return pd.DataFrame()
            
            # Convert to DataFrame
            df = pd.DataFrame(historical_data)
            
            # Rename columns to match our format
            df = df.rename(columns={
                'date': 'timestamp',
                'volume': 'volume'
            })
            
            # Convert timestamp to datetime
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            
            # Add ticker and frequency columns
            df['ticker'] = ticker.upper()
            df['frequency'] = 'day'
            
            # Sort by timestamp ascending (FMP returns descending)
            df = df.sort_values('timestamp')
            
            # Select and reorder columns
            columns = ['ticker', 'timestamp', 'open', 'high', 'low', 'close', 'volume', 'frequency']
            return df[columns]
            
        except Exception as e:
            logger.error(f"Error fetching FMP market data: {e}")
            return pd.DataFrame()
    
    def get_ohlc_data(self, ticker: str, start_date: str, end_date: str, frequency: str = 'day') -> pd.DataFrame:
        """Get only OHLC data (matching PolygonAPI interface)"""
        if frequency != 'day':
            logger.warning(f"FMP API only supports daily frequency, but {frequency} was requested")
            return pd.DataFrame()
        
        df = self.get_historical_price(ticker, start_date, end_date)
        if not df.empty:
            # Return OHLC columns AND frequency (needed for merge)
            return df[['timestamp', 'open', 'high', 'low', 'close', 'frequency']]
        return pd.DataFrame(columns=['timestamp', 'open', 'high', 'low', 'close', 'frequency'])
    
    def get_dividends(self, ticker: str, start_date: str, end_date: str) -> pd.DataFrame:
        """Get dividend data from FMP"""
        endpoint = f"/historical-price-full/stock_dividend/{ticker.upper()}"
        
        params = {
            'from': start_date,
            'to': end_date
        }
        
        try:
            data = self._make_request(endpoint, params)
            
            if not isinstance(data, dict) or 'historical' not in data:
                return pd.DataFrame(columns=['timestamp', 'dividends'])
            
            historical_data = data.get('historical', [])
            if not historical_data:
                return pd.DataFrame(columns=['timestamp', 'dividends'])
            
            df = pd.DataFrame(historical_data)
            
            # Rename columns
            df['timestamp'] = pd.to_datetime(df['date'])
            df['dividends'] = df['dividend']
            
            # Sort by timestamp ascending
            df = df.sort_values('timestamp')
            
            return df[['timestamp', 'dividends']]
            
        except Exception as e:
            logger.error(f"Error fetching FMP dividend data: {e}")
            return pd.DataFrame(columns=['timestamp', 'dividends'])
