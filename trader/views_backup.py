from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.core.cache import cache
import json
import plotly.graph_objects as go
from plotly.io import to_html
import pandas as pd
import logging
import requests
from django.conf import settings
import hashlib



from .forms import ChartDataForm
from .polygon_api import PolygonAPI
from .fmp_api import FMPAPI
from .models import MarketData, TickerSuggestion
from datetime import datetime

logger = logging.getLogger(__name__)


def merge_ticker_data(df_ticker, df_vix, df_vvix, df_dividends, ticker_name):
    """Merge ticker, VIX, VVIX data and dividends using inner join"""
    try:
        # Log initial data shapes
        logger.info(f"Initial data shapes - Ticker: {df_ticker.shape}, VIX: {df_vix.shape}, VVIX: {df_vvix.shape}, Dividends: {df_dividends.shape}")
        
        # Function to normalize timestamps based on frequency
        def normalize_timestamp(df, frequency):
            # Convert to datetime first
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            
            if frequency in ['day', 'week', 'month']:
                # For daily and longer frequencies, normalize to date only (midnight UTC)
                df['timestamp'] = df['timestamp'].dt.normalize()
            elif frequency in ['hour', '1hour', '60min']:
                # For hourly data, round to the nearest hour
                df['timestamp'] = df['timestamp'].dt.floor('h')
            elif frequency in ['minute', '1min', '5min', '15min', '30min']:
                # For minute data, round to the nearest minute (remove seconds/milliseconds)
                df['timestamp'] = df['timestamp'].dt.floor('min')
            
            return df
        
        # Get frequency from the first dataframe that has it
        frequency = None
        if not df_ticker.empty and 'frequency' in df_ticker.columns:
            frequency = df_ticker['frequency'].iloc[0]
            logger.info(f"Detected frequency: {frequency}")
        
        # Normalize timestamps for all dataframes if needed
        if frequency:
            if not df_ticker.empty:
                df_ticker = normalize_timestamp(df_ticker, frequency)
                logger.info(f"Ticker timestamps after normalization: {df_ticker['timestamp'].head()}")
            if not df_vix.empty:
                df_vix = normalize_timestamp(df_vix, frequency)
                logger.info(f"VIX timestamps after normalization: {df_vix['timestamp'].head()}")
            if not df_vvix.empty:
                df_vvix = normalize_timestamp(df_vvix, frequency)
                logger.info(f"VVIX timestamps after normalization: {df_vvix['timestamp'].head()}")
            if not df_dividends.empty:
                df_dividends = normalize_timestamp(df_dividends, frequency)
        
        # Rename columns for main ticker
        if not df_ticker.empty:
            df_ticker = df_ticker.rename(columns={
                'open': f'{ticker_name}_Open',
                'high': f'{ticker_name}_High',
                'low': f'{ticker_name}_Low',
                'close': f'{ticker_name}_Close'
            })
            # Drop frequency column before setting index (we already used it for normalization)
            if 'frequency' in df_ticker.columns:
                df_ticker = df_ticker.drop('frequency', axis=1)
            df_ticker = df_ticker.set_index('timestamp')
            logger.info(f"Ticker data after rename: {df_ticker.shape}, columns: {df_ticker.columns.tolist()}")
        
        # Rename columns for VIX
        if not df_vix.empty:
            df_vix = df_vix.rename(columns={
                'open': 'VIX_Open',
                'high': 'VIX_High',
                'low': 'VIX_Low',
                'close': 'VIX_Close'
            })
            # Drop frequency column before setting index
            if 'frequency' in df_vix.columns:
                df_vix = df_vix.drop('frequency', axis=1)
            df_vix = df_vix.set_index('timestamp')
            logger.info(f"VIX data after rename: {df_vix.shape}, columns: {df_vix.columns.tolist()}")
        
        # Rename columns for VVIX
        if not df_vvix.empty:
            df_vvix = df_vvix.rename(columns={
                'open': 'VVIX_Open',
                'high': 'VVIX_High',
                'low': 'VVIX_Low',
                'close': 'VVIX_Close'
            })
            # Drop frequency column before setting index
            if 'frequency' in df_vvix.columns:
                df_vvix = df_vvix.drop('frequency', axis=1)
            df_vvix = df_vvix.set_index('timestamp')
            logger.info(f"VVIX data after rename: {df_vvix.shape}, columns: {df_vvix.columns.tolist()}")
        
        # Process dividends
        if not df_dividends.empty:
            df_dividends = df_dividends.rename(columns={
                'dividends': f'{ticker_name}_Dividends'
            })
            df_dividends = df_dividends.set_index('timestamp')
            logger.info(f"Dividends data: {df_dividends.shape}")
        
        # Start with ticker data
        merged_df = df_ticker
        logger.info(f"Starting merge with ticker data: {merged_df.shape}")
        
        # Inner join with VIX if available
        if not df_vix.empty:
            # Debug: Check overlapping dates
            ticker_dates = set(merged_df.index)
            vix_dates = set(df_vix.index)
            common_dates = ticker_dates.intersection(vix_dates)
            logger.info(f"Ticker has {len(ticker_dates)} dates, VIX has {len(vix_dates)} dates, common dates: {len(common_dates)}")
            
            if len(common_dates) == 0:
                # Log sample dates from each dataset to debug the issue
                logger.warning(f"No common dates found between {ticker_name} and VIX!")
                logger.warning(f"Sample {ticker_name} dates: {list(ticker_dates)[:5] if ticker_dates else 'None'}")
                logger.warning(f"Sample VIX dates: {list(vix_dates)[:5] if vix_dates else 'None'}")
                logger.warning(f"Date ranges - {ticker_name}: {min(ticker_dates) if ticker_dates else 'N/A'} to {max(ticker_dates) if ticker_dates else 'N/A'}")
                logger.warning(f"Date ranges - VIX: {min(vix_dates) if vix_dates else 'N/A'} to {max(vix_dates) if vix_dates else 'N/A'}")
                return pd.DataFrame()  # Return empty DataFrame if no common dates
            else:
                logger.info(f"Sample common dates: {list(common_dates)[:5]}")
            
            merged_df = merged_df.join(df_vix, how='inner')
            logger.info(f"After VIX join: {merged_df.shape}")
        
        # Inner join with VVIX if available
        if not df_vvix.empty:
            merged_df = merged_df.join(df_vvix, how='inner')
            logger.info(f"After VVIX join: {merged_df.shape}")
        
        # Left join with dividends (not inner, as dividends are sparse)
        if not df_dividends.empty:
            merged_df = merged_df.join(df_dividends, how='left')
            # Fill NaN dividends with 0
            merged_df[f'{ticker_name}_Dividends'] = merged_df[f'{ticker_name}_Dividends'].fillna(0)
        else:
            # Add empty dividend column
            merged_df[f'{ticker_name}_Dividends'] = 0
        
        # Reset index to make timestamp a column again
        merged_df = merged_df.reset_index()
        
        # Sort by timestamp
        merged_df = merged_df.sort_values('timestamp')
        
        logger.info(f"Final merged dataframe: {merged_df.shape}, columns: {merged_df.columns.tolist()}")
        if not merged_df.empty:
            logger.info(f"Date range: {merged_df['timestamp'].min()} to {merged_df['timestamp'].max()}")
        
        return merged_df
        
    except Exception as e:
        logger.error(f"Error merging data: {e}", exc_info=True)
        return pd.DataFrame()


