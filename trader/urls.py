from django.urls import path
from . import views

app_name = 'trader'

urlpatterns = [
    path('', views.index, name='index'),
    path('api/search-tickers/', views.search_tickers, name='search_tickers'),
    path('api/ticker-suggestions/', views.ticker_suggestions, name='ticker_suggestions'),
    path('api/ticker-details/', views.ticker_details, name='ticker_details'),
    path('api/generate-chart/', views.generate_chart_api, name='generate_chart_api'),
]