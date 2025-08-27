# Index Support Documentation

## Overview

The Django Trading Dashboard now supports downloading and displaying data for major market indices like VIX, VVIX, SPX, and others through the Polygon.io API.

## What Changed

### 1. Polygon API Client (`polygon_api.py`)

- **Index Detection**: Added `is_index_ticker()` method to identify index symbols
- **Ticker Formatting**: Added `format_ticker_for_api()` to automatically add "I:" prefix for indices  
- **Common Indices Mapping**: Pre-defined mapping for popular indices (VIX → I:VIX, VVIX → I:VVIX, etc.)
- **Enhanced Suggestions**: Updated autocomplete to include indices with proper labeling
- **API Adjustments**: Removed 'adjusted' parameter for index data requests

### 2. Chart Generation (`views.py`)

- **Smart Labeling**: Charts automatically detect index vs stock and adjust titles
- **Proper Y-axis**: Uses "Value" for indices instead of "Price ($)"
- **Chart Titles**: Shows "Index" or "Stock" in the chart title

### 3. User Interface (`templates/`)

- **Visual Badges**: INDEX/STOCK badges in autocomplete suggestions
- **Enhanced Tooltips**: Updated placeholder text and help text
- **Better Tips**: Added tip about index support

### 4. Forms (`forms.py`)

- **Updated Placeholders**: Mentions both stocks and indices in examples
- **Enhanced Help Text**: Explains index support

### 5. Models (`models.py`)

- **Market Choices**: Added choices for different market types
- **Better Display**: Updated string representation to show market type

### 6. Tests (`tests.py`)

- **Index Tests**: Added comprehensive tests for index detection and formatting
- **API Tests**: Tests for ticker formatting and type detection

## Supported Indices

The following indices are automatically supported:

| Symbol | Full API Symbol | Description |
|--------|----------------|-------------|
| VIX    | I:VIX         | CBOE Volatility Index |
| VVIX   | I:VVIX        | VIX of VIX |
| SPX    | I:SPX         | S&P 500 Index |
| DJI    | I:DJI         | Dow Jones Industrial Average |
| NDX    | I:NDX         | NASDAQ-100 Index |
| RUT    | I:RUT         | Russell 2000 Index |
| VXN    | I:VXN         | NASDAQ-100 Volatility Index |
| RVX    | I:RVX         | Russell 2000 Volatility Index |
| SKEW   | I:SKEW        | CBOE SKEW Index |
| VIX9D  | I:VIX9D       | CBOE 9-Day Volatility Index |

## How It Works

1. **User Input**: User types "VIX" in the ticker field
2. **Detection**: System recognizes it's an index from the pre-defined mapping
3. **API Formatting**: Converts "VIX" to "I:VIX" for the Polygon API call
4. **Data Retrieval**: Fetches data using the properly formatted ticker
5. **Chart Display**: Shows "VIX Index - Candlestick Chart" with "Value" on Y-axis
6. **Autocomplete**: Shows "VIX [INDEX]" badge in suggestions

## API Differences for Indices

- **Ticker Format**: Indices require "I:" prefix (e.g., "I:VIX")
- **No Adjustments**: The 'adjusted' parameter is removed for index requests
- **Volume Data**: Some indices may have zero or missing volume data
- **Frequency Limits**: Some high-frequency data may not be available for all indices

## Testing Index Support

To test the new functionality:

1. Run the Django app: `python manage.py runserver`
2. Navigate to the main page
3. Type "VIX" in the ticker field
4. Select "VIX [INDEX]" from the dropdown
5. Choose a date range and frequency
6. Generate the chart

You should see:

- Chart titled "VIX Index - Candlestick Chart"
- Y-axis labeled "Value" instead of "Price ($)"
- Proper candlestick data for the VIX volatility index

## Error Handling

The system gracefully handles:

- Invalid index symbols (falls back to regular stock lookup)
- Missing volume data for indices (sets to 0)
- API errors (shows appropriate error messages)
- Mixed case input (automatically converts to uppercase)

## Future Enhancements

Potential improvements:

1. Support for more exotic indices
2. Cryptocurrency index support
3. International index support
4. Custom index symbol input (manual "I:" prefix)
5. Volume-less chart types for indices where volume is not relevant