def merge_ticker_data_with_daily_vix(df_ticker, df_vix_daily, df_vvix_daily, df_dividends, ticker_name):
    """Merge intraday ticker data with daily VIX/VVIX data by mapping dates"""
    try:
        logger.info(f"Merging intraday {ticker_name} data with daily VIX/VVIX data")
        
        # Prepare ticker data
        if not df_ticker.empty:
            df_ticker = df_ticker.copy()
            # Store the original timestamp before processing
            df_ticker['original_timestamp'] = df_ticker['timestamp']
            df_ticker['timestamp'] = pd.to_datetime(df_ticker['timestamp'])
            df_ticker['date_only'] = df_ticker['timestamp'].dt.date
            
            # Rename ticker columns
            df_ticker = df_ticker.rename(columns={
                'open': f'{ticker_name}_Open',
                'high': f'{ticker_name}_High',
                'low': f'{ticker_name}_Low',
                'close': f'{ticker_name}_Close'
            })
            
            # Drop frequency column if exists
            if 'frequency' in df_ticker.columns:
                df_ticker = df_ticker.drop('frequency', axis=1)
        
        # Prepare daily VIX data
        if not df_vix_daily.empty:
            df_vix_daily = df_vix_daily.copy()
            df_vix_daily['timestamp'] = pd.to_datetime(df_vix_daily['timestamp'])
            df_vix_daily['date_only'] = df_vix_daily['timestamp'].dt.date
            
            # Rename VIX columns
            df_vix_daily = df_vix_daily.rename(columns={
                'open': 'VIX_Open',
                'high': 'VIX_High',
                'low': 'VIX_Low',
                'close': 'VIX_Close'
            })
            
            # Drop frequency column and set date_only as index
            if 'frequency' in df_vix_daily.columns:
                df_vix_daily = df_vix_daily.drop('frequency', axis=1)
            df_vix_daily = df_vix_daily.drop('timestamp', axis=1).set_index('date_only')
        
        # Prepare daily VVIX data
        if not df_vvix_daily.empty:
            df_vvix_daily = df_vvix_daily.copy()
            df_vvix_daily['timestamp'] = pd.to_datetime(df_vvix_daily['timestamp'])
            df_vvix_daily['date_only'] = df_vvix_daily['timestamp'].dt.date
            
            # Rename VVIX columns
            df_vvix_daily = df_vvix_daily.rename(columns={
                'open': 'VVIX_Open',
                'high': 'VVIX_High',
                'low': 'VVIX_Low',
                'close': 'VVIX_Close'
            })
            
            # Drop frequency column and set date_only as index
            if 'frequency' in df_vvix_daily.columns:
                df_vvix_daily = df_vvix_daily.drop('frequency', axis=1)
            df_vvix_daily = df_vvix_daily.drop('timestamp', axis=1).set_index('date_only')
        
        # Process dividends
        if not df_dividends.empty:
            df_dividends = df_dividends.copy()
            df_dividends['timestamp'] = pd.to_datetime(df_dividends['timestamp'])
            df_dividends['date_only'] = df_dividends['timestamp'].dt.date
            df_dividends = df_dividends.rename(columns={'dividends': f'{ticker_name}_Dividends'})
            df_dividends = df_dividends.drop('timestamp', axis=1).set_index('date_only')
        
        # Merge data using date_only for VIX/VVIX mapping
        merged_df = df_ticker.set_index('date_only')
        
        # Join with daily VIX data
        if not df_vix_daily.empty:
            merged_df = merged_df.join(df_vix_daily, how='inner')
            logger.info(f"After VIX join: {merged_df.shape}")
        
        # Join with daily VVIX data
        if not df_vvix_daily.empty:
            merged_df = merged_df.join(df_vvix_daily, how='inner')
            logger.info(f"After VVIX join: {merged_df.shape}")
        
        # Join with dividends (left join)
        if not df_dividends.empty:
            merged_df = merged_df.join(df_dividends, how='left')
            merged_df[f'{ticker_name}_Dividends'] = merged_df[f'{ticker_name}_Dividends'].fillna(0)
        else:
            merged_df[f'{ticker_name}_Dividends'] = 0
        
        # Reset index and use original timestamp
        merged_df = merged_df.reset_index(drop=True)
        
        # Use the original intraday timestamp for the ticker
        merged_df['timestamp'] = merged_df['original_timestamp']
        merged_df = merged_df.drop(['original_timestamp'], axis=1, errors='ignore')
        
        # Sort by timestamp
        merged_df = merged_df.sort_values('timestamp')
        
        logger.info(f"Final merged dataframe with daily VIX/VVIX: {merged_df.shape}")
        return merged_df
        
    except Exception as e:
        logger.error(f"Error merging data with daily VIX/VVIX: {e}", exc_info=True)
        return pd.DataFrame()


