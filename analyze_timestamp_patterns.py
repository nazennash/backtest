"""
Analyze timestamp patterns to design alignment solution
"""
import os
import sys
import django
import pandas as pd
from datetime import datetime, timedelta

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'polygon_trader.settings')
django.setup()

from trader.polygon_api import PolygonAPI

print("=== Analyzing Timestamp Patterns for Alignment Solution ===\n")

polygon_api = PolygonAPI()
start_date = '2025-08-01'
end_date = '2025-08-22'

# Test multiple tickers and frequencies
tickers = ['YMAX', 'QQQ', 'SPY']
frequencies = {
    'hour': '1 Hour',
    '4hour': '4 Hours', 
    '30min': '30 Minutes',
    '15min': '15 Minutes'
}

patterns = {}

for freq_code, freq_name in frequencies.items():
    print(f"\n{freq_name} Frequency Analysis:")
    print("=" * 50)
    
    freq_patterns = {}
    
    for ticker in tickers + ['VIX', 'VVIX']:
        try:
            df = polygon_api.get_ohlc_data(ticker, start_date, end_date, freq_code)
            if not df.empty:
                timestamps = pd.to_datetime(df['timestamp'])
                
                # Get unique hours
                hours = sorted(set(timestamps.dt.hour))
                
                # Get pattern for first day
                first_day = timestamps.dt.date.min()
                first_day_times = timestamps[timestamps.dt.date == first_day]
                pattern = [t.strftime('%H:%M') for t in first_day_times[:8]]
                
                freq_patterns[ticker] = {
                    'hours': hours,
                    'pattern': pattern,
                    'count': len(timestamps)
                }
                
                print(f"  {ticker:5s}: Hours={hours[:8]}{'...' if len(hours) > 8 else ''}")
        except Exception as e:
            print(f"  {ticker:5s}: Error - {e}")
    
    patterns[freq_code] = freq_patterns
    
    # Analyze alignment
    if len(freq_patterns) > 1:
        all_hours = set()
        for data in freq_patterns.values():
            all_hours.update(data['hours'])
        
        print(f"\n  Alignment Analysis:")
        print(f"    All unique hours across assets: {sorted(all_hours)}")
        
        # Check for common pattern
        if 'hour' in freq_code or '4hour' in freq_code:
            # For hourly data, we can align to standard market hours
            print(f"    Suggested alignment: Round to nearest standard hour")
            print(f"    - For 1 hour: Use market hours 9, 10, 11, 12, 13, 14, 15, 16, etc.")
            print(f"    - For 4 hour: Use 8:00, 12:00, 16:00, 20:00 (or 9:00, 13:00, 17:00, 21:00)")
        elif 'min' in freq_code:
            print(f"    Suggested alignment: Round to nearest {freq_name} boundary")

print("\n\n=== Proposed Alignment Strategy ===")
print("1. For 4-hour frequency:")
print("   - Normalize all timestamps to nearest 4-hour boundary from market open")
print("   - Options:")
print("     a) Use 00:00, 04:00, 08:00, 12:00, 16:00, 20:00 (UTC aligned)")
print("     b) Use 09:00, 13:00, 17:00, 21:00 (market hours aligned)")
print("   - Round timestamps: 05:00->04:00, 09:00->08:00, etc.")
print("")
print("2. For 1-hour frequency:")
print("   - Already mostly aligned, just need to handle edge cases")
print("   - Round to nearest hour if needed")
print("")
print("3. For minute frequencies:")
print("   - Round to nearest period boundary")
print("   - 30min: 00, 30")
print("   - 15min: 00, 15, 30, 45")
print("   - 5min: 00, 05, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55")
print("")
print("4. Implementation approach:")
print("   - Create normalize_to_common_timestamps() function")
print("   - Apply BEFORE the merge operation")
print("   - Use pandas round/floor methods with appropriate frequency")