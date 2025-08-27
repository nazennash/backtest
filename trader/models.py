from django.db import models
from django.utils import timezone


class MarketData(models.Model):
    """Model to store market data from Polygon API"""
    ticker = models.CharField(max_length=10)
    timestamp = models.DateTimeField()
    open_price = models.DecimalField(max_digits=15, decimal_places=4)
    high_price = models.DecimalField(max_digits=15, decimal_places=4)
    low_price = models.DecimalField(max_digits=15, decimal_places=4)
    close_price = models.DecimalField(max_digits=15, decimal_places=4)
    volume = models.BigIntegerField()
    frequency = models.CharField(max_length=20)
    created_at = models.DateTimeField(default=timezone.now)
    
    class Meta:
        ordering = ['timestamp']
        unique_together = ['ticker', 'timestamp', 'frequency']
    
    def __str__(self):
        return f"{self.ticker} - {self.timestamp} - {self.frequency}"


class TickerSuggestion(models.Model):
    """Model to store ticker suggestions for autocomplete"""
    MARKET_CHOICES = [
        ('stocks', 'Stocks'),
        ('indices', 'Indices'),
        ('crypto', 'Cryptocurrency'),
        ('forex', 'Forex'),
    ]
    
    ticker = models.CharField(max_length=10, unique=True)
    name = models.CharField(max_length=200)
    market = models.CharField(max_length=50, choices=MARKET_CHOICES, default='stocks')
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(default=timezone.now)
    
    class Meta:
        ordering = ['ticker']
    
    def __str__(self):
        return f"{self.ticker} - {self.name} ({self.get_market_display()})"