def generate_data_table(df):
    """Generate HTML table from merged dataframe with proper column ordering"""
    try:
        if df.empty:
            return '<div class="alert alert-warning">No data available for the selected period.</div>'
        
        # Debug: Log the columns we received
        logger.info(f"DataFrame columns: {df.columns.tolist()}")
        
        # Format timestamp
        df['Date'] = df['timestamp'].dt.strftime('%Y-%m-%d %H:%M:%S')
        
        # Define column order based on the pattern: Date, Asset OHLC + Dividends, VIX OHLC, VVIX OHLC
        columns = ['Date']
        
        # Get the ticker name from the columns (it's the part before _Open/High/Low/Close)
        ticker_name = None
        for col in df.columns:
            if col.endswith('_Open') and not col.startswith(('VIX_', 'VVIX_')):
                ticker_name = col.replace('_Open', '')
                break
        
        # Add ticker columns in OHLC order
        if ticker_name:
            for suffix in ['_Open', '_High', '_Low', '_Close', '_Dividends']:
                col_name = f'{ticker_name}{suffix}'
                if col_name in df.columns:
                    columns.append(col_name)
        
        # Add VIX columns
        for suffix in ['_Open', '_High', '_Low', '_Close']:
            col_name = f'VIX{suffix}'  # VIX_Open, VIX_High, etc.
            if col_name in df.columns:
                columns.append(col_name)
        
        # Add VVIX columns
        for suffix in ['_Open', '_High', '_Low', '_Close']:
            col_name = f'VVIX{suffix}'  # VVIX_Open, VVIX_High, etc.
            if col_name in df.columns:
                columns.append(col_name)
        
        # Create HTML table with sticky header and limited visible rows
        table_html = '<div class="data-table-stats mb-2">'
        table_html += f'<small class="text-muted">Total rows: <strong>{len(df)}</strong> | Scroll to view all data</small>'
        table_html += '</div>'
        table_html += '<div class="table-responsive data-table-container">'
        table_html += '<table class="table table-dark table-striped table-hover table-sm">'
        table_html += '<thead class="sticky-top bg-dark"><tr>'
        for col in columns:
            # Format column headers for better readability
            display_col = col.replace('_', ' ')
            table_html += f'<th class="text-nowrap">{display_col}</th>'
        table_html += '</tr></thead>'
        table_html += '<tbody>'
        
        # Add all rows (container will handle scrolling)
        for _, row in df.iterrows():
            table_html += '<tr>'
            for col in columns:
                value = row.get(col, '')
                # Format numeric values
                if isinstance(value, (int, float)) and col != 'Date':
                    if 'Dividends' in col:
                        if value == 0:
                            value = '-'
                            cell_class = 'text-muted'
                        else:
                            value = f'{value:.4f}'
                            cell_class = 'text-success'
                    else:
                        value = f'{value:.2f}'
                        cell_class = ''
                else:
                    cell_class = ''
                table_html += f'<td class="text-nowrap {cell_class}">{value}</td>'
            table_html += '</tr>'
        
        table_html += '</tbody></table></div>'
        
        return table_html
        
    except Exception as e:
        logger.error(f"Error generating table: {e}")
        logger.error(f"DataFrame columns: {df.columns.tolist() if not df.empty else 'Empty DataFrame'}")
        return '<div class="alert alert-danger">Error generating data table.</div>'


