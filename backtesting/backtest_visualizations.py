"""
Backtest Visualization and Metrics Module

This module contains reusable functions for creating charts and calculating
performance metrics for backtesting strategies.
"""

import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.io import to_html
import logging

logger = logging.getLogger(__name__)


def create_portfolio_value_chart(result_df, ticker, strategy_name="Strategy", investment_amount=10000):
    """
    Create a portfolio value chart from backtest results.
    
    Parameters:
    - result_df: DataFrame with timestamp and Portfolio_Value columns
    - ticker: Stock ticker symbol
    - strategy_name: Name of the strategy for the title
    - investment_amount: Initial investment amount
    
    Returns:
    - HTML string of the plotly chart
    """
    fig = go.Figure()
    
    # Check if required columns exist
    if 'timestamp' in result_df.columns and 'Portfolio_Value' in result_df.columns:
        # Add portfolio value line
        fig.add_trace(go.Scatter(
            x=result_df['timestamp'],
            y=result_df['Portfolio_Value'],
            mode='lines',
            name='Portfolio Value',
            line=dict(color='#00ff88', width=2),
            hovertemplate='Date: %{x}<br>Portfolio Value: $%{y:,.2f}<extra></extra>'
        ))
    else:
        logger.error("Required columns (timestamp, Portfolio_Value) not found for chart generation")
        return ""
    
    # Calculate summary statistics
    initial_value = investment_amount
    
    if 'Portfolio_Value' in result_df.columns and len(result_df) > 0:
        final_value = result_df['Portfolio_Value'].iloc[-1]
        total_return = (final_value / initial_value - 1) * 100
    else:
        final_value = initial_value
        total_return = 0.0
        
    # Check if DD_Overall_% exists for max drawdown
    if 'DD_Overall_%' in result_df.columns:
        max_drawdown = result_df['DD_Overall_%'].max()  # max() because drawdowns are now positive
    else:
        max_drawdown = 0.0
    
    # Update layout
    fig.update_layout(
        title=f'{strategy_name} Backtest Results - {ticker}',
        xaxis_title='Date',
        yaxis_title='Portfolio Value ($)',
        template='plotly_dark',
        hovermode='x unified',
        height=600,
        showlegend=False
    )
    
    # Add annotations with summary stats
    fig.add_annotation(
        text=f"Initial: ${initial_value:,.0f}<br>Final: ${final_value:,.2f}<br>Return: {total_return:.2f}%<br>Max DD: {max_drawdown:.2f}%",
        xref="paper", yref="paper",
        x=0.98, y=0.02,
        showarrow=False,
        bgcolor="rgba(0,0,0,0.8)",
        bordercolor="#666",
        borderwidth=1,
        font=dict(size=12, color="white"),
        align="right"
    )
    
    # Convert chart to HTML
    return to_html(fig, include_plotlyjs='cdn', div_id="portfolio-chart")


