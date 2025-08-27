# Dividend Tracking Implementation - Django App V4

## Date: 2024-08-24

## Overview
This document captures the implementation of dividend tracking and performance metrics in the Django backtesting application. The work involved fixing how dividends are handled in portfolio calculations and adding a new metrics section for dividend-inclusive performance.

## Problem Statement

### Initial Issues Identified:
1. **Redundant Date Column**: The backtest results had both a `timestamp` column and a duplicate `Date` column with identical values
2. **Lost Dividends**: Portfolio value was correctly adding dividends on the dividend payment date, but immediately losing them the next day because the calculation reverted to just `shares × close price`
3. **Missing Dividend Metrics**: No way to view performance metrics that included dividend income

## Solutions Implemented

### Part 1: Remove Redundant Date Column

#### Files Modified:
- `backtesting/views.py`
- `backtesting/backtest_visualizations.py` 
- `backtesting/backtest_engine.py`

#### Changes Made:
1. Removed creation of duplicate `Date` column (`backtest_df['Date'] = backtest_df['timestamp']`)
2. Updated all references from `'Date'` to `'timestamp'` throughout:
   - Chart generation functions
   - Date filtering logic
   - Table formatting
   - Excel export functions

### Part 2: Implement Proper Dividend Tracking

#### Problem Analysis:
When dividends were paid, they would be added to the portfolio value for that day:
```
Portfolio_Value = shares × close_price + dividend_payment
```

But the next day, the formula would revert to:
```
Portfolio_Value = shares × close_price
```

This caused the dividend income to "disappear" from the portfolio value.

#### Solution Architecture:
Added three new columns to track dividends properly:

1. **`Portfolio_Value`** - Now shows ONLY `shares × close_price` (without dividends)
2. **`Dividends_Paid`** - Shows dividend payment for the current period (`shares × dividend`)
3. **`Portfolio_Value_with_Dividends`** - Shows cumulative portfolio value including all accumulated dividends

#### Implementation Details:

##### In `backtest_engine.py` - Strategy 1 (vix_backtest):
```python
# Added initialization
result_df['Dividends_Paid'] = 0.0
result_df['Portfolio_Value_with_Dividends'] = Investment_Amount
cumulative_dividends = 0.0  # Track total dividends received

# During each period calculation
dividend_payment = 0
if in_position and has_shares:
    if dividend_exists_for_period:
        dividend_payment = shares * dividend_value
        cumulative_dividends += dividend_payment

result_df['Dividends_Paid'] = dividend_payment
result_df['Portfolio_Value'] = shares * close_price  # NO dividends
result_df['Portfolio_Value_with_Dividends'] = Portfolio_Value + cumulative_dividends
```

##### In `backtest_engine.py` - Strategy 2 (vix_tsl_backtest):
- Applied same changes as Strategy 1
- Ensured TSL (Trailing Stop Loss) logic continues to work correctly
- New positions use `Portfolio_Value_with_Dividends` for share calculations

#### Key Points:
- Dividends accumulate permanently in `cumulative_dividends`
- When entering new trades, shares are calculated using `Portfolio_Value_with_Dividends`
- Performance metrics continue using original `Portfolio_Value` for backward compatibility
- Dividends are never "lost" - they persist throughout the backtest

### Part 3: Add Dividend-Inclusive Performance Metrics

#### New Function Created:
`calculate_dividend_inclusive_metrics()` in `backtest_visualizations.py`

Calculates 6 key metrics using `Portfolio_Value_with_Dividends`:
- Total Return (%)
- Final Portfolio Value  
- Sharpe Ratio
- CAGR
- Calmar Ratio
- Average Calmar Ratio

#### Backend Integration (`backtesting/views.py`):
```python
# Calculate regular metrics
metrics = calculate_performance_metrics(result_df, investment_amount)

# Calculate dividend-inclusive metrics
dividend_metrics = calculate_dividend_inclusive_metrics(result_df, investment_amount)

# Merge into main metrics dict
metrics.update(dividend_metrics)
```

