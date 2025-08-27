from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth.models import User
from .models import MarketData, TickerSuggestion
from .forms import ChartDataForm
from .polygon_api import PolygonAPI
from datetime import date, timedelta
import json


class TraderViewsTestCase(TestCase):
    def setUp(self):
        self.client = Client()
        
    def test_index_view_get(self):
        """Test that the index view loads correctly"""
        response = self.client.get(reverse('trader:index'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Chart Parameters')
        self.assertContains(response, 'ticker')
        
    def test_ticker_suggestions_api(self):
        """Test the ticker suggestions API endpoint"""
        # Create a test ticker suggestion
        TickerSuggestion.objects.create(
            ticker='AAPL',
            name='Apple Inc.',
            market='stocks',
            is_active=True
        )
        
        response = self.client.get(reverse('trader:ticker_suggestions'), {'q': 'AAP'})
        self.assertEqual(response.status_code, 200)
        
        data = json.loads(response.content)
        self.assertIn('suggestions', data)
        
    def test_form_validation(self):
        """Test form validation"""
        form_data = {
            'ticker': 'AAPL',
            'start_date': date.today() - timedelta(days=30),
            'end_date': date.today(),
            'frequency': 'day'
        }
        
        form = ChartDataForm(data=form_data)
        self.assertTrue(form.is_valid())
        
    def test_form_validation_invalid_dates(self):
        """Test form validation with invalid dates"""
        form_data = {
            'ticker': 'AAPL',
            'start_date': date.today(),
            'end_date': date.today() - timedelta(days=30),  # End before start
            'frequency': 'day'
        }
        
        form = ChartDataForm(data=form_data)
        self.assertFalse(form.is_valid())


class MarketDataModelTestCase(TestCase):
    def test_market_data_creation(self):
        """Test creating a MarketData instance"""
        market_data = MarketData.objects.create(
            ticker='AAPL',
            timestamp='2023-01-01 09:30:00',
            open_price=150.00,
            high_price=155.00,
            low_price=149.00,
            close_price=154.00,
            volume=1000000,
            frequency='day'
        )
        
        self.assertEqual(market_data.ticker, 'AAPL')
        self.assertEqual(str(market_data.close_price), '154.0000')
        
    def test_ticker_suggestion_creation(self):
        """Test creating a TickerSuggestion instance"""
        suggestion = TickerSuggestion.objects.create(
            ticker='MSFT',
            name='Microsoft Corporation',
            market='stocks'
        )
        
        self.assertEqual(suggestion.ticker, 'MSFT')
        self.assertTrue(suggestion.is_active)
        self.assertEqual(str(suggestion), 'MSFT - Microsoft Corporation')


class PolygonAPITestCase(TestCase):
    def setUp(self):
        self.api = PolygonAPI()
    
    def test_index_detection(self):
        """Test that indices are properly detected"""
        self.assertTrue(self.api.is_index_ticker('VIX'))
        self.assertTrue(self.api.is_index_ticker('VVIX'))
        self.assertTrue(self.api.is_index_ticker('I:VIX'))
        self.assertFalse(self.api.is_index_ticker('AAPL'))
        self.assertFalse(self.api.is_index_ticker('MSFT'))
    
    def test_ticker_formatting(self):
        """Test that tickers are properly formatted for API calls"""
        # Test index formatting
        self.assertEqual(self.api.format_ticker_for_api('VIX'), 'I:VIX')
        self.assertEqual(self.api.format_ticker_for_api('VVIX'), 'I:VVIX')
        self.assertEqual(self.api.format_ticker_for_api('I:VIX'), 'I:VIX')
        
        # Test stock formatting (should remain unchanged)
        self.assertEqual(self.api.format_ticker_for_api('AAPL'), 'AAPL')
        self.assertEqual(self.api.format_ticker_for_api('MSFT'), 'MSFT')
    
    def test_ticker_type_detection(self):
        """Test ticker type detection"""
        self.assertEqual(self.api.get_ticker_type('VIX'), 'index')
        self.assertEqual(self.api.get_ticker_type('VVIX'), 'index')
        self.assertEqual(self.api.get_ticker_type('AAPL'), 'stock')
        self.assertEqual(self.api.get_ticker_type('MSFT'), 'stock')
    
    def test_index_suggestions(self):
        """Test that index suggestions are included"""
        suggestions = self.api.get_ticker_suggestions('VIX', 10)
        
        # Should find VIX-related indices
        vix_suggestions = [s for s in suggestions if 'VIX' in s['ticker']]
        self.assertTrue(len(vix_suggestions) > 0)
        
        # Check that indices are marked correctly
        for suggestion in vix_suggestions:
            if suggestion['ticker'] in self.api.common_indices:
                self.assertEqual(suggestion['market'], 'indices')