def create_overall_drawdown_chart(result_df):
    """
    Create an overall drawdown chart from backtest results.
    
    Parameters:
    - result_df: DataFrame with timestamp and DD_Overall_% columns
    
    Returns:
    - HTML string of the plotly chart
    """
    fig = go.Figure()
    
    # Check if required columns exist
    if 'timestamp' in result_df.columns and 'DD_Overall_%' in result_df.columns:
        # Add overall drawdown line
        fig.add_trace(go.Scatter(
            x=result_df['timestamp'],
            y=-result_df['DD_Overall_%'],  # Negate to show drawdowns as negative
            mode='lines',
            name='Overall Drawdown',
            line=dict(color='#ff4444', width=2),
            fill='tozeroy',
            fillcolor='rgba(255, 68, 68, 0.3)',
            hovertemplate='Date: %{x}<br>Drawdown: %{y:.2f}%<extra></extra>'
        ))
        
        # Calculate drawdown statistics (drawdowns are positive in data, so we look for > 0)
        dd_values = result_df[result_df['DD_Overall_%'] > 0]['DD_Overall_%']
        if len(dd_values) > 0:
            dd_max = dd_values.max()
            dd_avg = dd_values.mean()
            dd_25th = dd_values.quantile(0.25)
            dd_75th = dd_values.quantile(0.75)
        else:
            dd_max = dd_avg = dd_25th = dd_75th = 0.0
    else:
        logger.warning("Required columns for Overall Drawdown chart not found")
        dd_max = dd_avg = dd_25th = dd_75th = 0.0
        return ""
    
    # Update layout
    fig.update_layout(
        title='Overall Drawdown',
        xaxis_title='Date',
        yaxis_title='Drawdown (%)',
        template='plotly_dark',
        hovermode='x unified',
        height=400,
        showlegend=False,
        yaxis=dict(
            tickformat='.1f',
            gridcolor='rgba(128, 128, 128, 0.2)',
            zeroline=True,
            zerolinecolor='rgba(255, 255, 255, 0.3)'
        ),
        xaxis=dict(
            gridcolor='rgba(128, 128, 128, 0.2)'
        )
    )
    
    # Add statistics annotation
    fig.add_annotation(
        text=f"<b>Statistics</b><br>Max DD: {dd_max:.2f}%<br>Avg DD: {dd_avg:.2f}%<br>25th Percentile: {dd_25th:.2f}%<br>75th Percentile: {dd_75th:.2f}%",
        xref="paper", yref="paper",
        x=0.98, y=0.02,
        showarrow=False,
        bordercolor="rgba(255, 255, 255, 0.3)",
        borderwidth=1,
        borderpad=10,
        bgcolor="rgba(30, 30, 30, 0.8)",
        font=dict(size=12, color="white"),
        align="left",
        xanchor="right",
        yanchor="bottom"
    )
    
    return to_html(fig, include_plotlyjs=False, div_id="dd-overall-chart")


def create_trade_drawdown_chart(result_df):
    """
    Create a drawdown per trade chart from backtest results.
    
    Parameters:
    - result_df: DataFrame with timestamp, DD_per_Trade_%, and In_Position columns
    
    Returns:
    - HTML string of the plotly chart
    """
    fig = go.Figure()
    
    # Check if required columns exist
    if 'In_Position' in result_df.columns and 'timestamp' in result_df.columns and 'DD_per_Trade_%' in result_df.columns:
        # Filter data to show only rows where we're in position
        in_position_df = result_df[result_df['In_Position'] == True].copy()
        
        if not in_position_df.empty:
            # Add drawdown per trade line with area fill
            fig.add_trace(go.Scatter(
                x=in_position_df['timestamp'],
                y=in_position_df['DD_per_Trade_%'],
                mode='lines',
                name='Drawdown per Trade',
                line=dict(color='#ff8844', width=2),
                fill='tozeroy',
                fillcolor='rgba(255, 136, 68, 0.3)',
                hovertemplate='Date: %{x}<br>Trade DD: %{y:.2f}%<extra></extra>'
            ))
            
            # Calculate per-trade drawdown statistics
            trade_dd_values = in_position_df[in_position_df['DD_per_Trade_%'] < 0]['DD_per_Trade_%']
            if len(trade_dd_values) > 0:
                trade_dd_max = trade_dd_values.min()
                trade_dd_avg = trade_dd_values.mean()
                trade_dd_25th = trade_dd_values.quantile(0.25)
                trade_dd_75th = trade_dd_values.quantile(0.75)
            else:
                trade_dd_max = trade_dd_avg = trade_dd_25th = trade_dd_75th = 0.0
        else:
            trade_dd_max = trade_dd_avg = trade_dd_25th = trade_dd_75th = 0.0
            return ""
    else:
        logger.warning("Required columns for Drawdown per Trade chart not found")
        return ""
    
    # Update layout
    fig.update_layout(
        title='Drawdown per Trade',
        xaxis_title='Date',
        yaxis_title='Drawdown (%)',
        template='plotly_dark',
        hovermode='x unified',
        height=400,
        showlegend=False,
        yaxis=dict(
            tickformat='.1f',
            gridcolor='rgba(128, 128, 128, 0.2)',
            zeroline=True,
            zerolinecolor='rgba(255, 255, 255, 0.3)'
        ),
        xaxis=dict(
            gridcolor='rgba(128, 128, 128, 0.2)'
        )
    )
    
    # Add statistics annotation
    fig.add_annotation(
        text=f"<b>Statistics</b><br>Max DD: {trade_dd_max:.2f}%<br>Avg DD: {trade_dd_avg:.2f}%<br>25th Percentile: {trade_dd_25th:.2f}%<br>75th Percentile: {trade_dd_75th:.2f}%",
        xref="paper", yref="paper",
        x=0.98, y=0.02,
        showarrow=False,
        bordercolor="rgba(255, 255, 255, 0.3)",
        borderwidth=1,
        borderpad=10,
        bgcolor="rgba(30, 30, 30, 0.8)",
        font=dict(size=12, color="white"),
        align="left",
        xanchor="right",
        yanchor="bottom"
    )
    
    return to_html(fig, include_plotlyjs=False, div_id="dd-trade-chart")