def index(request):
    """Main view for the Bloomberg-style trading app - AJAX powered"""
    form = ChartDataForm()
    
    context = {
        'form': form,
    }
    
    return render(request, 'trader/index.html', context)


def generate_candlestick_chart(df, ticker, frequency):
    """Generate a plotly candlestick chart with proper responsive dimensions"""
    try:
        # Determine if this is an index or stock
        polygon_client = PolygonAPI()
        ticker_type = polygon_client.get_ticker_type(ticker)
        type_label = "Index" if ticker_type == "index" else "Stock"
        
        # Create candlestick chart
        fig = go.Figure(data=go.Candlestick(
            x=df['timestamp'],
            open=df['open'],
            high=df['high'],
            low=df['low'],
            close=df['close'],
            name=ticker,
            increasing_line_color='#00ff00',  # Green for increasing
            decreasing_line_color='#ff0000',  # Red for decreasing
        ))
        
        # Update layout with dark theme and proper responsive settings
        price_label = "Value" if ticker_type == "index" else "Price ($)"
        chart_title = f'{ticker} {type_label} - Candlestick Chart ({frequency})'
        
        fig.update_layout(
            title={
                'text': chart_title,
                'x': 0.5,
                'xanchor': 'center',
                'font': {'size': 24, 'color': 'white'}
            },
            xaxis_title='Date/Time',
            yaxis_title=price_label,
            template='plotly_dark',
            paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor='rgba(0,0,0,0)',
            font={'color': 'white'},
            # Remove fixed dimensions - let container control size
            autosize=True,
            margin=dict(l=60, r=40, t=80, b=60),  # Reasonable margins
            xaxis=dict(
                gridcolor='rgba(128,128,128,0.3)',
                linecolor='white',
                tickcolor='white',
                titlefont={'color': 'white'},
                tickfont={'color': 'white'}
            ),
            yaxis=dict(
                gridcolor='rgba(128,128,128,0.3)',
                linecolor='white',
                tickcolor='white',
                titlefont={'color': 'white'},
                tickfont={'color': 'white'}
            ),
            legend=dict(
                font={'color': 'white'}
            )
        )
        
        # Configure the chart to be fully responsive
        config = {
            'displayModeBar': True,
            'displaylogo': False,
            'modeBarButtonsToRemove': ['pan2d', 'lasso2d'],
            'responsive': True,
            'toImageButtonOptions': {
                'format': 'png',
                'filename': f'{ticker}_chart',
                'height': 600,
                'width': 1000,
                'scale': 1
            }
        }
        
        # Create responsive HTML wrapper
        div_id = f'candlestick-chart-{ticker.lower().replace(":", "-")}'
        
        # Generate the chart HTML with responsive wrapper
        chart_html = f'''
        <div class="plotly-chart-wrapper">
            {to_html(fig, config=config, include_plotlyjs='cdn', div_id=div_id)}
        </div>
        <script>
        // Ensure chart resizes properly
        window.addEventListener('resize', function() {{
            var chartDiv = document.getElementById('{div_id}');
            if (chartDiv && window.Plotly) {{
                window.Plotly.Plots.resize(chartDiv);
            }}
        }});
        </script>
        '''
        
        return chart_html
        
    except Exception as e:
        logger.error(f"Error generating chart: {e}")
        return None


