"""
Custom JSON encoder for handling NumPy and Pandas data types.
This module provides utilities for JSON serialization of scientific computing types.
"""

import json
import numpy as np
import pandas as pd
from decimal import Decimal
from datetime import datetime, date, time, timedelta


class NumpyJSONEncoder(json.JSONEncoder):
    """
    Custom JSON encoder that handles NumPy and Pandas data types.
    
    This encoder converts NumPy/Pandas types to Python native types
    that are JSON serializable, preventing "Object of type int64 is not JSON serializable" errors.
    """
    
    def default(self, obj):
        """Convert NumPy/Pandas types to Python native types."""
        
        # Handle NumPy integer types
        if isinstance(obj, (np.integer, np.int_, np.intc, np.intp, np.int8,
                           np.int16, np.int32, np.int64, np.uint8,
                           np.uint16, np.uint32, np.uint64)):
            return int(obj)
        
        # Handle NumPy floating types
        elif isinstance(obj, (np.floating, np.float64_, np.float16, np.float32, np.float64)):
            # Check for special values
            if np.isnan(obj):
                return None  # or return 'NaN' if you prefer string representation
            elif np.isinf(obj):
                return 999999 if obj > 0 else -999999  # or return 'Infinity'/'-Infinity'
            return float(obj)
        
        # Handle NumPy boolean
        elif isinstance(obj, np.bool_):
            return bool(obj)
        
        # Handle NumPy arrays
        elif isinstance(obj, np.ndarray):
            return obj.tolist()
        
        # Handle Pandas Series
        elif isinstance(obj, pd.Series):
            return obj.tolist()
        
        # Handle Pandas DataFrame
        elif isinstance(obj, pd.DataFrame):
            return obj.to_dict(orient='records')
        
        # Handle Pandas Timestamp
        elif isinstance(obj, pd.Timestamp):
            return obj.isoformat()
        
        # Handle Pandas NaT (Not a Time)
        elif pd.isna(obj):
            return None
        
        # Handle Python datetime types
        elif isinstance(obj, (datetime, date, time)):
            return obj.isoformat()
        
        # Handle timedelta
        elif isinstance(obj, timedelta):
            return obj.total_seconds()
        
        # Handle Decimal
        elif isinstance(obj, Decimal):
            return float(obj)
        
        # Handle bytes
        elif isinstance(obj, bytes):
            return obj.decode('utf-8', errors='ignore')
        
        # Let the base class default method raise the TypeError
        return super().default(obj)


def sanitize_metrics_dict(metrics):
    """
    Sanitize a metrics dictionary to ensure all values are JSON serializable.
    
    This function converts NumPy/Pandas types to Python native types in place.
    
    Args:
        metrics (dict): Dictionary containing metric values
    
    Returns:
        dict: The same dictionary with all values converted to JSON-serializable types
    """
    for key, value in metrics.items():
        # Handle NumPy integer types
        if isinstance(value, (np.integer, np.int_, np.intc, np.intp, np.int8,
                             np.int16, np.int32, np.int64, np.uint8,
                             np.uint16, np.uint32, np.uint64)):
            metrics[key] = int(value)
        
        # Handle NumPy floating types
        elif isinstance(value, (np.floating, np.float16, np.float32, np.float64)):
            if np.isnan(value):
                metrics[key] = 0  # Default NaN to 0 for metrics
            elif np.isinf(value):
                metrics[key] = 999999 if value > 0 else -999999
            else:
                metrics[key] = float(value)
        
        # Handle NumPy boolean
        elif isinstance(value, np.bool_):
            metrics[key] = bool(value)
        
        # Handle NumPy arrays or Pandas Series
        elif isinstance(value, (np.ndarray, pd.Series)):
            metrics[key] = value.tolist()
        
        # Handle Pandas DataFrame
        elif isinstance(value, pd.DataFrame):
            metrics[key] = value.to_dict(orient='records')
        
        # Handle Pandas Timestamp
        elif isinstance(value, pd.Timestamp):
            metrics[key] = value.isoformat()
        
        # Handle NaN/None
        elif pd.isna(value):
            metrics[key] = 0  # Default to 0 for metrics
        
        # Handle Python float special cases
        elif isinstance(value, float):
            if np.isnan(value):
                metrics[key] = 0
            elif np.isinf(value):
                metrics[key] = 999999 if value > 0 else -999999
    
    return metrics


def safe_json_response(data, **kwargs):
    """
    Create a JsonResponse with automatic NumPy/Pandas type handling.
    
    This is a convenience function that automatically uses the NumpyJSONEncoder.
    
    Args:
        data: The data to serialize to JSON
        **kwargs: Additional arguments to pass to JsonResponse
    
    Returns:
        JsonResponse: A Django JsonResponse with proper encoding
    """
    from django.http import JsonResponse
    
    # Remove 'encoder' from kwargs if it exists to avoid conflicts
    kwargs.pop('encoder', None)
    
    # Always use our custom encoder
    return JsonResponse(data, encoder=NumpyJSONEncoder, **kwargs)