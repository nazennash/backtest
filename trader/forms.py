from django import forms
from django.core.exceptions import ValidationError
from datetime import date


class ChartDataForm(forms.Form):
    """Form for collecting user input for chart generation"""
    
    FREQUENCY_CHOICES = [
        ('1', '1 Second'),
        ('5', '5 Seconds'),
        ('10', '10 Seconds'),
        ('15', '15 Seconds'),
        ('30', '30 Seconds'),
        ('minute', '1 Minute'),
        ('5minute', '5 Minutes'),
        ('15minute', '15 Minutes'),
        ('30minute', '30 Minutes'),
        ('hour', '1 Hour'),
        ('4hour', '4 Hours'),
        ('day', '1 Day'),
        ('week', '1 Week'),
        ('month', '1 Month'),
    ]
    
    ticker = forms.CharField(
        max_length=10,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter ticker or index (e.g., AAPL, VIX)',
            'autocomplete': 'off',
            'id': 'ticker-input',
            'value': 'QQQ'
        }),
        initial='QQQ',
        help_text='Enter a stock ticker symbol or index (like VIX, VVIX, SPX)'
    )
    
    start_date = forms.DateField(
        widget=forms.DateInput(attrs={
            'class': 'form-control',
            'type': 'date',
            'id': 'start-date',
            'min': '2023-02-01',
            'max': date.today().strftime('%Y-%m-%d')
        }),
        initial=date(2023, 2, 1),
        help_text='Select start date for the data (earliest: Feb 1, 2023)'
    )
    
    end_date = forms.DateField(
        widget=forms.DateInput(attrs={
            'class': 'form-control',
            'type': 'date',
            'id': 'end-date',
            'max': date.today().strftime('%Y-%m-%d')
        }),
        initial=date.today,
        help_text='Select end date for the data (defaults to today)'
    )
    
    frequency = forms.ChoiceField(
        choices=FREQUENCY_CHOICES,
        widget=forms.Select(attrs={
            'class': 'form-control',
            'id': 'frequency-select'
        }),
        initial='day',
        help_text='Select the frequency for the candlestick data'
    )
    
    def clean_ticker(self):
        ticker = self.cleaned_data['ticker'].upper().strip()
        if len(ticker) < 1:
            raise ValidationError('Ticker symbol is required.')
        return ticker
    
    def clean(self):
        cleaned_data = super().clean()
        start_date = cleaned_data.get('start_date')
        end_date = cleaned_data.get('end_date')
        
        # Minimum allowed start date
        min_start_date = date(2023, 2, 1)
        
        if start_date:
            if start_date < min_start_date:
                raise ValidationError(f'Start date cannot be before {min_start_date.strftime("%B %d, %Y")}.')
        
        if start_date and end_date:
            if start_date > end_date:
                raise ValidationError('Start date must be before end date.')
            
            if end_date > date.today():
                raise ValidationError('End date cannot be in the future.')
        
        return cleaned_data