def calculate_performance_metrics(result_df, investment_amount=10000):
    """
    Calculate comprehensive performance metrics from backtest results.
    
    Parameters:
    - result_df: DataFrame with backtest results
    - investment_amount: Initial investment amount
    
    Returns:
    - Dictionary of performance metrics
    """
    metrics = {}
    
    # Basic counts
    total_market_days = len(result_df)
    
    # Days in market
    if 'In_Position' in result_df.columns:
        days_in_market = len(result_df[result_df['In_Position'] == True])
    else:
        logger.warning("In_Position column not found")
        days_in_market = 0
    
    days_out_of_market = total_market_days - days_in_market
    
    # Portfolio performance
    initial_value = investment_amount
    if 'Portfolio_Value' in result_df.columns and len(result_df) > 0:
        final_value = result_df['Portfolio_Value'].iloc[-1]
        total_return = (final_value / initial_value - 1) * 100
    else:
        final_value = initial_value
        total_return = 0.0
    
    # Max drawdown (drawdowns are positive in our data)
    if 'DD_Overall_%' in result_df.columns:
        max_drawdown = result_df['DD_Overall_%'].max()
    else:
        max_drawdown = 0.0
    
    # Trade analysis - Initialize ALL variables first
    num_trades = 0
    profitable_trades = loss_trades = 0
    max_profit = max_loss = avg_profit = avg_loss = 0
    expectancy = profit_factor = 0
    max_profit_streak = max_loss_streak = 0
    avg_duration = max_duration = min_duration = 0
    win_rate = 0  # Initialize win_rate here to avoid undefined variable error
    
    if 'TRADE_ID' in result_df.columns:
        # Get valid trade IDs
        all_trade_ids = result_df[result_df['TRADE_ID'] != '']['TRADE_ID'].unique()
        valid_trade_ids = []
        for tid in all_trade_ids:
            try:
                if tid != '' and int(tid) > 0:
                    valid_trade_ids.append(int(tid))
            except (ValueError, TypeError):
                pass
        
        num_trades = len(valid_trade_ids)
        
        if num_trades > 0:
            # Calculate P&L for each trade
            trade_pnl = []
            trade_durations = []
            
            for trade_id in valid_trade_ids:
                trade_data = result_df[result_df['TRADE_ID'] == trade_id]
                if len(trade_data) >= 1:  # Changed from >= 2 to >= 1 to count all trades
                    entry_value = trade_data['Portfolio_Value'].iloc[0]
                    exit_value = trade_data['Portfolio_Value'].iloc[-1]
                    pnl = exit_value - entry_value
                    trade_pnl.append(pnl)
                    trade_durations.append(len(trade_data))
            
            # Trade statistics
            if trade_pnl:
                profitable_trades = sum(1 for pnl in trade_pnl if pnl > 0)
                loss_trades = sum(1 for pnl in trade_pnl if pnl <= 0)
                win_rate = (profitable_trades / num_trades * 100) if num_trades > 0 else 0
                
                max_profit = max(trade_pnl) if trade_pnl else 0
                max_loss = min(trade_pnl) if trade_pnl else 0
                
                profits = [pnl for pnl in trade_pnl if pnl > 0]
                losses = [pnl for pnl in trade_pnl if pnl <= 0]
                
                avg_profit = sum(profits) / len(profits) if profits else 0
                avg_loss = sum(losses) / len(losses) if losses else 0
                
                # Expectancy
                expectancy = (profitable_trades/num_trades * avg_profit + loss_trades/num_trades * avg_loss) if num_trades > 0 else 0
                
                # Profit Factor - avoid infinity for better JSON handling
                total_profits = sum(profits) if profits else 0
                total_losses = abs(sum(losses)) if losses else 0
                if total_losses > 0:
                    profit_factor = total_profits / total_losses
                elif total_profits > 0:
                    # Instead of infinity, use a large number that indicates "no losses"
                    profit_factor = 999999  # Indicates perfect trades with no losses
                else:
                    profit_factor = 0
                
                # Duration statistics
                if trade_durations:
                    avg_duration = sum(trade_durations) / len(trade_durations)
                    max_duration = max(trade_durations)
                    min_duration = min(trade_durations)
                
                # Streak calculations
                current_profit_streak = current_loss_streak = 0
                for pnl in trade_pnl:
                    if pnl > 0:
                        current_profit_streak += 1
                        current_loss_streak = 0
                        max_profit_streak = max(max_profit_streak, current_profit_streak)
                    else:
                        current_loss_streak += 1
                        current_profit_streak = 0
                        max_loss_streak = max(max_loss_streak, current_loss_streak)
            else:
                # No trade P&L data, ensure all variables are set
                win_rate = 0
        else:
            # No valid trades, ensure all variables are set
            win_rate = 0
    else:
        # No TRADE_ID column, ensure all variables are set
        win_rate = 0
    
    # Additional metrics
    sharpe_ratio = avg_drawdown = cagr = calmar_ratio = avg_calmar = 0.0
    
    if 'Portfolio_Value' in result_df.columns and len(result_df) > 1:
        # Daily returns
        result_df['Daily_Return'] = result_df['Portfolio_Value'].pct_change()
        daily_returns = result_df['Daily_Return'].dropna()
        
        # Sharpe Ratio
        if len(daily_returns) > 0 and daily_returns.std() != 0:
            sharpe_ratio = (daily_returns.mean() * 252) / (daily_returns.std() * np.sqrt(252))
        
        # Average Drawdown
        if 'DD_Overall_%' in result_df.columns:
            drawdowns = result_df[result_df['DD_Overall_%'] > 0]['DD_Overall_%']
            avg_drawdown = drawdowns.mean() if len(drawdowns) > 0 else 0.0
        
        # CAGR
        years = len(result_df) / 252
        if years > 0 and initial_value > 0:
            cagr = (pow(final_value / initial_value, 1/years) - 1) * 100
        
        # Calmar Ratio - avoid infinity for better JSON handling
        if max_drawdown != 0:
            calmar_ratio = abs(cagr / max_drawdown)
        elif cagr > 0:
            # No drawdown but positive returns - use large number
            calmar_ratio = 999999  # Indicates excellent risk-adjusted returns
        else:
            calmar_ratio = 0.0
        
        # Average Calmar
        if len(result_df) > 252:
            rolling_returns = []
            rolling_max_dd = []
            for i in range(252, len(result_df)):
                window_data = result_df.iloc[i-252:i]
                if 'Portfolio_Value' in window_data.columns:
                    start_val = window_data['Portfolio_Value'].iloc[0]
                    end_val = window_data['Portfolio_Value'].iloc[-1]
                    annual_return = (end_val / start_val - 1) * 100
                    rolling_returns.append(annual_return)
                    
                    if 'DD_Overall_%' in window_data.columns:
                        window_max_dd = window_data['DD_Overall_%'].max()
                        rolling_max_dd.append(window_max_dd)
            
            if rolling_returns and rolling_max_dd:
                calmar_values = []
                for ret, dd in zip(rolling_returns, rolling_max_dd):
                    if dd != 0:
                        calmar_values.append(abs(ret / dd))
                if calmar_values:
                    avg_calmar = np.mean(calmar_values)
        else:
            avg_calmar = calmar_ratio
    
    # Return comprehensive metrics
    return {
        'total_market_days': total_market_days,
        'days_in_market': days_in_market,
        'days_in_market_pct': (days_in_market / total_market_days * 100) if total_market_days > 0 else 0,
        'num_trades': num_trades,
        'profitable_trades': profitable_trades,
        'loss_trades': loss_trades,
        'win_rate': win_rate,
        'max_profit': max_profit,
        'max_loss': max_loss,
        'avg_profit': avg_profit,
        'avg_loss': avg_loss,
        'expectancy': expectancy,
        'profit_factor': profit_factor,
        'max_profit_streak': max_profit_streak,
        'max_loss_streak': max_loss_streak,
        'avg_duration': avg_duration,
        'max_duration': max_duration,
        'min_duration': min_duration,
        'total_return': total_return,
        'max_drawdown': max_drawdown,
        'initial_value': initial_value,
        'final_value': final_value,
        'sharpe_ratio': sharpe_ratio,
        'avg_drawdown': avg_drawdown,
        'cagr': cagr,
        'calmar_ratio': calmar_ratio,
        'avg_calmar': avg_calmar
    }