def save_market_data_to_db(df):
    """Save market data to database"""
    try:
        for _, row in df.iterrows():
            MarketData.objects.update_or_create(
                ticker=row['ticker'],
                timestamp=row['timestamp'],
                frequency=row['frequency'],
                defaults={
                    'open_price': row['open'],
                    'high_price': row['high'],
                    'low_price': row['low'],
                    'close_price': row['close'],
                    'volume': row['volume'],
                }
            )
    except Exception as e:
        logger.error(f"Error saving data to database: {e}")


def search_tickers(request):
    """Search for tickers using Financial Modeling Prep API with Redis caching"""
    if request.method == 'GET':
        query = request.GET.get('q', '').strip()
        
        if not query or len(query) < 1:
            return JsonResponse({'results': []})
        
        # Create cache key for this search
        cache_key = f"ticker_search:{hashlib.md5(query.encode()).hexdigest()}"
        
        # Try to get cached results first
        cached_results = cache.get(cache_key)
        if cached_results is not None:
            logger.debug(f"Cache hit for ticker search: {query}")
            return JsonResponse({'results': cached_results})
        
        try:
            # Use FMP API for ticker search
            url = "https://financialmodelingprep.com/api/v3/search-ticker"
            params = {
                "query": query,
                "limit": 10,
                "apikey": settings.FMP_API_KEY
            }
            
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            
            # Format results
            results = []
            for item in data:
                results.append({
                    'symbol': item.get('symbol'),
                    'name': item.get('name'),
                    'exchange': item.get('stockExchange', '')
                })
            
            # Cache the results for 1 hour
            cache.set(cache_key, results, settings.CACHE_TTL['ticker_search'])
            logger.debug(f"Cached ticker search results for: {query}")
            
            return JsonResponse({'results': results})
            
        except Exception as e:
            logger.error(f"Error searching tickers: {e}")
            return JsonResponse({'results': []})
    
    return JsonResponse({'error': 'Method not allowed'}, status=405)


