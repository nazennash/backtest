"""
SQLite database storage for merged market data
"""
import sqlite3
import pandas as pd
import os
import logging
from datetime import datetime
from django.conf import settings

logger = logging.getLogger(__name__)


class MarketDataDB:
    """Handle SQLite storage for merged asset-VIX-VVIX data"""
    
    def __init__(self):
        # Create a data directory if it doesn't exist
        self.db_dir = os.path.join(settings.BASE_DIR, 'market_data_db')
        os.makedirs(self.db_dir, exist_ok=True)
    
    def get_db_filename(self, ticker, frequency):
        """Generate database filename based on ticker and frequency"""
        # Normalize frequency names
        freq_map = {
            'day': 'Daily',
            'hour': 'Hourly',
            '1hour': 'Hourly',
            '60min': 'Hourly',
            'minute': 'Minute',
            '1min': 'Minute',
            '5min': '5Min',
            '15min': '15Min',
            '30min': '30Min',
            'week': 'Weekly',
            'month': 'Monthly'
        }
        
        freq_name = freq_map.get(frequency, frequency.title())
        return f"{ticker}_VIX_VVIX_{freq_name}.db"
    
    def get_db_path(self, ticker, frequency):
        """Get full path to database file"""
        filename = self.get_db_filename(ticker, frequency)
        return os.path.join(self.db_dir, filename)
    
    def save_data(self, df, ticker, frequency, start_date, end_date):
        """Save merged dataframe to SQLite database"""
        try:
            db_path = self.get_db_path(ticker, frequency)
            logger.info(f"Saving data to SQLite: {db_path}")
            
            # Connect to database
            conn = sqlite3.connect(db_path)
            
            # Store the main data
            df.to_sql('market_data', conn, if_exists='replace', index=False)
            
            # Store metadata
            metadata = pd.DataFrame([{
                'ticker': ticker,
                'frequency': frequency,
                'start_date': start_date,
                'end_date': end_date,
                'rows': len(df),
                'columns': len(df.columns),
                'last_updated': datetime.now().isoformat()
            }])
            metadata.to_sql('metadata', conn, if_exists='replace', index=False)
            
            conn.close()
            logger.info(f"Successfully saved {len(df)} rows to {db_path}")
            return True
            
        except Exception as e:
            logger.error(f"Error saving to SQLite: {e}", exc_info=True)
            return False
    
    def load_data(self, ticker, frequency, start_date=None, end_date=None):
        """Load data from SQLite database"""
        try:
            db_path = self.get_db_path(ticker, frequency)
            
            if not os.path.exists(db_path):
                logger.warning(f"Database not found: {db_path}")
                return None
            
            logger.info(f"Loading data from SQLite: {db_path}")
            
            # Connect to database
            conn = sqlite3.connect(db_path)
            
            # Check if data exists and is recent
            try:
                metadata = pd.read_sql_query("SELECT * FROM metadata", conn)
                if not metadata.empty:
                    last_updated = pd.to_datetime(metadata['last_updated'].iloc[0])
                    data_age = (datetime.now() - last_updated).total_seconds() / 3600  # hours
                    logger.info(f"Data age: {data_age:.1f} hours")
            except:
                logger.warning("No metadata found in database")
            
            # Load the data
            df = pd.read_sql_query("SELECT * FROM market_data", conn)
            conn.close()
            
            # Convert timestamp column to datetime
            if 'timestamp' in df.columns:
                df['timestamp'] = pd.to_datetime(df['timestamp'])
            
            # Filter by date range if provided
            if start_date and end_date and 'timestamp' in df.columns:
                start_dt = pd.to_datetime(start_date)
                end_dt = pd.to_datetime(end_date)
                original_len = len(df)
                df = df[(df['timestamp'] >= start_dt) & (df['timestamp'] <= end_dt)]
                logger.info(f"Filtered data from {original_len} to {len(df)} rows based on date range")
            
            logger.info(f"Loaded {len(df)} rows from {db_path}")
            return df
            
        except Exception as e:
            logger.error(f"Error loading from SQLite: {e}", exc_info=True)
            return None
    
    def check_data_exists(self, ticker, frequency):
        """Check if database exists for given ticker and frequency"""
        db_path = self.get_db_path(ticker, frequency)
        return os.path.exists(db_path)
    
    def get_metadata(self, ticker, frequency):
        """Get metadata about stored data"""
        try:
            db_path = self.get_db_path(ticker, frequency)
            
            if not os.path.exists(db_path):
                return None
            
            conn = sqlite3.connect(db_path)
            metadata = pd.read_sql_query("SELECT * FROM metadata", conn)
            conn.close()
            
            if not metadata.empty:
                return metadata.iloc[0].to_dict()
            return None
            
        except Exception as e:
            logger.error(f"Error reading metadata: {e}")
            return None