def create_portfolio_value_with_dividends_chart(result_df, ticker, strategy_name="Strategy", investment_amount=10000):
    """
    Create a portfolio value chart including dividends from backtest results.
    
    Parameters:
    - result_df: DataFrame with timestamp and Portfolio_Value_with_Dividends columns
    - ticker: Stock ticker symbol
    - strategy_name: Name of the strategy for the title
    - investment_amount: Initial investment amount
    
    Returns:
    - HTML string of the plotly chart
    """
    fig = go.Figure()
    
    # Check if required columns exist
    if 'timestamp' in result_df.columns and 'Portfolio_Value_with_Dividends' in result_df.columns:
        # Add portfolio value with dividends line
        fig.add_trace(go.Scatter(
            x=result_df['timestamp'],
            y=result_df['Portfolio_Value_with_Dividends'],
            mode='lines',
            name='Portfolio Value (with Dividends)',
            line=dict(color='#00ff88', width=2),
            hovertemplate='Date: %{x}<br>Portfolio Value (with Dividends): $%{y:,.2f}<extra></extra>'
        ))
        
        # Also add the regular portfolio value for comparison
        if 'Portfolio_Value' in result_df.columns:
            fig.add_trace(go.Scatter(
                x=result_df['timestamp'],
                y=result_df['Portfolio_Value'],
                mode='lines',
                name='Portfolio Value (without Dividends)',
                line=dict(color='#ff8844', width=1, dash='dash'),
                hovertemplate='Date: %{x}<br>Portfolio Value (without Dividends): $%{y:,.2f}<extra></extra>'
            ))
    else:
        logger.error("Required columns (timestamp, Portfolio_Value_with_Dividends) not found for chart generation")
        return ""
    
    # Calculate summary statistics
    initial_value = investment_amount
    
    if 'Portfolio_Value_with_Dividends' in result_df.columns and len(result_df) > 0:
        final_value_with_div = result_df['Portfolio_Value_with_Dividends'].iloc[-1]
        total_return_with_div = (final_value_with_div / initial_value - 1) * 100
    else:
        final_value_with_div = initial_value
        total_return_with_div = 0.0
    
    if 'Portfolio_Value' in result_df.columns and len(result_df) > 0:
        final_value = result_df['Portfolio_Value'].iloc[-1]
        dividend_impact = final_value_with_div - final_value
    else:
        dividend_impact = 0.0
        
    # Check if DD_Overall_% exists for max drawdown
    if 'DD_Overall_%' in result_df.columns:
        max_drawdown = result_df['DD_Overall_%'].max()
    else:
        max_drawdown = 0.0
    
    # Update layout
    fig.update_layout(
        title=f'{strategy_name} Backtest Results with Dividends - {ticker}',
        xaxis_title='Date',
        yaxis_title='Portfolio Value ($)',
        template='plotly_dark',
        hovermode='x unified',
        height=600,
        showlegend=True
    )
    
    # Add annotations with summary stats
    fig.add_annotation(
        text=f"Initial: ${initial_value:,.0f}<br>Final (w/ Div): ${final_value_with_div:,.2f}<br>Return (w/ Div): {total_return_with_div:.2f}%<br>Dividend Impact: ${dividend_impact:,.2f}<br>Max DD: {max_drawdown:.2f}%",
        xref="paper", yref="paper",
        x=0.98, y=0.02,
        showarrow=False,
        bgcolor="rgba(0,0,0,0.8)",
        bordercolor="#666",
        borderwidth=1,
        font=dict(size=12, color="white"),
        align="right"
    )
    
    # Convert chart to HTML
    return to_html(fig, include_plotlyjs='cdn', div_id="portfolio-dividends-chart")