@csrf_exempt
def ticker_suggestions(request):
    """API endpoint for ticker autocomplete suggestions"""
    if request.method == 'GET':
        query = request.GET.get('q', '').strip()
        
        if len(query) < 1:
            return JsonResponse({'suggestions': []})
        
        try:
            # Try to get suggestions from database first
            db_suggestions = TickerSuggestion.objects.filter(
                ticker__icontains=query,
                is_active=True
            )[:10]
            
            suggestions = []
            for suggestion in db_suggestions:
                suggestions.append({
                    'ticker': suggestion.ticker,
                    'name': suggestion.name,
                    'display': f"{suggestion.ticker} - {suggestion.name}"
                })
            
            # If we don't have enough suggestions, fetch from Polygon API
            if len(suggestions) < 5:
                polygon_client = PolygonAPI()
                api_suggestions = polygon_client.get_ticker_suggestions(query, 10)
                
                for api_suggestion in api_suggestions:
                    # Avoid duplicates
                    if not any(s['ticker'] == api_suggestion['ticker'] for s in suggestions):
                        suggestions.append({
                            'ticker': api_suggestion['ticker'],
                            'name': api_suggestion['name'],
                            'display': f"{api_suggestion['ticker']} - {api_suggestion['name']}"
                        })
                        
                        # Save to database for future use
                        TickerSuggestion.objects.update_or_create(
                            ticker=api_suggestion['ticker'],
                            defaults={
                                'name': api_suggestion['name'],
                                'market': api_suggestion.get('market', 'stocks'),
                                'is_active': True
                            }
                        )
            
            return JsonResponse({'suggestions': suggestions[:10]})
            
        except Exception as e:
            logger.error(f"Error fetching ticker suggestions: {e}")
            return JsonResponse({'suggestions': []})
    
    return JsonResponse({'error': 'Invalid request method'}, status=405)


@csrf_exempt
def ticker_details(request):
    """API endpoint for getting ticker details"""
    if request.method == 'GET':
        ticker = request.GET.get('ticker', '').strip().upper()
        
        if len(ticker) < 1:
            return JsonResponse({'error': 'Ticker is required'}, status=400)
        
        try:
            # Initialize Polygon API client
            polygon_client = PolygonAPI()
            
            # Check if it's a known index first
            if polygon_client.is_index_ticker(ticker):
                ticker_type = 'index'
                # For known indices, we can provide the name
                index_names = {
                    'VIX': 'CBOE Volatility Index',
                    'VVIX': 'VIX of VIX Index',
                    'SPX': 'S&P 500 Index',
                    'DJI': 'Dow Jones Industrial Average',
                    'NDX': 'NASDAQ-100 Index',
                    'RUT': 'Russell 2000 Index',
                    'VXN': 'NASDAQ-100 Volatility Index',
                    'RVX': 'Russell 2000 Volatility Index',
                    'SKEW': 'CBOE SKEW Index',
                    'VIX9D': 'CBOE 9-Day Volatility Index',
                }
                name = index_names.get(ticker, f'{ticker} Index')
            else:
                ticker_type = 'stock'
                # Try to get suggestions to find the name
                suggestions = polygon_client.get_ticker_suggestions(ticker, 20)
                exact_match = next((s for s in suggestions if s['ticker'].upper() == ticker), None)
                
                if exact_match:
                    name = exact_match['name']
                else:
                    # If no exact match found, it might be invalid
                    # Try a more specific search
                    ticker_suggestions = polygon_client.get_ticker_suggestions(ticker, 5)
                    if not ticker_suggestions or not any(s['ticker'].upper() == ticker for s in ticker_suggestions):
                        # Return a default that indicates it might be invalid
                        name = f'{ticker} Stock'
                    else:
                        name = exact_match['name'] if exact_match else f'{ticker} Stock'
            
            return JsonResponse({
                'ticker': ticker,
                'name': name,
                'market': 'indices' if ticker_type == 'index' else 'stocks',
                'type': ticker_type
            })
            
        except Exception as e:
            logger.error(f"Error fetching ticker details: {e}")
            return JsonResponse({
                'ticker': ticker,
                'name': f'{ticker} Stock',
                'market': 'stocks',
                'type': 'stock'
            })
    
    return JsonResponse({'error': 'Invalid request method'}, status=405)


