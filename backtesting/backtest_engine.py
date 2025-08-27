import pandas as pd
import numpy as np
import logging
from django.core.cache import cache
from django.db import transaction

logger = logging.getLogger(__name__)


def vix_backtest(df, asset_name, VIX_Lower_Bound, VIX_Upper_Bound, VVIX_Lower_Bound, VVIX_Upper_Bound, Investment_Amount, progress_key=None):
    """
    Backtests a VIX-based trading strategy.
    
    Parameters:
    - df: DataFrame with columns {asset_name}_Open, {asset_name}_High, {asset_name}_Low, {asset_name}_Close,
          VIX_Open, VIX_High, VIX_Low, VIX_Close, VVIX_Open, VVIX_High, VVIX_Low, VVIX_Close
    - asset_name: String name of the asset (e.g., 'MSTY', 'QQQ')
    - VIX_Lower_Bound: Lower bound for VIX
    - VIX_Upper_Bound: Upper bound for VIX
    - VVIX_Lower_Bound: Lower bound for VVIX
    - VVIX_Upper_Bound: Upper bound for VVIX
    - Investment_Amount: Initial investment amount
    
    Returns:
    - DataFrame with all backtest results columns
    """
    
    # Create a copy to avoid modifying original
    result_df = df.copy()
    
    # Initialize result columns
    n_rows = len(df)
    result_df['Signal'] = False
    result_df['Entry_Marker'] = False
    result_df['Entry_Signal'] = False
    result_df['In_Position'] = False
    result_df['Exit_type'] = ''
    result_df['Entry_Price'] = ''
    result_df['Exit_Price'] = ''
    result_df['TRADE_ID'] = ''
    result_df['Shares'] = ''
    result_df['Portfolio_Value'] = Investment_Amount  # Initialize all with investment amount
    result_df['Dividends_Paid'] = 0.0  # New column for current period dividends
    result_df['Portfolio_Value_with_Dividends'] = Investment_Amount  # New column for portfolio including dividends
    result_df['Daily_return_%'] = ''
    result_df['Cumulative_Return_%'] = ''
    result_df['DD_per_Trade_%'] = 0.0
    result_df['DD_Overall_%'] = 0.0
    
    # Get asset column names
    asset_open = f'{asset_name}_Open'
    asset_high = f'{asset_name}_High'
    asset_low = f'{asset_name}_Low'
    asset_close = f'{asset_name}_Close'
    asset_dividends = f'{asset_name}_Dividends'
    
    # Calculate signals for all rows - Check ALL FOUR prices (Open, High, Low, Close)
    result_df['Signal'] = (
        # VIX Open within bounds
        (result_df['VIX_Open'] <= VIX_Upper_Bound) & 
        (result_df['VIX_Open'] >= VIX_Lower_Bound) &
        # VIX High within bounds
        (result_df['VIX_High'] <= VIX_Upper_Bound) & 
        (result_df['VIX_High'] >= VIX_Lower_Bound) &
        # VIX Low within bounds
        (result_df['VIX_Low'] <= VIX_Upper_Bound) & 
        (result_df['VIX_Low'] >= VIX_Lower_Bound) &
        # VIX Close within bounds
        (result_df['VIX_Close'] <= VIX_Upper_Bound) &
        (result_df['VIX_Close'] >= VIX_Lower_Bound) &
        # VVIX Open within bounds
        (result_df['VVIX_Open'] <= VVIX_Upper_Bound) & 
        (result_df['VVIX_Open'] >= VVIX_Lower_Bound) &
        # VVIX High within bounds
        (result_df['VVIX_High'] <= VVIX_Upper_Bound) & 
        (result_df['VVIX_High'] >= VVIX_Lower_Bound) &
        # VVIX Low within bounds
        (result_df['VVIX_Low'] <= VVIX_Upper_Bound) & 
        (result_df['VVIX_Low'] >= VVIX_Lower_Bound) &
        # VVIX Close within bounds
        (result_df['VVIX_Close'] <= VVIX_Upper_Bound) &
        (result_df['VVIX_Close'] >= VVIX_Lower_Bound)
    )
    
    # Initialize first row portfolio value
    result_df.loc[0, 'Portfolio_Value'] = Investment_Amount
    result_df.loc[0, 'Portfolio_Value_with_Dividends'] = Investment_Amount
    current_trade_id = 0
    cumulative_dividends = 0.0  # Track total dividends received
    
    # Initialize progress tracking using database model
    progress_obj = None
    if progress_key:
        from backtesting.models import BacktestProgress
        try:
            progress_obj = BacktestProgress.objects.get(progress_key=progress_key)
            progress_obj.current = 0
            progress_obj.total = n_rows
            progress_obj.percentage = 0
            progress_obj.status = 'Processing data...'
            progress_obj.save()
            logger.info(f"Using existing progress object for key: {progress_key}")
        except BacktestProgress.DoesNotExist:
            logger.warning(f"Progress object not found for key: {progress_key}")
            # Continue without progress tracking
            progress_obj = None
    
    
    # Process each row
    for i in range(n_rows):
        # Update progress with adaptive frequency based on total rows
        update_frequency = max(1, n_rows // 100)  # Update roughly 100 times regardless of dataset size
        if progress_obj and (i % update_frequency == 0 or i == n_rows - 1):
            percentage = min(99, int((i / n_rows) * 100))  # Cap at 99% until fully complete
            progress_obj.current = i
            progress_obj.total = n_rows
            progress_obj.percentage = percentage
            progress_obj.status = f'Processing row {i} of {n_rows}...'
            progress_obj.save(update_fields=['current', 'total', 'percentage', 'status', 'updated_at'])
            logger.info(f"Progress update: {percentage}% - Row {i}/{n_rows}")
        # Entry Marker - looks back one row at Signal
        if i > 0:
            result_df.loc[i, 'Entry_Marker'] = result_df.loc[i-1, 'Signal']
        else:
            result_df.loc[i, 'Entry_Marker'] = False
        
        # Entry Signal - TRUE only for the FIRST TRUE in each group of Entry Markers
        if i == 0:
            result_df.loc[i, 'Entry_Signal'] = result_df.loc[i, 'Entry_Marker']
        else:
            # Only TRUE if Entry_Marker is TRUE AND we're not already in position
            if result_df.loc[i, 'Entry_Marker'] and not result_df.loc[i-1, 'In_Position']:
                result_df.loc[i, 'Entry_Signal'] = True
            else:
                result_df.loc[i, 'Entry_Signal'] = False
        
        # In Position - Excel: =IF(Q9=TRUE, TRUE, IF(AND(R8=TRUE, O8=TRUE), TRUE, FALSE))
        if i == 0:
            result_df.loc[i, 'In_Position'] = result_df.loc[i, 'Entry_Signal']
        else:
            if result_df.loc[i, 'Entry_Signal']:
                result_df.loc[i, 'In_Position'] = True
            elif result_df.loc[i-1, 'In_Position'] and result_df.loc[i-1, 'Signal']:
                result_df.loc[i, 'In_Position'] = True
            else:
                result_df.loc[i, 'In_Position'] = False
        
        # Exit type - Only when transitioning from Signal=TRUE to Signal=FALSE
        if i > 0 and not result_df.loc[i, 'Signal'] and result_df.loc[i-1, 'Signal']:
            # Check Open prices first
            if (result_df.loc[i, 'VIX_Open'] > VIX_Upper_Bound or 
                result_df.loc[i, 'VIX_Open'] < VIX_Lower_Bound or
                result_df.loc[i, 'VVIX_Open'] > VVIX_Upper_Bound or 
                result_df.loc[i, 'VVIX_Open'] < VVIX_Lower_Bound):
                result_df.loc[i, 'Exit_type'] = 'Exit at Open'
            # Check High prices
            elif (result_df.loc[i, 'VIX_High'] > VIX_Upper_Bound or 
                  result_df.loc[i, 'VIX_High'] < VIX_Lower_Bound or
                  result_df.loc[i, 'VVIX_High'] > VVIX_Upper_Bound or 
                  result_df.loc[i, 'VVIX_High'] < VVIX_Lower_Bound):
                result_df.loc[i, 'Exit_type'] = 'Exit at High'
            # Check Low prices
            elif (result_df.loc[i, 'VIX_Low'] > VIX_Upper_Bound or 
                  result_df.loc[i, 'VIX_Low'] < VIX_Lower_Bound or
                  result_df.loc[i, 'VVIX_Low'] > VVIX_Upper_Bound or 
                  result_df.loc[i, 'VVIX_Low'] < VVIX_Lower_Bound):
                result_df.loc[i, 'Exit_type'] = 'Exit at Low'
            # Check Close prices
            elif (result_df.loc[i, 'VIX_Close'] > VIX_Upper_Bound or 
                  result_df.loc[i, 'VIX_Close'] < VIX_Lower_Bound or
                  result_df.loc[i, 'VVIX_Close'] > VVIX_Upper_Bound or 
                  result_df.loc[i, 'VVIX_Close'] < VVIX_Lower_Bound):
                result_df.loc[i, 'Exit_type'] = 'Exit at Close'
            else:
                result_df.loc[i, 'Exit_type'] = 'Unknown'
        else:
            result_df.loc[i, 'Exit_type'] = ''
        
        # Entry Price - only when Entry Signal is TRUE
        if result_df.loc[i, 'Entry_Signal']:
            result_df.loc[i, 'Entry_Price'] = result_df.loc[i, asset_open]
        else:
            result_df.loc[i, 'Entry_Price'] = ''
        
        # Exit Price - based on Exit Type
        exit_type = result_df.loc[i, 'Exit_type']
        if exit_type == 'Exit at Open':
            result_df.loc[i, 'Exit_Price'] = result_df.loc[i, asset_open]
        elif exit_type == 'Exit at High':
            result_df.loc[i, 'Exit_Price'] = result_df.loc[i, asset_high]
        elif exit_type == 'Exit at Low':
            result_df.loc[i, 'Exit_Price'] = result_df.loc[i, asset_low]
        elif exit_type == 'Exit at Close':
            result_df.loc[i, 'Exit_Price'] = result_df.loc[i, asset_close]
        else:
            result_df.loc[i, 'Exit_Price'] = ''
        
        # Trade ID - Excel: =IF($R9=TRUE, IF($R8=TRUE, V8, MAX($V$7:V8)+1), "")
        if result_df.loc[i, 'In_Position']:
            if i == 0:
                current_trade_id = 1
                result_df.loc[i, 'TRADE_ID'] = current_trade_id
            else:
                if result_df.loc[i-1, 'In_Position']:
                    # Continue same trade
                    result_df.loc[i, 'TRADE_ID'] = result_df.loc[i-1, 'TRADE_ID']
                else:
                    # New trade
                    current_trade_id += 1
                    result_df.loc[i, 'TRADE_ID'] = current_trade_id
        else:
            result_df.loc[i, 'TRADE_ID'] = ''
        
        # Shares - Excel: =IF(V9="","", IF(V9<>V8, IF(V9=1, $X$8 / T9, X8 / T9), W8))
        if result_df.loc[i, 'TRADE_ID'] == '':
            result_df.loc[i, 'Shares'] = ''
        else:
            if i == 0 or result_df.loc[i, 'TRADE_ID'] != result_df.loc[i-1, 'TRADE_ID']:
                # New trade - calculate shares
                if result_df.loc[i, 'TRADE_ID'] == 1:
                    # First trade uses initial investment
                    result_df.loc[i, 'Shares'] = Investment_Amount / result_df.loc[i, 'Entry_Price']
                else:
                    # Subsequent trades use previous portfolio value WITH dividends
                    result_df.loc[i, 'Shares'] = result_df.loc[i-1, 'Portfolio_Value_with_Dividends'] / result_df.loc[i, 'Entry_Price']
            else:
                # Continue with same shares
                result_df.loc[i, 'Shares'] = result_df.loc[i-1, 'Shares']
        
        # Calculate dividends for this period
        dividend_payment = 0
        if result_df.loc[i, 'In_Position'] and result_df.loc[i, 'Shares'] != '':
            shares = result_df.loc[i, 'Shares']
            if isinstance(shares, (int, float)) and shares > 0:
                if f'{asset_name}_Dividends' in result_df.columns:
                    if pd.notna(result_df.loc[i, asset_dividends]) and result_df.loc[i, asset_dividends] > 0:
                        dividend_payment = shares * result_df.loc[i, asset_dividends]
                        cumulative_dividends += dividend_payment
        
        result_df.loc[i, 'Dividends_Paid'] = dividend_payment
        
        # Portfolio Value - Now WITHOUT dividends (just shares * price)
        if result_df.loc[i, 'Exit_Price'] != '':
            # Exit day - use exit price
            result_df.loc[i, 'Portfolio_Value'] = result_df.loc[i, 'Shares'] * result_df.loc[i, 'Exit_Price']
        elif result_df.loc[i, 'In_Position']:
            # In position - mark to market at close (NO DIVIDENDS)
            shares = result_df.loc[i, 'Shares']
            if isinstance(shares, (int, float)) and shares > 0:
                # Portfolio value = shares * close price ONLY
                result_df.loc[i, 'Portfolio_Value'] = shares * result_df.loc[i, asset_close]
            else:
                result_df.loc[i, 'Portfolio_Value'] = result_df.loc[i-1, 'Portfolio_Value'] if i > 0 else Investment_Amount
        else:
            # Not in position - maintain previous portfolio value
            if i == 0:
                result_df.loc[i, 'Portfolio_Value'] = Investment_Amount
            else:
                result_df.loc[i, 'Portfolio_Value'] = result_df.loc[i-1, 'Portfolio_Value']
        
        # Portfolio_Value_with_Dividends = Portfolio_Value + cumulative dividends
        result_df.loc[i, 'Portfolio_Value_with_Dividends'] = result_df.loc[i, 'Portfolio_Value'] + cumulative_dividends
    
    # Calculate return metrics
    for i in range(n_rows):
        # Daily return % - Excel: =IF(X9="", "", (X9 / X8 - 1))
        if i == 0:
            result_df.loc[i, 'Daily_return_%'] = 0.0
        else:
            result_df.loc[i, 'Daily_return_%'] = (result_df.loc[i, 'Portfolio_Value'] / result_df.loc[i-1, 'Portfolio_Value'] - 1) * 100
        
        # Cumulative Return % - Excel: =IF(X9="", "", (X9 / $X$8 - 1))
        result_df.loc[i, 'Cumulative_Return_%'] = (result_df.loc[i, 'Portfolio_Value'] / Investment_Amount - 1) * 100
        
        # DD per Trade % - Excel: =IF(OR(V9="", W9=0), 0, (X9 / MAX(FILTER($X$8:X9, $V$8:V9=V9)) - 1))
        if result_df.loc[i, 'TRADE_ID'] == '' or result_df.loc[i, 'Shares'] == '' or result_df.loc[i, 'Shares'] == 0:
            result_df.loc[i, 'DD_per_Trade_%'] = 0
        else:
            trade_id = result_df.loc[i, 'TRADE_ID']
            # Find max portfolio value for this trade up to current row
            trade_values = []
            for j in range(i+1):
                if result_df.loc[j, 'TRADE_ID'] == trade_id:
                    trade_values.append(result_df.loc[j, 'Portfolio_Value'])
            if trade_values:
                max_value_in_trade = max(trade_values)
                result_df.loc[i, 'DD_per_Trade_%'] = (result_df.loc[i, 'Portfolio_Value'] / max_value_in_trade - 1) * 100
            else:
                result_df.loc[i, 'DD_per_Trade_%'] = 0
        
        # DD Overall % - Excel: =(MAX($X$9:X9) - X9) / MAX($X$9:X9)
        if i == 0:
            result_df.loc[i, 'DD_Overall_%'] = 0
        else:
            max_portfolio_value = result_df.loc[:i, 'Portfolio_Value'].max()
            if max_portfolio_value > 0:
                result_df.loc[i, 'DD_Overall_%'] = ((max_portfolio_value - result_df.loc[i, 'Portfolio_Value']) / max_portfolio_value) * 100
            else:
                result_df.loc[i, 'DD_Overall_%'] = 0
    
    # Handle open positions at the end of the backtest period
    # Check if the last row is still in position
    if n_rows > 0 and result_df.iloc[-1]['In_Position']:
        last_idx = n_rows - 1
        
        # Mark a virtual exit at the end of the period
        result_df.loc[last_idx, 'Exit_type'] = 'End of Period (Open)'
        result_df.loc[last_idx, 'Exit_Price'] = result_df.loc[last_idx, asset_close]
        
        # Log this for debugging
        logger.info(f"Position still open at end of backtest. Virtual exit at {result_df.loc[last_idx, asset_close]}")
    
    # Format the output columns to include all original data columns plus the calculated columns
    # Get all original columns from the input dataframe
    original_columns = [col for col in result_df.columns]
    
    # Ensure we include all required columns
    output_columns = list(dict.fromkeys(original_columns))  # Remove duplicates while preserving order
    
    # Mark progress as complete
    if progress_obj:
        progress_obj.current = n_rows
        progress_obj.total = n_rows
        progress_obj.percentage = 100
        progress_obj.status = 'Backtest complete!'
        progress_obj.save(update_fields=['current', 'total', 'percentage', 'status', 'updated_at'])
    
    return result_df[output_columns]


def vix_tsl_backtest(df, asset_name, VIX_Lower_Bound, VIX_Upper_Bound, VVIX_Lower_Bound, VVIX_Upper_Bound, 
                     Investment_Amount, TSL_Percentage, Wait_Period, Ignore_Low=False, progress_key=None):
    """
    Complete VIX backtest with Trailing Stop Loss logic.
    
    Parameters:
    - df: DataFrame with price and VIX data
    - asset_name: String name of the asset (e.g., 'MSTY', 'QQQ')
    - VIX_Lower_Bound, VIX_Upper_Bound: VIX bounds
    - VVIX_Lower_Bound, VVIX_Upper_Bound: VVIX bounds
    - Investment_Amount: Initial investment amount
    - TSL_Percentage: Trailing stop loss percentage (e.g., 0.02 for 2%)
    - Wait_Period: Days to wait after TSL hit before re-entering
    - Ignore_Low: If True, only check Close for TSL breach; if False, check both Low and Close
    - progress_key: Optional key for progress tracking
    
    Returns:
    - DataFrame with complete backtest results including TSL
    """
    
    # Create a copy
    result_df = df.copy()
    
    # Get asset column names
    asset_open = f'{asset_name}_Open'
    asset_high = f'{asset_name}_High'
    asset_low = f'{asset_name}_Low'
    asset_close = f'{asset_name}_Close'
    asset_dividends = f'{asset_name}_Dividends'
    
    # Initialize columns
    n_rows = len(df)
    result_df['Signal'] = False
    result_df['Entry_Marker'] = False
    result_df['TRADE_SESSION_ID'] = ''
    result_df['Peak_Price'] = np.nan
    result_df['TSL_Price'] = np.nan
    result_df['TSL_Hit'] = False
    result_df['Wait_Counter'] = ''
    result_df['Entry_Signal'] = False
    result_df['In_Position'] = False
    result_df['Exit_type'] = ''
    result_df['Entry_Price'] = ''
    result_df['Exit_Price'] = ''
    result_df['TRADE_ID'] = ''
    result_df['Shares'] = ''
    result_df['Portfolio_Value'] = Investment_Amount
    result_df['Dividends_Paid'] = 0.0  # New column for current period dividends
    result_df['Portfolio_Value_with_Dividends'] = Investment_Amount  # New column for portfolio including dividends
    result_df['Daily_return_%'] = ''
    result_df['Cumulative_Return_%'] = ''
    result_df['DD_per_Trade_%'] = 0.0
    result_df['DD_Overall_%'] = 0.0
    
    # Initialize progress tracking using database model
    progress_obj = None
    if progress_key:
        from backtesting.models import BacktestProgress
        try:
            progress_obj = BacktestProgress.objects.get(progress_key=progress_key)
            progress_obj.current = 0
            progress_obj.total = n_rows
            progress_obj.percentage = 0
            progress_obj.status = 'Processing data...'
            progress_obj.save()
            logger.info(f"Using existing progress object for key: {progress_key}")
        except BacktestProgress.DoesNotExist:
            logger.warning(f"Progress object not found for key: {progress_key}")
            # Continue without progress tracking
            progress_obj = None
    
    # Calculate Signal (checking all four prices)
    result_df['Signal'] = (
        # VIX bounds check
        (result_df['VIX_Open'] <= VIX_Upper_Bound) & 
        (result_df['VIX_Open'] >= VIX_Lower_Bound) &
        (result_df['VIX_High'] <= VIX_Upper_Bound) & 
        (result_df['VIX_High'] >= VIX_Lower_Bound) &
        (result_df['VIX_Low'] <= VIX_Upper_Bound) & 
        (result_df['VIX_Low'] >= VIX_Lower_Bound) &
        (result_df['VIX_Close'] <= VIX_Upper_Bound) &
        (result_df['VIX_Close'] >= VIX_Lower_Bound) &
        # VVIX bounds check
        (result_df['VVIX_Open'] <= VVIX_Upper_Bound) & 
        (result_df['VVIX_Open'] >= VVIX_Lower_Bound) &
        (result_df['VVIX_High'] <= VVIX_Upper_Bound) & 
        (result_df['VVIX_High'] >= VVIX_Lower_Bound) &
        (result_df['VVIX_Low'] <= VVIX_Upper_Bound) & 
        (result_df['VVIX_Low'] >= VVIX_Lower_Bound) &
        (result_df['VVIX_Close'] <= VVIX_Upper_Bound) &
        (result_df['VVIX_Close'] >= VVIX_Lower_Bound)
    )
    
    # Calculate Entry Marker (lagged Signal)
    for i in range(n_rows):
        if i > 0:
            result_df.loc[i, 'Entry_Marker'] = result_df.loc[i-1, 'Signal']
        else:
            result_df.loc[i, 'Entry_Marker'] = False
    
    # Calculate TRADE SESSION ID
    current_session_id = 0
    for i in range(n_rows):
        if not result_df.loc[i, 'Entry_Marker']:
            result_df.loc[i, 'TRADE_SESSION_ID'] = ''
        else:
            if i == 0 or not result_df.loc[i-1, 'Entry_Marker']:
                # New session starts
                current_session_id += 1
            result_df.loc[i, 'TRADE_SESSION_ID'] = current_session_id
    
    # Initialize trade counter and dividend tracking
    current_trade_id = 0
    cumulative_dividends = 0.0  # Track total dividends received
    
    # Process each row for complete backtest
    for i in range(n_rows):
        # Update progress with adaptive frequency based on total rows
        update_frequency = max(1, n_rows // 100)  # Update roughly 100 times regardless of dataset size
        if progress_obj and (i % update_frequency == 0 or i == n_rows - 1):
            percentage = min(99, int((i / n_rows) * 100))  # Cap at 99% until fully complete
            progress_obj.current = i
            progress_obj.total = n_rows
            progress_obj.percentage = percentage
            progress_obj.status = f'Processing row {i} of {n_rows}...'
            progress_obj.save(update_fields=['current', 'total', 'percentage', 'status', 'updated_at'])
            logger.info(f"Progress update: {percentage}% - Row {i}/{n_rows}")
            
        # First, check if we need to continue counting from yesterday
        if i > 0 and result_df.loc[i-1, 'Wait_Counter'] != '' and result_df.loc[i, 'TRADE_SESSION_ID'] != '':
            # Only continue counting if still in session
            prev_count = int(result_df.loc[i-1, 'Wait_Counter'])
            if prev_count < Wait_Period:
                # Continue counting
                result_df.loc[i, 'Wait_Counter'] = prev_count + 1
            else:
                # Reached wait period, ready to trade again
                result_df.loc[i, 'Wait_Counter'] = ''
        else:
            # Default: not waiting (either not in session or no previous wait)
            result_df.loc[i, 'Wait_Counter'] = ''
        
        # Check if we're in active trading session and not in wait period
        in_session = result_df.loc[i, 'TRADE_SESSION_ID'] != ''
        in_wait = result_df.loc[i, 'Wait_Counter'] != ''
        
        # Entry Signal - now includes re-entry after wait period
        # But first check if entry would be valid (VIX/VVIX at open within bounds)
        can_enter_at_open = True
        if in_session:
            # Check if VIX/VVIX at open are within bounds
            if (result_df.loc[i, 'VIX_Open'] > VIX_Upper_Bound or 
                result_df.loc[i, 'VIX_Open'] < VIX_Lower_Bound or
                result_df.loc[i, 'VVIX_Open'] > VVIX_Upper_Bound or 
                result_df.loc[i, 'VVIX_Open'] < VVIX_Lower_Bound):
                can_enter_at_open = False
        
        if i == 0:
            result_df.loc[i, 'Entry_Signal'] = result_df.loc[i, 'Entry_Marker'] and not in_wait and can_enter_at_open
        else:
            # Entry signal if:
            # 1. Entry marker is true AND not already in position AND not waiting AND can enter at open
            # 2. OR re-entering after wait period ends (was waiting yesterday, not waiting today, still in session) AND can enter at open
            if result_df.loc[i, 'Entry_Marker'] and not result_df.loc[i-1, 'In_Position'] and not in_wait and can_enter_at_open:
                result_df.loc[i, 'Entry_Signal'] = True
            elif (i > 0 and result_df.loc[i-1, 'Wait_Counter'] != '' and 
                  result_df.loc[i, 'Wait_Counter'] == '' and in_session and can_enter_at_open):
                # Re-entry after wait period
                result_df.loc[i, 'Entry_Signal'] = True
            else:
                result_df.loc[i, 'Entry_Signal'] = False
        
        # In Position
        if i == 0:
            result_df.loc[i, 'In_Position'] = result_df.loc[i, 'Entry_Signal']
        else:
            if result_df.loc[i, 'Entry_Signal']:
                result_df.loc[i, 'In_Position'] = True
            elif result_df.loc[i-1, 'In_Position'] and in_session and not in_wait:
                # Stay in position if in session and not stopped out
                result_df.loc[i, 'In_Position'] = True
            else:
                result_df.loc[i, 'In_Position'] = False
        
        # Calculate Peak Price
        # Only calculate if in position AND no VIX exit on entry day
        should_calculate_peak = False
        if result_df.loc[i, 'In_Position']:
            # Check if this is entry day with VIX exit
            if result_df.loc[i, 'Entry_Signal'] and result_df.loc[i, 'Exit_type'] in ['Exit at High', 'Exit at Low', 'Exit at Close']:
                # Don't calculate peak if exiting on entry day
                should_calculate_peak = False
            else:
                should_calculate_peak = True
        
        if should_calculate_peak:
            # Get highest of Open, High, Close for today
            # For dividend-adjusted peak, use close + dividend if dividend exists
            if f'{asset_name}_Dividends' in result_df.columns and pd.notna(result_df.loc[i, asset_dividends]) and result_df.loc[i, asset_dividends] > 0:
                adjusted_close = result_df.loc[i, asset_close] + result_df.loc[i, asset_dividends]
                today_max = max(result_df.loc[i, asset_open], 
                               result_df.loc[i, asset_high], 
                               adjusted_close)
            else:
                today_max = max(result_df.loc[i, asset_open], 
                               result_df.loc[i, asset_high], 
                               result_df.loc[i, asset_close])
            
            if result_df.loc[i, 'Entry_Signal']:
                # First day of new trade (either new session or re-entry)
                result_df.loc[i, 'Peak_Price'] = today_max
            elif i > 0 and not pd.isna(result_df.loc[i-1, 'Peak_Price']):
                # Continue trade - take max of previous peak and today's max
                result_df.loc[i, 'Peak_Price'] = max(result_df.loc[i-1, 'Peak_Price'], today_max)
            else:
                result_df.loc[i, 'Peak_Price'] = today_max
        else:
            result_df.loc[i, 'Peak_Price'] = np.nan
        
        # Calculate TSL Price
        if not pd.isna(result_df.loc[i, 'Peak_Price']):
            result_df.loc[i, 'TSL_Price'] = result_df.loc[i, 'Peak_Price'] * (1 - TSL_Percentage)
        else:
            result_df.loc[i, 'TSL_Price'] = np.nan
        
        # Check TSL Hit
        if result_df.loc[i, 'In_Position'] and not pd.isna(result_df.loc[i, 'TSL_Price']):
            tsl_hit = False
            
            # Check gap-down at open (compare to yesterday's TSL)
            if i > 0 and not pd.isna(result_df.loc[i-1, 'TSL_Price']):
                if result_df.loc[i, asset_open] < result_df.loc[i-1, 'TSL_Price']:
                    tsl_hit = True
            
            # Check intraday breach (today's prices vs today's TSL)
            if not tsl_hit:
                if Ignore_Low:
                    # Only check Close
                    if result_df.loc[i, asset_close] < result_df.loc[i, 'TSL_Price']:
                        tsl_hit = True
                else:
                    # Check both Low and Close
                    if (result_df.loc[i, asset_low] < result_df.loc[i, 'TSL_Price'] or 
                        result_df.loc[i, asset_close] < result_df.loc[i, 'TSL_Price']):
                        tsl_hit = True
            
            result_df.loc[i, 'TSL_Hit'] = tsl_hit
        else:
            result_df.loc[i, 'TSL_Hit'] = False
        
        # Update Wait Counter AFTER checking TSL Hit
        # If TSL Hit today AND still in session, set counter to 0
        if result_df.loc[i, 'TSL_Hit'] and result_df.loc[i, 'TRADE_SESSION_ID'] != '':
            result_df.loc[i, 'Wait_Counter'] = 0
        
        # Exit type - Check VIX/VVIX exits FIRST, then TSL
        # Special case: Check if we couldn't enter at open (only on potential entry days)
        if (result_df.loc[i, 'Entry_Marker'] and not result_df.loc[i, 'In_Position'] and
            (i == 0 or not result_df.loc[i-1, 'In_Position']) and not in_wait and not can_enter_at_open):
            # Would have entered but VIX/VVIX at open prevented it
            result_df.loc[i, 'Exit_type'] = 'Exit at Open'
        # Check VIX/VVIX exits for active positions
        elif result_df.loc[i, 'In_Position']:
            # Check for VIX/VVIX breaches
            vix_exit = False
            vix_exit_type = ''
            
            # For entry day, check if High/Low/Close breach bounds
            if result_df.loc[i, 'Entry_Signal']:
                # Entry day - check High first
                if (result_df.loc[i, 'VIX_High'] > VIX_Upper_Bound or 
                    result_df.loc[i, 'VIX_High'] < VIX_Lower_Bound or
                    result_df.loc[i, 'VVIX_High'] > VVIX_Upper_Bound or 
                    result_df.loc[i, 'VVIX_High'] < VVIX_Lower_Bound):
                    vix_exit = True
                    vix_exit_type = 'Exit at High'
                # Check Low
                elif (result_df.loc[i, 'VIX_Low'] > VIX_Upper_Bound or 
                      result_df.loc[i, 'VIX_Low'] < VIX_Lower_Bound or
                      result_df.loc[i, 'VVIX_Low'] > VVIX_Upper_Bound or 
                      result_df.loc[i, 'VVIX_Low'] < VVIX_Lower_Bound):
                    vix_exit = True
                    vix_exit_type = 'Exit at Low'
                # Check Close
                elif (result_df.loc[i, 'VIX_Close'] > VIX_Upper_Bound or 
                      result_df.loc[i, 'VIX_Close'] < VIX_Lower_Bound or
                      result_df.loc[i, 'VVIX_Close'] > VVIX_Upper_Bound or 
                      result_df.loc[i, 'VVIX_Close'] < VVIX_Lower_Bound):
                    vix_exit = True
                    vix_exit_type = 'Exit at Close'
            # For non-entry days, check normal signal transition
            elif i > 0 and not result_df.loc[i, 'Signal'] and result_df.loc[i-1, 'Signal']:
                # Regular VIX breach exits
                if (result_df.loc[i, 'VIX_Open'] > VIX_Upper_Bound or 
                    result_df.loc[i, 'VIX_Open'] < VIX_Lower_Bound or
                    result_df.loc[i, 'VVIX_Open'] > VVIX_Upper_Bound or 
                    result_df.loc[i, 'VVIX_Open'] < VVIX_Lower_Bound):
                    vix_exit = True
                    vix_exit_type = 'Exit at Open'
                elif (result_df.loc[i, 'VIX_High'] > VIX_Upper_Bound or 
                      result_df.loc[i, 'VIX_High'] < VIX_Lower_Bound or
                      result_df.loc[i, 'VVIX_High'] > VVIX_Upper_Bound or 
                      result_df.loc[i, 'VVIX_High'] < VVIX_Lower_Bound):
                    vix_exit = True
                    vix_exit_type = 'Exit at High'
                elif (result_df.loc[i, 'VIX_Low'] > VIX_Upper_Bound or 
                      result_df.loc[i, 'VIX_Low'] < VIX_Lower_Bound or
                      result_df.loc[i, 'VVIX_Low'] > VVIX_Upper_Bound or 
                      result_df.loc[i, 'VVIX_Low'] < VVIX_Lower_Bound):
                    vix_exit = True
                    vix_exit_type = 'Exit at Low'
                elif (result_df.loc[i, 'VIX_Close'] > VIX_Upper_Bound or 
                      result_df.loc[i, 'VIX_Close'] < VIX_Lower_Bound or
                      result_df.loc[i, 'VVIX_Close'] > VVIX_Upper_Bound or 
                      result_df.loc[i, 'VVIX_Close'] < VVIX_Lower_Bound):
                    vix_exit = True
                    vix_exit_type = 'Exit at Close'
            
            # Set exit type based on priority
            if vix_exit:
                result_df.loc[i, 'Exit_type'] = vix_exit_type
            elif result_df.loc[i, 'TSL_Hit']:
                result_df.loc[i, 'Exit_type'] = 'TSL Exit'
            else:
                result_df.loc[i, 'Exit_type'] = ''
        else:
            result_df.loc[i, 'Exit_type'] = ''
        
        # Entry Price
        if result_df.loc[i, 'Entry_Signal']:
            result_df.loc[i, 'Entry_Price'] = result_df.loc[i, asset_open]
        else:
            result_df.loc[i, 'Entry_Price'] = ''
        
        # Exit Price
        exit_type = result_df.loc[i, 'Exit_type']
        if exit_type == 'TSL Exit':
            # For TSL exits, check if it's a gap-down at open
            if i > 0 and not pd.isna(result_df.loc[i-1, 'TSL_Price']):
                if result_df.loc[i, asset_open] < result_df.loc[i-1, 'TSL_Price']:
                    # Gap down at open - exit at open price
                    result_df.loc[i, 'Exit_Price'] = result_df.loc[i, asset_open]
                else:
                    # Normal TSL exit - use TSL price
                    result_df.loc[i, 'Exit_Price'] = result_df.loc[i, 'TSL_Price']
            else:
                result_df.loc[i, 'Exit_Price'] = result_df.loc[i, 'TSL_Price']
        elif exit_type == 'Exit at Open':
            result_df.loc[i, 'Exit_Price'] = result_df.loc[i, asset_open]
        elif exit_type == 'Exit at High':
            result_df.loc[i, 'Exit_Price'] = result_df.loc[i, asset_high]
        elif exit_type == 'Exit at Low':
            result_df.loc[i, 'Exit_Price'] = result_df.loc[i, asset_low]
        elif exit_type == 'Exit at Close':
            result_df.loc[i, 'Exit_Price'] = result_df.loc[i, asset_close]
        else:
            result_df.loc[i, 'Exit_Price'] = ''
        
        # Trade ID - new logic based on actual trades (entry/exit pairs)
        if result_df.loc[i, 'In_Position']:
            if result_df.loc[i, 'Entry_Signal']:
                # New trade starts
                current_trade_id += 1
                result_df.loc[i, 'TRADE_ID'] = current_trade_id
            elif i > 0 and result_df.loc[i-1, 'In_Position']:
                # Continue same trade
                result_df.loc[i, 'TRADE_ID'] = result_df.loc[i-1, 'TRADE_ID']
            else:
                current_trade_id += 1
                result_df.loc[i, 'TRADE_ID'] = current_trade_id
        else:
            result_df.loc[i, 'TRADE_ID'] = ''
        
        # Shares
        if result_df.loc[i, 'TRADE_ID'] == '':
            result_df.loc[i, 'Shares'] = ''
        else:
            if result_df.loc[i, 'Entry_Signal']:
                # New trade - calculate shares based on current portfolio value WITH DIVIDENDS
                if i == 0:
                    capital = Investment_Amount
                else:
                    capital = result_df.loc[i-1, 'Portfolio_Value_with_Dividends']
                
                entry_price = result_df.loc[i, 'Entry_Price']
                if isinstance(entry_price, (int, float)) and entry_price > 0:
                    result_df.loc[i, 'Shares'] = capital / entry_price
                else:
                    result_df.loc[i, 'Shares'] = 0
            else:
                # Continue with same shares
                if i > 0 and result_df.loc[i-1, 'Shares'] != '':
                    result_df.loc[i, 'Shares'] = result_df.loc[i-1, 'Shares']
                else:
                    result_df.loc[i, 'Shares'] = 0
        
        # Calculate dividends for this period
        dividend_payment = 0
        if result_df.loc[i, 'In_Position'] and result_df.loc[i, 'Shares'] != '':
            shares = result_df.loc[i, 'Shares']
            if isinstance(shares, (int, float)) and shares > 0:
                if f'{asset_name}_Dividends' in result_df.columns:
                    if pd.notna(result_df.loc[i, asset_dividends]) and result_df.loc[i, asset_dividends] > 0:
                        dividend_payment = shares * result_df.loc[i, asset_dividends]
                        cumulative_dividends += dividend_payment
        
        result_df.loc[i, 'Dividends_Paid'] = dividend_payment
        
        # Portfolio Value - Now WITHOUT dividends (just shares * price)
        if result_df.loc[i, 'Exit_Price'] != '':
            # Exit day - use exit price
            shares = result_df.loc[i, 'Shares']
            if isinstance(shares, (int, float)) and shares > 0:
                result_df.loc[i, 'Portfolio_Value'] = shares * result_df.loc[i, 'Exit_Price']
            else:
                # This shouldn't happen, but maintain previous value if it does
                result_df.loc[i, 'Portfolio_Value'] = result_df.loc[i-1, 'Portfolio_Value'] if i > 0 else Investment_Amount
        elif result_df.loc[i, 'In_Position']:
            # In position - mark to market at close (NO DIVIDENDS)
            shares = result_df.loc[i, 'Shares']
            if isinstance(shares, (int, float)) and shares > 0:
                # Portfolio value = shares * close price ONLY
                result_df.loc[i, 'Portfolio_Value'] = shares * result_df.loc[i, asset_close]
            else:
                # This shouldn't happen, but maintain previous value if it does
                result_df.loc[i, 'Portfolio_Value'] = result_df.loc[i-1, 'Portfolio_Value'] if i > 0 else Investment_Amount
        else:
            # Not in position - maintain previous portfolio value
            if i == 0:
                result_df.loc[i, 'Portfolio_Value'] = Investment_Amount
            else:
                result_df.loc[i, 'Portfolio_Value'] = result_df.loc[i-1, 'Portfolio_Value']
        
        # Portfolio_Value_with_Dividends = Portfolio_Value + cumulative dividends
        result_df.loc[i, 'Portfolio_Value_with_Dividends'] = result_df.loc[i, 'Portfolio_Value'] + cumulative_dividends
    
    # Calculate return metrics
    max_portfolio_value_ever = Investment_Amount  # Track all-time high for DD Overall
    
    for i in range(n_rows):
        # Daily return %
        if i == 0:
            result_df.loc[i, 'Daily_return_%'] = 0.0
        else:
            result_df.loc[i, 'Daily_return_%'] = (result_df.loc[i, 'Portfolio_Value'] / result_df.loc[i-1, 'Portfolio_Value'] - 1) * 100
        
        # Cumulative Return %
        result_df.loc[i, 'Cumulative_Return_%'] = (result_df.loc[i, 'Portfolio_Value'] / Investment_Amount - 1) * 100
        
        # Update all-time high portfolio value
        if result_df.loc[i, 'Portfolio_Value'] > max_portfolio_value_ever:
            max_portfolio_value_ever = result_df.loc[i, 'Portfolio_Value']
        
        # DD per Trade % - uses peak within current trade only
        if result_df.loc[i, 'TRADE_ID'] != '' and result_df.loc[i, 'In_Position']:
            trade_id = result_df.loc[i, 'TRADE_ID']
            # Find max portfolio value for THIS SPECIFIC trade only
            trade_values = []
            for j in range(i+1):
                if result_df.loc[j, 'TRADE_ID'] == trade_id:
                    trade_values.append(result_df.loc[j, 'Portfolio_Value'])
            if trade_values:
                max_value_in_trade = max(trade_values)
                result_df.loc[i, 'DD_per_Trade_%'] = (result_df.loc[i, 'Portfolio_Value'] / max_value_in_trade - 1) * 100
            else:
                result_df.loc[i, 'DD_per_Trade_%'] = 0
        else:
            result_df.loc[i, 'DD_per_Trade_%'] = 0
        
        # DD Overall % - uses all-time high (including when not in position)
        result_df.loc[i, 'DD_Overall_%'] = ((max_portfolio_value_ever - result_df.loc[i, 'Portfolio_Value']) / max_portfolio_value_ever) * 100
    
    # Output ALL columns in order
    output_columns = ['timestamp', f'{asset_name}_Open', f'{asset_name}_High', f'{asset_name}_Low', f'{asset_name}_Close',
                     'VIX_Open', 'VIX_High', 'VIX_Low', 'VIX_Close', 
                     'VVIX_Open', 'VVIX_High', 'VVIX_Low', 'VVIX_Close', 
                     'Signal', 'Entry_Marker', 'TRADE_SESSION_ID', 
                     'Peak_Price', 'TSL_Price', 'TSL_Hit', 'Wait_Counter',
                     'Entry_Signal', 'In_Position', 'Exit_type', 'Entry_Price', 
                     'Exit_Price', 'TRADE_ID', 'Shares', 'Portfolio_Value', 
                     'Dividends_Paid', 'Portfolio_Value_with_Dividends',
                     'Daily_return_%', 'Cumulative_Return_%', 'DD_per_Trade_%', 'DD_Overall_%']
    
    # Check if Dividends column exists and add it if present
    if f'{asset_name}_Dividends' in result_df.columns:
        # Insert dividends column after the close price
        close_idx = output_columns.index(f'{asset_name}_Close')
        output_columns.insert(close_idx + 1, f'{asset_name}_Dividends')
    
    # Handle open positions at the end of the backtest period
    # Check if the last row is still in position
    if n_rows > 0 and result_df.iloc[-1]['In_Position']:
        last_idx = n_rows - 1
        
        # Mark a virtual exit at the end of the period
        result_df.loc[last_idx, 'Exit_type'] = 'End of Period (Open)'
        result_df.loc[last_idx, 'Exit_Price'] = result_df.loc[last_idx, asset_close]
        
        # Log this for debugging
        logger.info(f"TSL Strategy: Position still open at end of backtest. Virtual exit at {result_df.loc[last_idx, asset_close]}")
    
    # Mark progress as complete
    if progress_obj:
        progress_obj.current = n_rows
        progress_obj.total = n_rows
        progress_obj.percentage = 100
        progress_obj.status = 'Backtest complete!'
        progress_obj.save(update_fields=['current', 'total', 'percentage', 'status', 'updated_at'])
    
    return result_df[output_columns]