def create_dividends_bar_chart(result_df, ticker):
    """
    Create a bar chart showing dividend payments over time.
    
    Parameters:
    - result_df: DataFrame with timestamp and Dividends_Paid columns
    - ticker: Stock ticker symbol
    
    Returns:
    - HTML string of the plotly chart
    """
    fig = go.Figure()
    
    # Check if required columns exist
    if 'timestamp' in result_df.columns and 'Dividends_Paid' in result_df.columns:
        # Filter for non-zero dividend payments
        dividend_df = result_df[result_df['Dividends_Paid'] > 0].copy()
        
        if not dividend_df.empty:
            # Create bar chart for dividend payments
            fig.add_trace(go.Bar(
                x=dividend_df['timestamp'],
                y=dividend_df['Dividends_Paid'],
                name='Dividend Payments',
                marker_color='#00ffcc',
                hovertemplate='Date: %{x}<br>Dividend Payment: $%{y:,.2f}<extra></extra>'
            ))
            
            # Calculate total dividends
            total_dividends = dividend_df['Dividends_Paid'].sum()
            num_payments = len(dividend_df)
            avg_payment = total_dividends / num_payments if num_payments > 0 else 0
        else:
            total_dividends = 0
            num_payments = 0
            avg_payment = 0
    else:
        logger.warning("Required columns for Dividends bar chart not found")
        return ""
    
    # Update layout
    fig.update_layout(
        title=f'Dividend Payments - {ticker}',
        xaxis_title='Date',
        yaxis_title='Dividend Payment ($)',
        template='plotly_dark',
        hovermode='x unified',
        height=400,
        showlegend=False,
        yaxis=dict(
            tickformat='$,.2f',
            gridcolor='rgba(128, 128, 128, 0.2)'
        ),
        xaxis=dict(
            gridcolor='rgba(128, 128, 128, 0.2)'
        )
    )
    
    # Add statistics annotation
    fig.add_annotation(
        text=f"<b>Dividend Statistics</b><br>Total Dividends: ${total_dividends:,.2f}<br>Number of Payments: {num_payments}<br>Average Payment: ${avg_payment:,.2f}",
        xref="paper", yref="paper",
        x=0.98, y=0.98,
        showarrow=False,
        bordercolor="rgba(255, 255, 255, 0.3)",
        borderwidth=1,
        borderpad=10,
        bgcolor="rgba(30, 30, 30, 0.8)",
        font=dict(size=12, color="white"),
        align="left",
        xanchor="right",
        yanchor="top"
    )
    
    return to_html(fig, include_plotlyjs=False, div_id="dividends-bar-chart")