@csrf_exempt
def generate_chart_api(request):
    """API endpoint for generating charts via AJAX - Bloomberg style"""
    if request.method == 'POST':
        try:
            # Parse JSON data
            data = json.loads(request.body)
            ticker = data.get('ticker', '').strip().upper()
            start_date = data.get('start_date', '')
            end_date = data.get('end_date', '')
            frequency = data.get('frequency', 'day')
            
            if not all([ticker, start_date, end_date]):
                return JsonResponse({'error': 'Missing required parameters'}, status=400)
            
            # Date validation for non-daily frequencies
            if frequency != 'day':
                try:
                    start_date_obj = datetime.strptime(start_date, '%Y-%m-%d')
                    feb_2023 = datetime(2023, 2, 1)
                    
                    if start_date_obj < feb_2023:
                        return JsonResponse({
                            'error': 'For non-daily frequencies, start date cannot be before February 2023',
                            'min_date': '2023-02-01'
                        }, status=400)
                except ValueError:
                    return JsonResponse({'error': 'Invalid date format'}, status=400)
            
            # Store in session for backtesting
            request.session['last_ticker'] = ticker
            request.session['last_start_date'] = start_date
            request.session['last_end_date'] = end_date
            request.session['last_frequency'] = frequency
            
            # Create cache key for this chart bundle
            cache_key = f"charts:{hashlib.md5(f'{ticker}_{start_date}_{end_date}_{frequency}'.encode()).hexdigest()}"
            
            # Try cache first
            cached_data = cache.get(cache_key)
            if cached_data is not None:
                logger.debug(f"Cache hit for chart bundle: {ticker}")
                return JsonResponse({
                    'success': True,
                    **cached_data,
                    'cached': True
                })
            
            # Generate fresh charts and data
            # Choose API based on frequency
            if frequency == 'day':
                # Use FMP for ALL daily data (ticker, VIX, VVIX, dividends)
                logger.info(f"Using FMP API for daily data")
                fmp_client = FMPAPI()
                df_ticker = fmp_client.get_ohlc_data(ticker, start_date, end_date, frequency)
                df_dividends = fmp_client.get_dividends(ticker, start_date, end_date)
                
                # Use FMP for VIX and VVIX as well - no Polygon for daily frequency
                # Note: FMP requires URL-encoded symbols for indices: %5E is the URL encoding for ^
                df_vix = fmp_client.get_ohlc_data('%5EVIX', start_date, end_date, frequency)
                df_vvix = fmp_client.get_ohlc_data('%5EVVIX', start_date, end_date, frequency)
            else:
                # Use Polygon for non-daily frequencies
                logger.info(f"Using Polygon API for {frequency} data")
                polygon_client = PolygonAPI()
                df_ticker = polygon_client.get_ohlc_data(ticker, start_date, end_date, frequency)
                df_vix = polygon_client.get_ohlc_data('VIX', start_date, end_date, frequency)
                df_vvix = polygon_client.get_ohlc_data('VVIX', start_date, end_date, frequency)
                df_dividends = polygon_client.get_dividends(ticker, start_date, end_date)
            
            # Log the data we got
            logger.info(f"Data fetched - Ticker: {df_ticker.shape}, VIX: {df_vix.shape}, VVIX: {df_vvix.shape}")
            if not df_ticker.empty:
                logger.info(f"Ticker date range: {df_ticker['timestamp'].min()} to {df_ticker['timestamp'].max()}")
            if not df_vix.empty:
                logger.info(f"VIX date range: {df_vix['timestamp'].min()} to {df_vix['timestamp'].max()}")
            if not df_vvix.empty:
                logger.info(f"VVIX date range: {df_vvix['timestamp'].min()} to {df_vvix['timestamp'].max()}")
            
            if df_ticker.empty:
                return JsonResponse({
                    'error': f'No data found for {ticker} in the specified date range'
                }, status=404)
            
            # Generate charts
            chart_html_ticker = generate_candlestick_chart(df_ticker, ticker, frequency)
            chart_html_vix = generate_candlestick_chart(df_vix, 'VIX', frequency) if not df_vix.empty else None
            chart_html_vvix = generate_candlestick_chart(df_vvix, 'VVIX', frequency) if not df_vvix.empty else None
            
            # Merge dataframes for table
            merged_df = merge_ticker_data(df_ticker, df_vix, df_vvix, df_dividends, ticker)
            
            # If merge failed for intraday data, try falling back to daily VIX/VVIX data
            if merged_df.empty and frequency in ['hour', '1hour', '60min', 'minute', '1min', '5min', '15min', '30min']:
                logger.warning(f"Initial merge failed for {frequency} frequency. Trying with daily VIX/VVIX data...")
                
                # Fetch daily VIX/VVIX data as fallback
                df_vix_daily = polygon_client.get_ohlc_data('VIX', start_date, end_date, 'day')
                df_vvix_daily = polygon_client.get_ohlc_data('VVIX', start_date, end_date, 'day')
                
                if not df_vix_daily.empty and not df_vvix_daily.empty:
                    # Use the custom merge function that joins intraday ticker data with daily VIX/VVIX
                    merged_df = merge_ticker_data_with_daily_vix(df_ticker, df_vix_daily, df_vvix_daily, df_dividends, ticker)
                    
                    if not merged_df.empty:
                        logger.info(f"Successfully merged using daily VIX/VVIX data. Shape: {merged_df.shape}")
            
            # Check if merge was successful
            if merged_df.empty:
                return JsonResponse({
                    'error': 'Failed to merge data. No common timestamps found between ticker and VIX/VVIX data.'
                }, status=400)
            
            logger.info(f"Merged dataframe shape: {merged_df.shape}")
            logger.info(f"Merged dataframe columns: {merged_df.columns.tolist()}")
            
            # Save merged data to SQLite database
            from .db_storage import MarketDataDB
            db = MarketDataDB()
            db.save_data(merged_df, ticker, frequency, start_date, end_date)
            logger.info(f"Saved merged data to SQLite database for {ticker} {frequency}")
            
            table_html = generate_data_table(merged_df)
            
            response_data = {
                'success': True,
                'chart_html_ticker': chart_html_ticker,
                'chart_html_vix': chart_html_vix,
                'chart_html_vvix': chart_html_vvix,
                'table_html': table_html,
                'cached': False,
                'data_points': len(df_ticker),
                'timestamp': pd.Timestamp.now().isoformat()  # Force browser refresh
            }
            
            # Cache the charts for 15 minutes
            cache.set(cache_key, response_data, settings.CACHE_TTL['chart_data'])
            logger.debug(f"Cached chart bundle for: {ticker}")
            
            # Save to database (async would be better)
            save_market_data_to_db(df_ticker)
            
            return JsonResponse(response_data)
            
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON data'}, status=400)
        except Exception as e:
            logger.error(f"Error generating charts: {e}")
            return JsonResponse({'error': 'Failed to generate charts'}, status=500)
    
    return JsonResponse({'error': 'Method not allowed'}, status=405)

