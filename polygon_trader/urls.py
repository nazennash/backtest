"""polygon_trader URL Configuration"""
from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('trader.urls')),
    path('backtesting/', include('backtesting.urls')),
]