def calculate_dividend_inclusive_metrics(result_df, investment_amount=10000):
    """
    Calculate performance metrics that include dividend returns.
    
    Parameters:
    - result_df: DataFrame with backtest results including dividend columns
    - investment_amount: Initial investment amount
    
    Returns:
    - Dictionary of dividend-inclusive metrics
    """
    metrics = {}
    
    # Basic portfolio values
    initial_value = investment_amount
    
    # Calculate metrics with dividends
    if 'Portfolio_Value_with_Dividends' in result_df.columns and len(result_df) > 0:
        final_value_with_div = result_df['Portfolio_Value_with_Dividends'].iloc[-1]
        total_return_with_div = (final_value_with_div / initial_value - 1) * 100
    else:
        final_value_with_div = initial_value
        total_return_with_div = 0.0
    
    # Calculate metrics without dividends for comparison
    if 'Portfolio_Value' in result_df.columns and len(result_df) > 0:
        final_value = result_df['Portfolio_Value'].iloc[-1]
        total_return = (final_value / initial_value - 1) * 100
    else:
        final_value = initial_value
        total_return = 0.0
    
    # Dividend specific metrics
    if 'Dividends_Paid' in result_df.columns:
        total_dividends = result_df['Dividends_Paid'].sum()
        dividend_payments = result_df[result_df['Dividends_Paid'] > 0]
        num_dividend_payments = len(dividend_payments)
        
        if num_dividend_payments > 0:
            avg_dividend_payment = total_dividends / num_dividend_payments
            max_dividend_payment = dividend_payments['Dividends_Paid'].max()
        else:
            avg_dividend_payment = 0
            max_dividend_payment = 0
    else:
        total_dividends = 0
        num_dividend_payments = 0
        avg_dividend_payment = 0
        max_dividend_payment = 0
    
    # Calculate dividend contribution to returns
    dividend_contribution = total_return_with_div - total_return
    dividend_contribution_pct = (dividend_contribution / total_return * 100) if total_return != 0 else 0
    
    # CAGR with dividends
    years = len(result_df) / 252 if len(result_df) > 0 else 0
    if years > 0 and initial_value > 0:
        cagr_with_div = (pow(final_value_with_div / initial_value, 1/years) - 1) * 100
    else:
        cagr_with_div = 0
    
    # Sharpe ratio with dividends
    if 'Portfolio_Value_with_Dividends' in result_df.columns and len(result_df) > 1:
        result_df['Daily_Return_with_Div'] = result_df['Portfolio_Value_with_Dividends'].pct_change()
        daily_returns_with_div = result_df['Daily_Return_with_Div'].dropna()
        
        if len(daily_returns_with_div) > 0 and daily_returns_with_div.std() != 0:
            sharpe_with_div = (daily_returns_with_div.mean() * 252) / (daily_returns_with_div.std() * np.sqrt(252))
        else:
            sharpe_with_div = 0
    else:
        sharpe_with_div = 0
    
    return {
        'total_dividends': total_dividends,
        'num_dividend_payments': num_dividend_payments,
        'avg_dividend_payment': avg_dividend_payment,
        'max_dividend_payment': max_dividend_payment,
        'final_value_with_dividends': final_value_with_div,
        'total_return_with_dividends': total_return_with_div,
        'dividend_contribution': dividend_contribution,
        'dividend_contribution_pct': dividend_contribution_pct,
        'cagr_with_dividends': cagr_with_div,
        'sharpe_with_dividends': sharpe_with_div
    }


