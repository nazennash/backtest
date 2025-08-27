from django.shortcuts import render
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.core.cache import cache
import json
import pandas as pd
import numpy as np

import logging
import hashlib
from io import BytesIO

from .backtest_engine import vix_backtest, vix_tsl_backtest
from .backtest_visualizations import (
    create_portfolio_value_chart,
    create_portfolio_value_with_dividends_chart,
    create_dividends_bar_chart,
    create_overall_drawdown_chart,
    create_trade_drawdown_chart,
    calculate_performance_metrics,
    calculate_dividend_inclusive_metrics,
    calculate_dividend_yield_metrics
)
from .json_utils import NumpyJSONEncoder, sanitize_metrics_dict

logger = logging.getLogger(__name__)


def backtesting_section(request):
    """Render the backtesting section for inclusion in the main dashboard."""
    return render(request, 'backtesting/backtesting_section.html')


@csrf_exempt
def get_backtest_progress(request, progress_key):
    """Get the current progress of a backtest"""
    if request.method != 'GET':
        return JsonResponse({'error': 'Method not allowed'}, encoder=NumpyJSONEncoder, status=405)
    
    try:
        from .models import BacktestProgress
        
        try:
            progress_obj = BacktestProgress.objects.get(progress_key=progress_key)
            progress_data = {
                'current': progress_obj.current,
                'total': progress_obj.total,
                'percentage': progress_obj.percentage,
                'status': progress_obj.status,
                'error': progress_obj.error
            }
            
            # Return both formats for compatibility
            return JsonResponse({
                'success': True,
                'current': progress_obj.current,
                'total': progress_obj.total,
                'percentage': progress_obj.percentage,
                'status': progress_obj.status,
                'error': progress_obj.error,
                'progress': progress_data
            }, encoder=NumpyJSONEncoder)
            
        except BacktestProgress.DoesNotExist:
            return JsonResponse({
                'success': False,
                'error': 'Progress data not found'
            }, encoder=NumpyJSONEncoder, status=404)
        
    except Exception as e:
        logger.error(f"Error getting backtest progress: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, encoder=NumpyJSONEncoder, status=500)


@csrf_exempt
def run_strategy1_backtest(request):
    """Run Strategy 1 VIX Threshold backtest"""
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, encoder=NumpyJSONEncoder, status=405)
    
    try:
        # Parse request data
        data = json.loads(request.body)
        vix_upper = float(data.get('vix_upper', 20))
        vix_lower = float(data.get('vix_lower', 0))
        vvix_upper = float(data.get('vvix_upper', 100))
        vvix_lower = float(data.get('vvix_lower', 0))
        investment_amount = float(data.get('investment_amount', 10000))
        
        logger.info(f"Received backtest request with params: VIX({vix_lower}-{vix_upper}), VVIX({vvix_lower}-{vvix_upper}), Investment: {investment_amount}")
        
        # Simple approach: Get data from session and fetch fresh
        ticker = request.session.get('last_ticker', 'QQQ')
        start_date = request.session.get('last_start_date')
        end_date = request.session.get('last_end_date')
        frequency = request.session.get('last_frequency', 'day')
        
        # If no session data, use defaults
        if not start_date or not end_date:
            # Default to last 6 months
            from datetime import datetime, timedelta
            end_date = datetime.now().strftime('%Y-%m-%d')
            start_date = (datetime.now() - timedelta(days=180)).strftime('%Y-%m-%d')
            logger.info(f"No session data, using defaults: {ticker} from {start_date} to {end_date}")
        
        logger.info(f"Using data params: {ticker} from {start_date} to {end_date}, frequency: {frequency}")
        
        # Load data from SQLite database
        from trader.db_storage import MarketDataDB
        db = MarketDataDB()
        
        # First check if data exists
        if not db.check_data_exists(ticker, frequency):
            logger.warning(f"No data found in database for {ticker} {frequency}")
            return JsonResponse({
                'success': False,
                'error': f'No data loaded. Please use the "Get Data" button in the first section to load and prepare the data before running backtests.'
            }, encoder=NumpyJSONEncoder)
        
        # Load the data
        merged_df = db.load_data(ticker, frequency, start_date, end_date)
        
        if merged_df is None or merged_df.empty:
            logger.error(f"Failed to load data from database for {ticker} {frequency}")
            return JsonResponse({
                'success': False,
                'error': f'Failed to load data from database. Please reload data using the "Get Data" button.'
            }, encoder=NumpyJSONEncoder)
        
        logger.info(f"Loaded data from SQLite database: {merged_df.shape}")
        
        if merged_df.empty:
            return JsonResponse({
                'success': False,
                'error': f'Failed to merge {ticker} data with VIX/VVIX data. This usually happens when:\n'
                        f'1. The ticker has different trading hours than VIX/VVIX\n'
                        f'2. No overlapping dates exist between the datasets\n'
                        f'3. The selected date range has no VIX/VVIX data available\n\n'
                        f'Please try a different date range or use daily frequency.'
            }, encoder=NumpyJSONEncoder)
        
        logger.info(f"Merged dataframe shape: {merged_df.shape}")
        
        # Prepare data for backtesting
        backtest_df = merged_df.copy()
        
        # Generate unique progress key for this backtest
        import uuid
        import threading
        progress_key = f"backtest_progress_{uuid.uuid4().hex[:8]}"
        logger.info(f"Generated progress key: {progress_key}")
        
        # Create progress object in database
        from .models import BacktestProgress
        
        # Clean up old records first
        deleted_count = BacktestProgress.cleanup_old_records(hours=2)
        if deleted_count > 0:
            logger.info(f"Cleaned up {deleted_count} old progress records")
        
        progress_obj = BacktestProgress.objects.create(
            progress_key=progress_key,
            current=0,
            total=len(backtest_df),
            percentage=0,
            status='Starting backtest...'
        )
        logger.info(f"Created progress object for key {progress_key} with {len(backtest_df)} rows")
        
        # Store all data needed for the backtest in cache
        backtest_data = {
            'df': backtest_df,
            'ticker': ticker,
            'vix_lower': vix_lower,
            'vix_upper': vix_upper,
            'vvix_lower': vvix_lower,
            'vvix_upper': vvix_upper,
            'investment_amount': investment_amount,
            'start_date': start_date,
            'end_date': end_date,
            'progress_key': progress_key,
            'frequency': frequency  # Add frequency for Excel export
        }
        cache.set(f"{progress_key}_data", backtest_data, 600)  # Store for 10 minutes
        
        # Define function to run backtest in background
        def run_backtest_async():
            # Import Django database connection handling
            from django.db import connection
            
            try:
                logger.info(f"Starting async backtest thread for key: {progress_key}")
                
                # Ensure we have a fresh database connection in the thread
                connection.ensure_connection()
                
                # Update progress to show we're starting
                try:
                    progress_obj = BacktestProgress.objects.get(progress_key=progress_key)
                    progress_obj.percentage = 1
                    progress_obj.status = 'Backtest engine started...'
                    progress_obj.save()
                    logger.info(f"Updated progress to 1% for key: {progress_key}")
                except Exception as e:
                    logger.error(f"Error updating progress start: {e}")
                
                # Small delay to ensure the thread is running
                import time
                time.sleep(0.1)
                
                # Run the actual backtest
                logger.info(f"Calling vix_backtest with {len(backtest_df)} rows")
                result_df = vix_backtest(
                    df=backtest_df,
                    asset_name=ticker,
                    VIX_Lower_Bound=vix_lower,
                    VIX_Upper_Bound=vix_upper,
                    VVIX_Lower_Bound=vvix_lower,
                    VVIX_Upper_Bound=vvix_upper,
                    Investment_Amount=investment_amount,
                    progress_key=progress_key
                )
                
                # Store the results in the progress object AND cache for redundancy
                progress_obj = BacktestProgress.objects.get(progress_key=progress_key)
                progress_obj.set_result(result_df)
                progress_obj.percentage = 100
                progress_obj.status = 'Backtest complete!'
                progress_obj.save()
                
                # Also store in cache as backup (both as DataFrame and JSON)
                cache.set(f"{progress_key}_result", result_df, 3600)  # Store DataFrame directly
                cache.set(f"{progress_key}_result_json", result_df.to_json(orient='split'), 3600)  # Store as JSON
                
                logger.info(f"Backtest complete for key: {progress_key}, result shape: {result_df.shape}")
                logger.info(f"Results stored in database and cache for redundancy")
                
            except Exception as e:
                logger.error(f"Error in async backtest: {e}", exc_info=True)
                try:
                    progress_obj = BacktestProgress.objects.get(progress_key=progress_key)
                    progress_obj.current = 0
                    progress_obj.percentage = 0
                    progress_obj.status = f'Error: {str(e)}'
                    progress_obj.error = True
                    progress_obj.save()
                except Exception as db_error:
                    logger.error(f"Error updating progress on error: {db_error}")
            finally:
                # Close database connection in thread
                connection.close()
                logger.info(f"Closed database connection for thread {progress_key}")
        
        # Start backtest in background thread
        backtest_thread = threading.Thread(target=run_backtest_async, name=f"backtest-{progress_key}")
        backtest_thread.daemon = True  # Make it a daemon thread so it doesn't block shutdown
        
        # Log thread status
        logger.info(f"Starting thread {backtest_thread.name}")
        backtest_thread.start()
        
        # Give thread a moment to start
        import time
        time.sleep(0.1)
        
        logger.info(f"Thread {backtest_thread.name} is alive: {backtest_thread.is_alive()}")
        
        # Return immediately with progress key
        return JsonResponse({
            'success': True,
            'progress_key': progress_key,
            'message': 'Backtest started successfully'
        }, encoder=NumpyJSONEncoder)
        
    except Exception as e:
        logger.error(f"Error in strategy 1 backtest: {str(e)}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, encoder=NumpyJSONEncoder, status=500)


@csrf_exempt
def run_strategy2_backtest(request):
    """Run Strategy 2 VIX Threshold with TSL backtest"""
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, encoder=NumpyJSONEncoder, status=405)
    
    try:
        # Parse request data
        data = json.loads(request.body)
        vix_upper = float(data.get('vix_upper', 20))
        vix_lower = float(data.get('vix_lower', 0))
        vvix_upper = float(data.get('vvix_upper', 100))
        vvix_lower = float(data.get('vvix_lower', 0))
        investment_amount = float(data.get('investment_amount', 10000))
        tsl_percentage = float(data.get('tsl_percentage', 0.02))  # Default 2% (0.02 as decimal)
        wait_period = int(data.get('wait_period', 2))  # Default 2 days
        ignore_low = bool(data.get('ignore_low', False))  # Default False
        
        logger.info(f"Received Strategy 2 backtest request with params: VIX({vix_lower}-{vix_upper}), VVIX({vvix_lower}-{vvix_upper}), TSL: {tsl_percentage*100}%, Wait: {wait_period} days, Ignore Low: {ignore_low}")
        
        # Simple approach: Get data from session and fetch fresh
        ticker = request.session.get('last_ticker', 'QQQ')
        start_date = request.session.get('last_start_date')
        end_date = request.session.get('last_end_date')
        frequency = request.session.get('last_frequency', 'day')
        
        logger.info(f"Session data - ticker: {ticker}, start: {start_date}, end: {end_date}, freq: {frequency}")
        
        # If no session data, use defaults but check if data exists
        if not start_date or not end_date:
            # Default to last 6 months
            from datetime import datetime, timedelta
            end_date = datetime.now().strftime('%Y-%m-%d')
            start_date = (datetime.now() - timedelta(days=180)).strftime('%Y-%m-%d')
            logger.info(f"No session data, using defaults: {ticker} from {start_date} to {end_date}")
            
            # Check if default data exists before returning error
            from trader.db_storage import MarketDataDB
            db = MarketDataDB()
            if not db.check_data_exists(ticker, frequency):
                return JsonResponse({
                    'success': False,
                    'error': 'No data has been loaded yet. Please use the "Get Data" button in the first section to load market data before running backtests.'
                }, encoder=NumpyJSONEncoder)
        
        logger.info(f"Using data params: {ticker} from {start_date} to {end_date}, frequency: {frequency}")
        
        # Date validation for non-daily frequencies
        if frequency != 'day':
            try:
                from datetime import datetime
                start_date_obj = datetime.strptime(start_date, '%Y-%m-%d')
                feb_2023 = datetime(2023, 2, 1)
                
                if start_date_obj < feb_2023:
                    return JsonResponse({
                        'error': 'For non-daily frequencies, start date cannot be before February 2023',
                        'min_date': '2023-02-01'
                    }, encoder=NumpyJSONEncoder, status=400)
            except ValueError:
                return JsonResponse({'error': 'Invalid date format'}, status=400, encoder=NumpyJSONEncoder)
        
        # Load data from SQLite database
        from trader.db_storage import MarketDataDB
        db = MarketDataDB()
        
        # First check if data exists
        if not db.check_data_exists(ticker, frequency):
            logger.warning(f"No data found in database for {ticker} {frequency}")
            return JsonResponse({
                'success': False,
                'error': f'No data loaded. Please use the "Get Data" button in the first section to load and prepare the data before running backtests.'
            }, encoder=NumpyJSONEncoder)
        
        # Load the data
        merged_df = db.load_data(ticker, frequency, start_date, end_date)
        
        if merged_df is None or merged_df.empty:
            logger.error(f"Failed to load data from database for {ticker} {frequency}")
            return JsonResponse({
                'success': False,
                'error': f'Failed to load data from database. Please reload data using the "Get Data" button.'
            }, encoder=NumpyJSONEncoder)
        
        logger.info(f"Loaded data from SQLite database: {merged_df.shape}")
        
        if merged_df.empty:
            return JsonResponse({
                'success': False,
                'error': f'Failed to merge {ticker} data with VIX/VVIX data. This usually happens when:\n'
                        f'1. The ticker has different trading hours than VIX/VVIX\n'
                        f'2. No overlapping dates exist between the datasets\n'
                        f'3. The selected date range has no VIX/VVIX data available\n\n'
                        f'Please try a different date range or use daily frequency.'
            }, encoder=NumpyJSONEncoder)
        
        logger.info(f"Merged dataframe shape: {merged_df.shape}")
        
        # Prepare data for backtesting
        backtest_df = merged_df.copy()
        
        # Generate unique progress key for this backtest
        import uuid
        import threading
        progress_key = f"backtest_progress_{uuid.uuid4().hex[:8]}"
        logger.info(f"Generated progress key: {progress_key}")
        
        # Create progress object in database
        from .models import BacktestProgress
        
        # Clean up old records first
        deleted_count = BacktestProgress.cleanup_old_records(hours=2)
        if deleted_count > 0:
            logger.info(f"Cleaned up {deleted_count} old progress records")
        
        progress_obj = BacktestProgress.objects.create(
            progress_key=progress_key,
            current=0,
            total=len(backtest_df),
            percentage=0,
            status='Starting backtest...'
        )
        logger.info(f"Created progress object for key {progress_key} with {len(backtest_df)} rows")
        
        # Store all data needed for the backtest in cache
        backtest_data = {
            'df': backtest_df,
            'ticker': ticker,
            'vix_lower': vix_lower,
            'vix_upper': vix_upper,
            'vvix_lower': vvix_lower,
            'vvix_upper': vvix_upper,
            'investment_amount': investment_amount,
            'tsl_percentage': tsl_percentage,
            'wait_period': wait_period,
            'ignore_low': ignore_low,
            'start_date': start_date,
            'end_date': end_date,
            'progress_key': progress_key,
            'frequency': frequency,  # Add frequency for Excel export
            'strategy': 2  # Mark as Strategy 2
        }
        cache.set(f"{progress_key}_data", backtest_data, 600)  # Store for 10 minutes
        
        # Define function to run backtest in background
        def run_backtest_async():
            # Import Django database connection handling
            from django.db import connection
            
            try:
                logger.info(f"Starting async backtest thread for key: {progress_key}")
                
                # Ensure we have a fresh database connection in the thread
                connection.ensure_connection()
                
                # Update progress to show we're starting
                try:
                    progress_obj = BacktestProgress.objects.get(progress_key=progress_key)
                    progress_obj.percentage = 1
                    progress_obj.status = 'Backtest engine started...'
                    progress_obj.save()
                    logger.info(f"Updated progress to 1% for key: {progress_key}")
                except Exception as e:
                    logger.error(f"Error updating progress start: {e}")
                
                # Small delay to ensure the thread is running
                import time
                time.sleep(0.1)
                
                # Run the actual backtest
                logger.info(f"Calling vix_tsl_backtest with {len(backtest_df)} rows")
                result_df = vix_tsl_backtest(
                    df=backtest_df,
                    asset_name=ticker,
                    VIX_Lower_Bound=vix_lower,
                    VIX_Upper_Bound=vix_upper,
                    VVIX_Lower_Bound=vvix_lower,
                    VVIX_Upper_Bound=vvix_upper,
                    Investment_Amount=investment_amount,
                    TSL_Percentage=tsl_percentage,
                    Wait_Period=wait_period,
                    Ignore_Low=ignore_low,
                    progress_key=progress_key
                )
                
                # Store the results in the progress object AND cache for redundancy
                progress_obj = BacktestProgress.objects.get(progress_key=progress_key)
                progress_obj.set_result(result_df)
                progress_obj.percentage = 100
                progress_obj.status = 'Backtest complete!'
                progress_obj.save()
                
                # Also store in cache as backup (both as DataFrame and JSON)
                cache.set(f"{progress_key}_result", result_df, 3600)  # Store DataFrame directly
                cache.set(f"{progress_key}_result_json", result_df.to_json(orient='split'), 3600)  # Store as JSON
                
                logger.info(f"Backtest complete for key: {progress_key}, result shape: {result_df.shape}")
                logger.info(f"Results stored in database and cache for redundancy")
                
            except Exception as e:
                logger.error(f"Error in async backtest: {e}", exc_info=True)
                try:
                    progress_obj = BacktestProgress.objects.get(progress_key=progress_key)
                    progress_obj.current = 0
                    progress_obj.percentage = 0
                    progress_obj.status = f'Error: {str(e)}'
                    progress_obj.error = True
                    progress_obj.save()
                except Exception as db_error:
                    logger.error(f"Error updating progress on error: {db_error}")
            finally:
                # Close database connection in thread
                connection.close()
                logger.info(f"Closed database connection for thread {progress_key}")
        
        # Start backtest in background thread
        backtest_thread = threading.Thread(target=run_backtest_async, name=f"backtest-{progress_key}")
        backtest_thread.daemon = True  # Make it a daemon thread so it doesn't block shutdown
        
        # Log thread status
        logger.info(f"Starting thread {backtest_thread.name}")
        backtest_thread.start()
        
        # Give thread a moment to start
        import time
        time.sleep(0.1)
        
        logger.info(f"Thread {backtest_thread.name} is alive: {backtest_thread.is_alive()}")
        
        # Return immediately with progress key
        return JsonResponse({
            'success': True,
            'progress_key': progress_key,
            'message': 'Backtest started successfully'
        }, encoder=NumpyJSONEncoder)
        
    except Exception as e:
        logger.error(f"Error in strategy 2 backtest: {str(e)}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, encoder=NumpyJSONEncoder, status=500)


@csrf_exempt
def get_backtest_result(request):
    """Get the result of a completed backtest"""
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, encoder=NumpyJSONEncoder, status=405)
    
    try:
        data = json.loads(request.body)
        progress_key = data.get('progress_key')
        
        if not progress_key:
            return JsonResponse({'error': 'No progress key provided'}, status=400, encoder=NumpyJSONEncoder)
        
        # Check if backtest is complete using database
        from .models import BacktestProgress
        
        try:
            progress_obj = BacktestProgress.objects.get(progress_key=progress_key)
        except BacktestProgress.DoesNotExist:
            return JsonResponse({'error': 'Progress data not found'}, status=404, encoder=NumpyJSONEncoder)
        
        # Check for errors
        if progress_obj.error:
            return JsonResponse({
                'success': False,
                'error': progress_obj.status
            }, encoder=NumpyJSONEncoder)
        
        # Check if complete
        if progress_obj.percentage < 100:
            return JsonResponse({
                'success': False,
                'status': 'incomplete',
                'progress': {
                    'current': progress_obj.current,
                    'total': progress_obj.total,
                    'percentage': progress_obj.percentage,
                    'status': progress_obj.status
                }
            }, encoder=NumpyJSONEncoder)
        
        # Get the result dataframe from database with retry logic
        result_df = None
        max_retries = 3
        retry_delay = 0.5
        
        for attempt in range(max_retries):
            # First try to get from database
            result_df = progress_obj.get_result()
            
            if result_df is not None:
                logger.info(f"Successfully retrieved results from database on attempt {attempt + 1}")
                break
            
            # If database failed, try cache
            cached_result = cache.get(f"{progress_key}_result")
            if cached_result is not None:
                # If it's already a DataFrame, use it directly
                if hasattr(cached_result, 'shape'):
                    result_df = cached_result
                else:
                    # Otherwise, it's JSON that needs to be parsed
                    try:
                        result_df = pd.read_json(cached_result, orient='split')
                    except:
                        result_df = None
                
                if result_df is not None:
                    logger.info(f"Successfully retrieved results from cache on attempt {attempt + 1}")
                    break
            
            # Also try the JSON version in cache
            cached_json = cache.get(f"{progress_key}_result_json")
            if cached_json is not None:
                try:
                    from io import StringIO
                    result_df = pd.read_json(StringIO(cached_json), orient='split')
                    logger.info(f"Successfully retrieved JSON results from cache on attempt {attempt + 1}")
                    break
                except:
                    result_df = None
            
            # If still no results and not the last attempt, wait and retry
            if attempt < max_retries - 1:
                logger.warning(f"Results not ready on attempt {attempt + 1}, waiting {retry_delay}s before retry...")
                import time
                time.sleep(retry_delay)
                # Refresh the progress object
                try:
                    progress_obj.refresh_from_db()
                except:
                    pass
        
        if result_df is None:
            # Check if the backtest actually failed
            if progress_obj.error:
                return JsonResponse({
                    'success': False,
                    'error': f'Backtest failed: {progress_obj.status}'
                }, encoder=NumpyJSONEncoder)
            else:
                return JsonResponse({
                    'success': False,
                    'error': 'Results not ready yet. The backtest may still be finalizing. Please try again in a moment.'
                }, encoder=NumpyJSONEncoder)
        
        # Get the original request data
        backtest_data = cache.get(f"{progress_key}_data")
        if not backtest_data:
            # Try to reconstruct basic data from the result dataframe
            logger.warning("Original request data not found in cache, using defaults")
            backtest_data = {
                'ticker': 'Unknown',
                'investment_amount': 10000,
                'start_date': str(result_df['timestamp'].iloc[0]) if 'timestamp' in result_df.columns else 'Unknown',
                'end_date': str(result_df['timestamp'].iloc[-1]) if 'timestamp' in result_df.columns else 'Unknown',
                'frequency': 'Unknown'
            }
        
        ticker = backtest_data['ticker']
        investment_amount = backtest_data['investment_amount']
        start_date = backtest_data['start_date']
        end_date = backtest_data['end_date']
        
        logger.info(f"Returning results for backtest {progress_key}. Result shape: {result_df.shape}")
        
        # Determine strategy name from backtest data
        strategy_num = backtest_data.get('strategy', 1)  # Default to 1 if not specified
        strategy_name = f"Strategy {strategy_num}"
        if strategy_num == 2:
            strategy_name += " (TSL)"  # Add TSL indicator for Strategy 2
        
        # Generate portfolio value chart using the new function
        chart_html = create_portfolio_value_chart(
            result_df=result_df,
            ticker=ticker,
            strategy_name=strategy_name,
            investment_amount=investment_amount
        )
        
        # Generate portfolio value with dividends chart
        chart_dividends_html = create_portfolio_value_with_dividends_chart(
            result_df=result_df,
            ticker=ticker,
            strategy_name=strategy_name,
            investment_amount=investment_amount
        )
        
        # Generate dividends bar chart
        dividends_bar_html = create_dividends_bar_chart(
            result_df=result_df,
            ticker=ticker
        )
        
        # Generate Overall Drawdown Chart using the new function
        dd_overall_html = create_overall_drawdown_chart(result_df)
        
        # Generate Drawdown per Trade Chart using the new function
        dd_trade_html = create_trade_drawdown_chart(result_df)
        
        # Calculate comprehensive metrics using the new function
        metrics = calculate_performance_metrics(result_df, investment_amount)
        
        # Calculate dividend-inclusive metrics
        dividend_metrics = calculate_dividend_inclusive_metrics(result_df, investment_amount)
        
        # Calculate dividend yield metrics
        dividend_yield_metrics = calculate_dividend_yield_metrics(result_df, investment_amount)
        
        # Merge dividend metrics into main metrics dict
        metrics.update(dividend_metrics)
        metrics.update(dividend_yield_metrics)
        
        # Sanitize metrics to ensure all values are JSON serializable
        # This handles NumPy int64, float64, inf, nan, etc.
        metrics = sanitize_metrics_dict(metrics)
        
        # Generate results table HTML
        # Format the DataFrame for display
        display_df = result_df.copy()
        
        # Format numeric columns - now including all OHLC columns
        for col in display_df.columns:
            # Skip non-numeric columns
            if col in ['Signal', 'Entry_Marker', 'Entry_Signal', 'In_Position', 
                      'Exit_type', 'TRADE_ID', 'timestamp']:
                continue
                
            # Try to convert to numeric
            original_values = display_df[col].copy()
            display_df[col] = pd.to_numeric(display_df[col], errors='coerce')
            
            # Format based on column type
            if '_Open' in col or '_High' in col or '_Low' in col or '_Close' in col:
                # OHLC price columns
                display_df[col] = display_df[col].apply(lambda x: f'{x:.2f}' if pd.notna(x) else '')
            elif col in ['Entry_Price', 'Exit_Price', 'Portfolio_Value', 'Peak_Price', 'TSL_Price']:
                # Currency columns with dollar sign
                display_df[col] = display_df[col].apply(lambda x: f'${x:,.2f}' if pd.notna(x) else '')
            elif col == 'Shares':
                display_df[col] = display_df[col].apply(lambda x: f'{x:,.4f}' if pd.notna(x) else '')
            elif '%' in col:
                display_df[col] = display_df[col].apply(lambda x: f'{x:.2f}%' if pd.notna(x) else '')
            elif col == 'Daily_Return' or 'return' in col.lower():
                # Return columns - format to 2 decimal places
                display_df[col] = display_df[col].apply(lambda x: f'{x:.2f}' if pd.notna(x) else '')
            elif '_Dividends' in col:
                # Dividend columns
                display_df[col] = display_df[col].apply(lambda x: f'${x:.4f}' if pd.notna(x) and x > 0 else '0')
            elif 'volume' in col.lower():
                # Volume columns
                display_df[col] = display_df[col].apply(lambda x: f'{int(x):,}' if pd.notna(x) else '0')
            elif col in ['TRADE_SESSION_ID', 'Wait_Counter', 'TRADE_ID']:
                # These columns should show empty string instead of nan
                display_df[col] = display_df[col].apply(lambda x: str(x) if pd.notna(x) and str(x) != 'nan' else '')
            else:
                # For any other numeric columns, check if conversion failed
                if display_df[col].isna().all():
                    # Restore original values if conversion failed completely
                    display_df[col] = original_values
        
        # Format timestamp column
        if 'timestamp' in display_df.columns:
            display_df['timestamp'] = pd.to_datetime(display_df['timestamp']).dt.strftime('%Y-%m-%d %H:%M')
        
        # Replace all remaining NaN values with empty strings
        display_df = display_df.fillna('')
        
        # Also replace string 'nan' values with empty strings
        display_df = display_df.replace('nan', '')
        
        # Create HTML table
        table_html = f'''
        <div class="backtest-results-table">
            <div class="d-flex justify-content-between align-items-center mb-3">
                <div>
                    <h6 class="mb-0">Detailed Backtest Results (All Data)</h6>
                    <p class="text-muted small mb-0">Showing all original OHLC data plus calculated backtest metrics</p>
                </div>
                <button class="btn btn-success btn-sm" id="download-excel-btn" onclick="downloadBacktestExcel()">
                    <i class="fas fa-download me-1"></i> Download Excel
                </button>
            </div>
            <div class="table-container" style="max-height: 400px; overflow: auto;">
                <table class="table table-dark table-striped table-hover table-sm">
                    <thead style="position: sticky; top: 0; background-color: #1a1a1a; z-index: 10;">
                        <tr>
        '''
        
        # Add table headers
        for col in display_df.columns:
            table_html += f'<th>{col}</th>'
        
        table_html += '''
                        </tr>
                    </thead>
                    <tbody>
        '''
        
        # Add table rows (show all rows, scrollable)
        for idx, row in display_df.iterrows():
            table_html += '<tr>'
            for col in display_df.columns:
                value = row[col]
                # Add special styling for certain columns
                if col == 'Entry_Signal' and value == True:
                    table_html += '<td class="text-success">✓</td>'
                elif col == 'Exit_type' and value:
                    table_html += f'<td class="text-warning">{value}</td>'
                elif col == 'In_Position' and value == True:
                    table_html += '<td class="text-info">●</td>'
                else:
                    table_html += f'<td>{value}</td>'
            table_html += '</tr>'
        
        table_html += '''
                    </tbody>
                </table>
            </div>
            <small class="text-muted mt-2">Showing all {total_rows} rows. Scroll to see more.</small>
        </div>
        '''.format(total_rows=len(display_df))
        
        # Add some custom CSS for the table
        table_style = '''
        <style>
        .backtest-results-table {
            margin-top: 30px;
            padding: 20px;
            background-color: rgba(0, 0, 0, 0.3);
            border-radius: 8px;
        }
        .table-container {
            border: 1px solid #333;
            border-radius: 4px;
            position: relative;
        }
        .table-container::-webkit-scrollbar {
            width: 10px;
            height: 10px;
        }
        .table-container::-webkit-scrollbar-track {
            background: #1a1a1a;
        }
        .table-container::-webkit-scrollbar-thumb {
            background: #666;
            border-radius: 4px;
        }
        .table-container::-webkit-scrollbar-thumb:hover {
            background: #888;
        }
        .table-container::-webkit-scrollbar-corner {
            background: #1a1a1a;
        }
        .backtest-results-table table {
            margin-bottom: 0;
            white-space: nowrap;
        }
        .backtest-results-table th {
            font-size: 0.85rem;
            font-weight: 600;
            border-top: none;
            padding: 8px 12px;
            background-color: #1a1a1a !important;
        }
        .backtest-results-table td {
            font-size: 0.82rem;
            padding: 6px 12px;
        }
        /* Highlight important columns */
        .backtest-results-table th:nth-child(1),
        .backtest-results-table td:nth-child(1) {
            position: sticky;
            left: 0;
            background-color: #1a1a1a !important;
            z-index: 5;
            border-right: 1px solid #444;
        }
        </style>
        '''
        
        # Use progress_key as session_key for consistency
        session_key = progress_key
        
        # Store in cache for period updates
        cache_key = f'backtest_results_{session_key}'
        cache_data = {
            'result_df': result_df.to_json(date_format='iso'),
            'investment_amount': investment_amount
        }
        cache.set(cache_key, cache_data, 3600)  # Store for 1 hour
        
        # Store the result DataFrame separately for Excel download
        cache.set(f'backtest_result_{session_key}', result_df.to_json(orient='split'), 3600)
        
        return JsonResponse({
            'success': True,
            'chart_html': chart_html,
            'chart_dividends_html': chart_dividends_html,
            'dividends_bar_html': dividends_bar_html,
            'dd_overall_html': dd_overall_html,
            'dd_trade_html': dd_trade_html,
            'table_html': table_style + table_html,
            'metrics': metrics,
            'session_key': session_key,
            'progress_key': progress_key,  # Add progress key for frontend polling
            'chart_dates': {
                'start': start_date,
                'end': end_date
            },
            'summary': {
                'initial_value': metrics['initial_value'],
                'final_value': metrics['final_value'],
                'total_return': metrics['total_return'],
                'max_drawdown': metrics['max_drawdown'],
                'total_trades': metrics['num_trades'],
                'total_rows': len(result_df)
            }
        }, encoder=NumpyJSONEncoder)
        
    except Exception as e:
        logger.error(f"Error in strategy 1 backtest: {str(e)}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': f'Backtest failed: {str(e)}'
        }, encoder=NumpyJSONEncoder)


