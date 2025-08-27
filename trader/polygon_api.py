import requests
import pandas as pd
from django.conf import settings
from typing import Dict, List
import logging

logger = logging.getLogger(__name__)


class PolygonAPI:
    """Polygon API client for fetching market data"""
    
    def __init__(self):
        self.api_key = settings.POLYGON_API_KEY
        self.base_url = "https://api.polygon.io"
        
        # Common indices that users might search for
        self.common_indices = {
            'VIX': 'I:VIX',
            'VVIX': 'I:VVIX', 
            'SPX': 'I:SPX',
            'DJI': 'I:DJI',
            'NDX': 'I:NDX',
            'RUT': 'I:RUT',
            'VXN': 'I:VXN',
            'RVX': 'I:RVX',
            'SKEW': 'I:SKEW',
            'VIX9D': 'I:VIX9D',
            'VXD': 'I:VXD',
            'VXEEM': 'I:VXEEM',
            'VXFXI': 'I:VXFXI',
            'VXGDX': 'I:VXGDX'
        }
    
    def is_index_ticker(self, ticker: str) -> bool:
        """Check if a ticker is an index"""
        ticker_upper = ticker.upper()
        
        # If already has I: prefix
        if ticker_upper.startswith('I:'):
            return True
            
        # Check if it's a known index
        return ticker_upper in self.common_indices
    
    def format_ticker_for_api(self, ticker: str) -> str:
        """Format ticker for API calls (add I: prefix for indices)"""
        ticker_upper = ticker.upper()
        
        # If already formatted, return as is
        if ticker_upper.startswith('I:'):
            return ticker_upper
            
        # If it's a known index, add the I: prefix
        if ticker_upper in self.common_indices:
            return self.common_indices[ticker_upper]
            
        # For regular stocks, return as is
        return ticker_upper
    
    def get_ticker_type(self, ticker: str) -> str:
        """Get the type of ticker (stock or index)"""
        return 'index' if self.is_index_ticker(ticker) else 'stock'
        
    def _make_request(self, endpoint: str, params: Dict) -> Dict:
        """Make a request to the Polygon API"""
        params['apikey'] = self.api_key
        
        try:
            response = requests.get(f"{self.base_url}{endpoint}", params=params, timeout=30)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Error making request to Polygon API: {e}")
            raise
    
    def get_aggregates(self, ticker: str, timespan: str, multiplier: int, 
                      from_date: str, to_date: str) -> List[Dict]:
        """Get aggregate bars for a ticker (supports both stocks and indices)"""
        # Format the ticker properly for the API
        formatted_ticker = self.format_ticker_for_api(ticker)
        endpoint = f"/v2/aggs/ticker/{formatted_ticker}/range/{multiplier}/{timespan}/{from_date}/{to_date}"
        
        params = {
            'adjusted': 'true',
            'sort': 'asc',
            'limit': 50000
        }
        
        # For indices, we might need to remove the 'adjusted' parameter
        if self.is_index_ticker(ticker):
            params.pop('adjusted', None)
        
        logger.info(f"Fetching data for {formatted_ticker} from {from_date} to {to_date}")
        data = self._make_request(endpoint, params)
        
        if data.get('status') == 'OK' and 'results' in data:
            logger.info(f"Got {len(data['results'])} records for {formatted_ticker}")
            return data['results']
        else:
            logger.warning(f"No data returned for {formatted_ticker}: {data.get('message', 'Unknown error')}")
            return []
    
    def convert_frequency_to_polygon_params(self, frequency: str) -> tuple:
        """Convert our frequency format to Polygon API parameters"""
        frequency_mapping = {
            '1': (1, 'second'),
            '5': (5, 'second'),
            '10': (10, 'second'),
            '15': (15, 'second'),
            '30': (30, 'second'),
            'minute': (1, 'minute'),
            '5minute': (5, 'minute'),
            '15minute': (15, 'minute'),
            '30minute': (30, 'minute'),
            'hour': (1, 'hour'),
            '4hour': (4, 'hour'),
            'day': (1, 'day'),
            'week': (1, 'week'),
            'month': (1, 'month'),
        }
        
        return frequency_mapping.get(frequency, (1, 'day'))
    
    def get_market_data(self, ticker: str, start_date: str, end_date: str, frequency: str) -> pd.DataFrame:
        """Get market data and return as DataFrame (supports both stocks and indices)"""
        multiplier, timespan = self.convert_frequency_to_polygon_params(frequency)
        
        try:
            results = self.get_aggregates(ticker, timespan, multiplier, start_date, end_date)
            
            if not results:
                return pd.DataFrame()
            
            # Convert to DataFrame
            df = pd.DataFrame(results)
            
            # Rename columns to match our model
            df.rename(columns={
                'o': 'open',
                'h': 'high',
                'l': 'low',
                'c': 'close',
                'v': 'volume',
                't': 'timestamp'
            }, inplace=True)
            
            # Convert timestamp from milliseconds to datetime
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            
            # Add ticker and frequency columns (use original ticker for display)
            display_ticker = ticker.upper()
            df['ticker'] = display_ticker
            df['frequency'] = frequency
            
            # For indices, volume might be 0 or missing, so we'll handle that
            if 'volume' not in df.columns:
                df['volume'] = 0
            
            return df[['ticker', 'timestamp', 'open', 'high', 'low', 'close', 'volume', 'frequency']]
            
        except Exception as e:
            logger.error(f"Error fetching market data: {e}")
            return pd.DataFrame()
    
    def get_ticker_suggestions(self, query: str, limit: int = 20) -> List[Dict]:
        """Get ticker suggestions for autocomplete (includes both stocks and indices)"""
        suggestions = []
        query_upper = query.upper()
        
        # First, check for matching indices
        matching_indices = []
        for index_symbol, _ in self.common_indices.items():
            if query_upper in index_symbol:
                matching_indices.append({
                    'ticker': index_symbol,
                    'name': f'{index_symbol} Index',
                    'market': 'indices'
                })
        
        # Sort indices by relevance (exact matches first)
        matching_indices.sort(key=lambda x: (
            0 if x['ticker'].startswith(query_upper) else 1,
            len(x['ticker'])
        ))
        
        # Add indices to suggestions
        suggestions.extend(matching_indices[:5])  # Limit to top 5 indices
        
        # Then search for stocks if we need more suggestions
        remaining_limit = limit - len(suggestions)
        if remaining_limit > 0:
            try:
                endpoint = "/v3/reference/tickers"
                params = {
                    'search': query,
                    'active': 'true',
                    'sort': 'ticker',
                    'order': 'asc',
                    'limit': remaining_limit,
                    'market': 'stocks'
                }
                
                data = self._make_request(endpoint, params)
                
                if data.get('status') == 'OK' and 'results' in data:
                    for result in data['results']:
                        suggestions.append({
                            'ticker': result.get('ticker', ''),
                            'name': result.get('name', ''),
                            'market': result.get('market', 'stocks')
                        })
                        
            except Exception as e:
                logger.error(f"Error fetching stock suggestions: {e}")
        
        return suggestions[:limit]
    
    def get_dividends(self, ticker: str, start_date: str, end_date: str) -> pd.DataFrame:
        """Get dividend data for a ticker"""
        try:
            # Dividends are only for stocks, not indices
            if self.is_index_ticker(ticker):
                return pd.DataFrame(columns=['timestamp', 'dividends'])
            
            endpoint = f"/v3/reference/dividends"
            params = {
                'ticker': ticker.upper(),
                'ex_dividend_date.gte': start_date,
                'ex_dividend_date.lte': end_date,
                'order': 'asc',
                'limit': 1000
            }
            
            data = self._make_request(endpoint, params)
            
            if data.get('status') == 'OK' and 'results' in data:
                df = pd.DataFrame(data['results'])
                if not df.empty:
                    # Convert ex_dividend_date to timestamp
                    df['timestamp'] = pd.to_datetime(df['ex_dividend_date'])
                    df['dividends'] = df['cash_amount']
                    return df[['timestamp', 'dividends']]
            
            return pd.DataFrame(columns=['timestamp', 'dividends'])
            
        except Exception as e:
            logger.error(f"Error fetching dividend data: {e}")
            return pd.DataFrame(columns=['timestamp', 'dividends'])
    
    def get_ohlc_data(self, ticker: str, start_date: str, end_date: str, frequency: str) -> pd.DataFrame:
        """Get only OHLC data (no volume) for a ticker"""
        df = self.get_market_data(ticker, start_date, end_date, frequency)
        if not df.empty:
            # Return OHLC columns AND frequency (needed for merge)
            return df[['timestamp', 'open', 'high', 'low', 'close', 'frequency']]
        return pd.DataFrame(columns=['timestamp', 'open', 'high', 'low', 'close', 'frequency'])