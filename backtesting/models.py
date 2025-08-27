from django.db import models
from django.utils import timezone
from datetime import timedelta
import json

class BacktestProgress(models.Model):
    """Model to track backtest progress in database"""
    progress_key = models.CharField(max_length=50, unique=True, db_index=True)
    current = models.IntegerField(default=0)
    total = models.IntegerField(default=0)
    percentage = models.IntegerField(default=0)
    status = models.CharField(max_length=200, default='Starting...')
    error = models.BooleanField(default=False)
    result_data = models.TextField(blank=True, null=True)  # Store serialized result
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'backtest_progress'
        
    def set_result(self, dataframe):
        """Store the result dataframe as JSON"""
        if dataframe is not None:
            self.result_data = dataframe.to_json(date_format='iso')
            self.save()
            
    def get_result(self):
        """Retrieve the result dataframe from JSON"""
        import pandas as pd
        from io import StringIO
        if self.result_data:
            try:
                # Use StringIO to avoid deprecation warning
                return pd.read_json(StringIO(self.result_data), convert_dates=True)
            except Exception as e:
                # Fallback to old method if StringIO fails
                try:
                    return pd.read_json(self.result_data, convert_dates=True)
                except:
                    # Log the error and return None
                    import logging
                    logger = logging.getLogger(__name__)
                    logger.error(f"Failed to deserialize result data: {e}")
                    return None
        return None
        
    @classmethod
    def cleanup_old_records(cls, hours=2):
        """Delete progress records older than specified hours"""
        cutoff_time = timezone.now() - timedelta(hours=hours)
        old_records = cls.objects.filter(created_at__lt=cutoff_time)
        count = old_records.count()
        old_records.delete()
        return count
  