@require_http_methods(["POST"])
def update_metrics_for_period(request):
    """Update metrics for a specific period without re-running the full backtest"""
    try:
        data = json.loads(request.body)
        session_key = data.get('session_key')
        start_date = data.get('start_date')
        end_date = data.get('end_date')
        
        # Retrieve results from cache
        cache_key = f'backtest_results_{session_key}'
        cached_data = cache.get(cache_key)
        
        if not cached_data:
            return JsonResponse({
                'success': False,
                'error': 'Session expired. Please run the backtest again.'
            }, encoder=NumpyJSONEncoder)
        
        # Extract data from cache
        if isinstance(cached_data, dict):
            cached_results = cached_data.get('result_df')
            investment_amount = cached_data.get('investment_amount', 10000)
        else:
            # Backward compatibility if old format
            cached_results = cached_data
            investment_amount = 10000
        
        # Convert JSON back to DataFrame
        result_df = pd.read_json(cached_results, convert_dates=True)
        
        # Ensure timestamp column is datetime
        if 'timestamp' in result_df.columns:
            result_df['timestamp'] = pd.to_datetime(result_df['timestamp'])
        
        # Filter data for the specified period if dates are provided
        if start_date and end_date:
            try:
                # Validate date format and ensure it's YYYY-MM-DD
                from datetime import datetime
                
                # Parse dates with explicit format to avoid ambiguity
                try:
                    # First try ISO format YYYY-MM-DD
                    start_dt = datetime.strptime(start_date, '%Y-%m-%d')
                    end_dt = datetime.strptime(end_date, '%Y-%m-%d')
                except ValueError:
                    # If that fails, return error
                    return JsonResponse({
                        'success': False,
                        'error': 'Invalid date format. Please use YYYY-MM-DD format.'
                    }, encoder=NumpyJSONEncoder)
                
                # Validate date range (1900-2100)
                if start_dt.year < 1900 or start_dt.year > 2100 or end_dt.year < 1900 or end_dt.year > 2100:
                    return JsonResponse({
                        'success': False,
                        'error': 'Date out of valid range. Please use dates between 1900 and 2100.'
                    }, encoder=NumpyJSONEncoder)
                
                # Convert to pandas datetime
                start_date = pd.to_datetime(start_dt)
                end_date = pd.to_datetime(end_dt)
                
                filtered_df = result_df[(result_df['timestamp'] >= start_date) & (result_df['timestamp'] <= end_date)].copy()
                logger.info(f"Filtering data for period: {start_date} to {end_date}, filtered rows: {len(filtered_df)}")
                
            except Exception as e:
                logger.error(f"Error parsing dates: {e}")
                return JsonResponse({
                    'success': False,
                    'error': f'Error parsing dates: {str(e)}'
                }, encoder=NumpyJSONEncoder)
        else:
            # Use full data for overall metrics
            filtered_df = result_df.copy()
            logger.info(f"Using full data for overall metrics, total rows: {len(filtered_df)}")
        
        # Recalculate metrics using the filtered data
        if len(filtered_df) == 0:
            # Return zero metrics if no data in the period
            metrics = {
                'total_market_days': 0,
                'days_in_market': 0,
                'days_in_market_pct': 0.0,
                'num_trades': 0,
                'profitable_trades': 0,
                'loss_trades': 0,
                'win_rate': 0.0,
                'max_profit': 0.0,
                'max_loss': 0.0,
                'avg_profit': 0.0,
                'avg_loss': 0.0,
                'expectancy': 0.0,
                'profit_factor': 0.0,
                'max_profit_streak': 0,
                'max_loss_streak': 0,
                'avg_duration': 0.0,
                'max_duration': 0,
                'min_duration': 0,
                'total_return': 0.0,
                'total_return_pct': 0.0,
                'sharpe_ratio': 0.0,
                'max_drawdown': 0.0,
                'avg_drawdown': 0.0,
                'cagr': 0.0,
                'calmar_ratio': 0.0,
                'avg_calmar': 0.0,
                'total_return_with_divs': 0.0,
                'final_value_with_divs': investment_amount,
                'sharpe_ratio_with_divs': 0.0,
                'cagr_with_divs': 0.0,
                'calmar_ratio_with_divs': 0.0,
                'avg_calmar_with_divs': 0.0
            }
        else:
            # For custom periods, we need to adjust the initial value
            if not start_date and not end_date:
                # Overall period - use original investment amount
                period_investment = investment_amount
            else:
                # Custom period - use portfolio value at start of period
                period_investment = filtered_df.iloc[0]['Portfolio_Value'] if 'Portfolio_Value' in filtered_df.columns else investment_amount
            
            # Calculate metrics using the new function
            metrics = calculate_performance_metrics(filtered_df, period_investment)
            
            # Calculate dividend-inclusive metrics
            dividend_metrics = calculate_dividend_inclusive_metrics(filtered_df, period_investment)
            
            # Calculate dividend yield metrics
            dividend_yield_metrics = calculate_dividend_yield_metrics(filtered_df, period_investment)
            
            # Merge dividend metrics into main metrics dict
            metrics.update(dividend_metrics)
            metrics.update(dividend_yield_metrics)
            
            # Add total_return_pct for compatibility (the function returns total_return as percentage)
            metrics['total_return_pct'] = metrics['total_return']
            
            # Fix max_win_streak and max_loss_streak naming for compatibility
            metrics['max_win_streak'] = metrics.get('max_profit_streak', 0)
            
            # Sanitize metrics to ensure all values are JSON serializable
            # This handles NumPy int64, float64, inf, nan, etc.
            metrics = sanitize_metrics_dict(metrics)
            
            # Round metrics for display after sanitization
            for key in ['days_in_market_pct', 'win_rate', 'avg_duration', 'sharpe_ratio', 'cagr', 'calmar_ratio', 'avg_calmar']:
                if key in metrics:
                    metrics[key] = round(metrics[key], 1) if key in ['days_in_market_pct', 'win_rate', 'avg_duration'] else round(metrics[key], 2)
            
            for key in ['max_profit', 'max_loss', 'avg_profit', 'avg_loss', 'expectancy', 'profit_factor', 'total_return', 'max_drawdown', 'avg_drawdown']:
                if key in metrics and isinstance(metrics[key], (int, float)):
                    metrics[key] = round(metrics[key], 2)
        
        return JsonResponse({
            'success': True,
            'metrics': metrics
        }, encoder=NumpyJSONEncoder)
        
    except Exception as e:
        logger.error(f"Error updating metrics: {str(e)}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, encoder=NumpyJSONEncoder)


@csrf_exempt
@require_http_methods(["POST"])
def download_backtest_excel(request):
    """Download backtest results as Excel file"""
    try:
        # Get session key from POST data
        session_key = request.POST.get('session_key')
        
        if not session_key:
            return JsonResponse({
                'success': False,
                'error': 'No session key provided'
            }, encoder=NumpyJSONEncoder, status=400)
        
        # Get backtest data from cache (session_key is the progress_key)
        backtest_data = cache.get(f'{session_key}_data')
        if not backtest_data:
            return JsonResponse({
                'success': False,
                'error': 'Backtest data not found'
            }, encoder=NumpyJSONEncoder, status=404)
        
        # Get the result DataFrame
        result_df_json = cache.get(f'backtest_result_{session_key}')
        if not result_df_json:
            return JsonResponse({
                'success': False,
                'error': 'Backtest results not found'
            }, encoder=NumpyJSONEncoder, status=404)
        
        # Convert JSON back to DataFrame
        result_df = pd.read_json(result_df_json, orient='split')
        
        # Create a BytesIO object to hold the Excel file
        output = BytesIO()
        
        # Create Excel writer with multiple sheets
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            # Write main results to first sheet
            result_df.to_excel(writer, sheet_name='Backtest Results', index=False)
            
            # Calculate and add summary statistics sheet
            summary_data = {
                'Metric': [],
                'Value': []
            }
            
            # Calculate key metrics
            if 'Portfolio_Value' in result_df.columns:
                # Initial and final values
                initial_value = backtest_data.get('investment_amount', 10000)
                final_value = result_df['Portfolio_Value'].iloc[-1]
                
                # Returns
                total_return = ((final_value - initial_value) / initial_value) * 100
                
                # Win/Loss metrics
                if 'Win' in result_df.columns:
                    total_trades = len(result_df[result_df['Win'].notna()])
                    winning_trades = len(result_df[result_df['Win'] == 1])
                    losing_trades = len(result_df[result_df['Win'] == 0])
                    win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0
                else:
                    total_trades = winning_trades = losing_trades = win_rate = 0
                
                # Add metrics to summary
                summary_data['Metric'].extend([
                    'Initial Investment',
                    'Final Portfolio Value',
                    'Total Return (%)',
                    'Total Trades',
                    'Winning Trades',
                    'Losing Trades',
                    'Win Rate (%)',
                    'Ticker',
                    'Data Frequency',
                    'Start Date',
                    'End Date'
                ])
                
                summary_data['Value'].extend([
                    f"${initial_value:,.2f}",
                    f"${final_value:,.2f}",
                    f"{total_return:.2f}%",
                    total_trades,
                    winning_trades,
                    losing_trades,
                    f"{win_rate:.2f}%",
                    backtest_data.get('ticker', 'N/A'),
                    backtest_data.get('frequency', 'N/A'),
                    result_df['timestamp'].iloc[0] if 'timestamp' in result_df.columns else 'N/A',
                    result_df['timestamp'].iloc[-1] if 'timestamp' in result_df.columns else 'N/A'
                ])
            
            # Create summary DataFrame and write to Excel
            summary_df = pd.DataFrame(summary_data)
            summary_df.to_excel(writer, sheet_name='Summary', index=False)
            
            # Add strategy parameters sheet
            params_data = {
                'Parameter': [
                    'VIX Upper Threshold',
                    'VIX Lower Threshold',
                    'VVIX Upper Threshold',
                    'VVIX Lower Threshold',
                    'Investment Amount'
                ],
                'Value': [
                    backtest_data.get('vix_upper', 'N/A'),
                    backtest_data.get('vix_lower', 'N/A'),
                    backtest_data.get('vvix_upper', 'N/A'),
                    backtest_data.get('vvix_lower', 'N/A'),
                    f"${backtest_data.get('investment_amount', 10000):,.2f}"
                ]
            }
            params_df = pd.DataFrame(params_data)
            params_df.to_excel(writer, sheet_name='Strategy Parameters', index=False)
        
        # Get the Excel file content
        output.seek(0)
        excel_data = output.getvalue()
        
        # Create response with Excel file
        response = HttpResponse(
            excel_data,
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        
        # Set filename with ticker and timestamp
        ticker = backtest_data.get('ticker', 'Unknown')
        timestamp = pd.Timestamp.now().strftime('%Y%m%d_%H%M%S')
        filename = f'{ticker}_backtest_results_{timestamp}.xlsx'
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        
        return response
        
    except Exception as e:
        logger.error(f"Error generating Excel file: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': f'Error generating Excel file: {str(e)}'
        }, encoder=NumpyJSONEncoder, status=500)