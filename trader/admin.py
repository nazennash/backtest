from django.contrib import admin
from .models import MarketData, TickerSuggestion


@admin.register(MarketData)
class MarketDataAdmin(admin.ModelAdmin):
    list_display = ['ticker', 'timestamp', 'close_price', 'volume', 'frequency']
    list_filter = ['ticker', 'frequency', 'timestamp']
    search_fields = ['ticker']
    ordering = ['-timestamp']


@admin.register(TickerSuggestion)
class TickerSuggestionAdmin(admin.ModelAdmin):
    list_display = ['ticker', 'name', 'market', 'is_active']
    list_filter = ['market', 'is_active']
    search_fields = ['ticker', 'name']
    ordering = ['ticker']