def calculate_dividend_yield_metrics(result_df, investment_amount=10000):
    """
    Calculate dividend yield specific metrics.
    
    Parameters:
    - result_df: DataFrame with backtest results including dividend columns
    - investment_amount: Initial investment amount
    
    Returns:
    - Dictionary of dividend yield metrics
    """
    metrics = {}
    
    # Get ticker name from columns
    ticker_cols = [col for col in result_df.columns if col.endswith('_Close') and not col.startswith('VIX') and not col.startswith('VVIX')]
    if ticker_cols:
        ticker_name = ticker_cols[0].replace('_Close', '')
        dividend_col = f'{ticker_name}_Dividends'
        close_col = f'{ticker_name}_Close'
    else:
        dividend_col = 'Dividends_Paid'
        close_col = None
    
    # Calculate yield metrics
    if dividend_col in result_df.columns:
        # Total dividends
        if 'Dividends_Paid' in result_df.columns:
            total_dividends = result_df['Dividends_Paid'].sum()
        else:
            total_dividends = result_df[dividend_col].sum()
        
        # Annual dividend yield based on initial investment
        years = len(result_df) / 252 if len(result_df) > 0 else 0
        if years > 0:
            annual_dividend = total_dividends / years
            annual_yield_on_cost = (annual_dividend / investment_amount * 100) if investment_amount > 0 else 0
        else:
            annual_dividend = 0
            annual_yield_on_cost = 0
        
        # Current yield (based on current price if available)
        if close_col and close_col in result_df.columns and len(result_df) > 0:
            current_price = result_df[close_col].iloc[-1]
            
            # Get last year's dividends
            if len(result_df) >= 252:
                last_year_df = result_df.iloc[-252:]
                if 'Dividends_Paid' in last_year_df.columns:
                    last_year_dividends = last_year_df['Dividends_Paid'].sum()
                else:
                    last_year_dividends = last_year_df[dividend_col].sum()
            else:
                if 'Dividends_Paid' in result_df.columns:
                    last_year_dividends = result_df['Dividends_Paid'].sum() * (252 / len(result_df))
                else:
                    last_year_dividends = result_df[dividend_col].sum() * (252 / len(result_df))
            
            # Calculate trailing yield
            if 'Shares' in result_df.columns and len(result_df) > 0:
                # Get average shares held
                shares_df = result_df[result_df['Shares'] != '']
                if not shares_df.empty:
                    avg_shares = shares_df['Shares'].astype(float).mean()
                    trailing_yield = (last_year_dividends / (avg_shares * current_price) * 100) if (avg_shares * current_price) > 0 else 0
                else:
                    trailing_yield = 0
            else:
                trailing_yield = 0
        else:
            current_price = 0
            last_year_dividends = 0
            trailing_yield = 0
        
        # Dividend growth rate (if we have enough data)
        if 'Dividends_Paid' in result_df.columns:
            yearly_dividends = []
            for i in range(0, len(result_df), 252):
                year_end = min(i + 252, len(result_df))
                year_dividends = result_df.iloc[i:year_end]['Dividends_Paid'].sum()
                if year_dividends > 0:
                    yearly_dividends.append(year_dividends)
            
            if len(yearly_dividends) > 1:
                # Calculate CAGR of dividends
                first_year = yearly_dividends[0]
                last_year = yearly_dividends[-1]
                years_of_data = len(yearly_dividends) - 1
                if years_of_data > 0 and first_year > 0:
                    dividend_growth_rate = (pow(last_year / first_year, 1/years_of_data) - 1) * 100
                else:
                    dividend_growth_rate = 0
            else:
                dividend_growth_rate = 0
        else:
            dividend_growth_rate = 0
    else:
        total_dividends = 0
        annual_dividend = 0
        annual_yield_on_cost = 0
        current_price = 0
        last_year_dividends = 0
        trailing_yield = 0
        dividend_growth_rate = 0
    
    return {
        'total_dividends_received': total_dividends,
        'annual_dividend': annual_dividend,
        'annual_yield_on_cost': annual_yield_on_cost,
        'last_year_dividends': last_year_dividends,
        'trailing_yield': trailing_yield,
        'dividend_growth_rate': dividend_growth_rate
    }





