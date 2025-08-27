from django.urls import path
from . import views

app_name = 'backtesting'

urlpatterns = [
    path('section/', views.backtesting_section, name='section'),
    path('run-strategy1/', views.run_strategy1_backtest, name='run_strategy1'),
    path('run-strategy2/', views.run_strategy2_backtest, name='run_strategy2'),
    path('progress/<str:progress_key>/', views.get_backtest_progress, name='get_progress'),
    path('get-result/', views.get_backtest_result, name='get_result'),
    path('update-metrics/', views.update_metrics_for_period, name='update_metrics'),
    path('download-excel/', views.download_backtest_excel, name='download_excel'),
]