#### Frontend Display (`backtesting_section.html`):
Added new section in the `createMetricsCards()` function:
```javascript
<!-- Performance Metrics with Paid Dividends Included -->
<div class="mt-4">
    <h6 class="text-info mb-3" style="border-bottom: 2px solid #dc3545;">
        Performance Metrics with Paid Dividends Included
    </h6>
    <div class="row">
        <!-- 6 metric cards for dividend-inclusive metrics -->
    </div>
</div>
```

#### Features:
- Positioned below main metrics with red underline separator
- Responds to period selection (Overall/Specify Period)
- Same styling as existing metrics
- Color coding: green for positive, red for negative
- Conditional highlighting when thresholds exceeded

## Files Modified Summary

### Backend Files:
1. **`backtesting/backtest_engine.py`**
   - Added dividend tracking columns to both strategies
   - Implemented cumulative dividend tracking
   - Modified portfolio value calculations

2. **`backtesting/backtest_visualizations.py`**
   - Changed all Date references to timestamp
   - Added `calculate_dividend_inclusive_metrics()` function

3. **`backtesting/views.py`**
   - Removed duplicate Date column creation
   - Added dividend metrics calculation
   - Updated date filtering to use timestamp

### Frontend Files:
1. **`backtesting/templates/backtesting/backtesting_section.html`**
   - Added dividend metrics display section
   - Updated to show 6 new metrics with proper formatting

## Testing Performed
- Django configuration check passed
- Verified no syntax errors
- Confirmed period selection works with dividend metrics
- Validated that original metrics remain unchanged

## Impact and Benefits

1. **Accurate Dividend Tracking**: Dividends are now properly accumulated and never lost
2. **True Performance Visibility**: Users can see actual returns including dividend income
3. **Comparison Capability**: Side-by-side view of performance with and without dividends
4. **Period Flexibility**: Both metric sets respond to date range selection
5. **Data Integrity**: Original Portfolio_Value preserved for backward compatibility

## Next Steps for Tomorrow

### Potential Enhancements:
1. Add dividend yield metrics
2. Show total dividends received as a separate metric
3. Add dividend contribution percentage to total return
4. Consider adding dividend reinvestment tracking
5. Add export functionality for dividend metrics

### Testing Needed:
1. Test with various assets that pay different dividend frequencies
2. Verify calculations with manual Excel comparison
3. Test edge cases (no dividends, single dividend, etc.)
4. Performance test with large datasets

## Code Snippets for Quick Reference

### Check if dividends exist:
```python
if f'{asset_name}_Dividends' in result_df.columns:
    if pd.notna(result_df.loc[i, asset_dividends]) and result_df.loc[i, asset_dividends] > 0:
        # Process dividend
```

### Calculate metrics for custom period:
```python
if not start_date and not end_date:
    period_investment = investment_amount  # Overall period
else:
    period_investment = filtered_df.iloc[0]['Portfolio_Value']  # Custom period
```

### Format display values in JavaScript:
```javascript
${metrics.total_return_with_divs ? metrics.total_return_with_divs.toFixed(2) + '%' : '0.00%'}
```

## Session Context
- Working directory: `D:\Benson\aUpWork\Douglas Backtester Algo\Backtester Apps`
- Primary app: Django App V4
- Git status: Changes uncommitted, on main branch
- Python environment: 3.13 tested

## Important Notes
- Portfolio_Value now excludes dividends for clean price tracking
- Portfolio_Value_with_Dividends includes all accumulated dividends
- Metrics use Portfolio_Value to maintain backward compatibility
- New dividend metrics use Portfolio_Value_with_Dividends for accurate total return

---

This implementation ensures dividends are properly tracked, accumulated, and reflected in performance metrics while maintaining backward compatibility with existing systems.