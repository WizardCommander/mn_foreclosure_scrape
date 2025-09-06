#!/usr/bin/env python3
"""
Unit tests for MN Notice Scraper using built-in unittest module
"""

import unittest
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, MagicMock
import sys
import os

# Add current directory to path for imports
sys.path.insert(0, os.path.dirname(__file__))

from mn_scraper import MNNoticeScraperClean


class TestMNScraperPureFunctions(unittest.TestCase):
    """Test pure functions that don't require browser automation"""
    
    def setUp(self):
        """Set up test fixtures"""
        # Create scraper instance without browser setup
        self.scraper = MNNoticeScraperClean.__new__(MNNoticeScraperClean)
        # Don't call __init__ to avoid browser setup
    
    def test_calculate_search_dates_returns_yesterday(self):
        """Test that search dates are calculated as yesterday"""
        start_date, end_date = self.scraper._calculate_search_dates()
        
        # Both should be yesterday
        yesterday = datetime.now() - timedelta(days=1)
        
        # Check dates are correct (within same day, accounting for test execution time)
        self.assertEqual(start_date.date(), yesterday.date())
        self.assertEqual(end_date.date(), yesterday.date())
        self.assertEqual(start_date, end_date)
    
    def test_calculate_search_dates_timezone_handling(self):
        """Test date calculation handles timezone properly"""
        # Mock datetime to test specific date scenarios
        with patch('mn_scraper.datetime') as mock_datetime:
            mock_now = datetime(2024, 1, 15, 14, 30, 0)
            mock_datetime.now.return_value = mock_now
            
            start_date, end_date = self.scraper._calculate_search_dates()
            
            expected_date = datetime(2024, 1, 14, 14, 30, 0)  # Previous day
            self.assertEqual(start_date, expected_date)
            self.assertEqual(end_date, expected_date)
    
    def test_calculate_search_dates_new_year_boundary(self):
        """Test date calculation across year boundary"""
        with patch('mn_scraper.datetime') as mock_datetime:
            # January 1st should give December 31st of previous year
            mock_now = datetime(2024, 1, 1, 0, 0, 0)
            mock_datetime.now.return_value = mock_now
            
            start_date, end_date = self.scraper._calculate_search_dates()
            
            expected_date = datetime(2023, 12, 31, 0, 0, 0)
            self.assertEqual(start_date, expected_date)
            self.assertEqual(end_date, expected_date)


class TestMNScraperBrowserFunctions(unittest.TestCase):
    """Test browser interaction functions with mocking"""
    
    def setUp(self):
        """Set up test fixtures with mocked browser"""
        # Create scraper instance without browser setup
        self.scraper = MNNoticeScraperClean.__new__(MNNoticeScraperClean)
        
        # Mock the page object
        self.mock_page = Mock()
        self.scraper.page = self.mock_page
        
        # Mock common page elements
        self.mock_element = Mock()
        self.mock_element.fill.return_value = None
        self.mock_element.click.return_value = None
        self.mock_element.is_checked.return_value = False
        self.mock_element.is_visible.return_value = True
        self.mock_element.is_enabled.return_value = True
        self.mock_element.get_attribute.return_value = ""
        
        self.mock_page.wait_for_selector.return_value = self.mock_element
        self.mock_page.query_selector_all.return_value = []
    
    def test_fill_keyword_field_success(self):
        """Test successful keyword field filling"""
        result = self.scraper._fill_keyword_field("foreclosure")
        
        self.assertTrue(result)
        self.mock_page.wait_for_selector.assert_called_with("input[type='text']")
        self.mock_element.fill.assert_called_with("foreclosure")
    
    def test_fill_keyword_field_failure(self):
        """Test keyword field filling handles exceptions"""
        self.mock_page.wait_for_selector.side_effect = Exception("Element not found")
        
        result = self.scraper._fill_keyword_field("foreclosure")
        
        self.assertFalse(result)
    
    def test_set_any_words_radio_success(self):
        """Test successful radio button setting"""
        result = self.scraper._set_any_words_radio()
        
        self.assertTrue(result)
        self.mock_page.wait_for_selector.assert_called_with(
            "#ctl00_ContentPlaceHolder1_as1_rdoType_1"
        )
        # Should check if already selected
        self.mock_element.is_checked.assert_called()
    
    def test_set_any_words_radio_already_checked(self):
        """Test radio button when already selected"""
        self.mock_element.is_checked.return_value = True
        
        result = self.scraper._set_any_words_radio()
        
        self.assertTrue(result)
        # Should not click if already checked
        self.mock_page.evaluate.assert_not_called()
    
    def test_click_search_button_success(self):
        """Test successful search button click"""
        result = self.scraper._click_search_button()
        
        self.assertTrue(result)
        self.mock_page.wait_for_selector.assert_called_with(
            "#ctl00_ContentPlaceHolder1_as1_btnGo"
        )
        self.mock_element.click.assert_called()
    
    def test_click_search_button_failure(self):
        """Test search button click handles exceptions"""
        self.mock_element.click.side_effect = Exception("Click failed")
        
        result = self.scraper._click_search_button()
        
        self.assertFalse(result)
    
    @patch('time.sleep')  # Mock sleep to speed up tests
    def test_fill_date_fields_success(self, mock_sleep):
        """Test successful date field filling"""
        # Mock date inputs with from/to fields
        from_field = Mock()
        from_field.is_visible.return_value = True
        from_field.is_enabled.return_value = True
        from_field.get_attribute.side_effect = lambda attr: "fromDate" if attr == "name" else ""
        
        to_field = Mock()
        to_field.is_visible.return_value = True
        to_field.is_enabled.return_value = True
        to_field.get_attribute.side_effect = lambda attr: "toDate" if attr == "name" else ""
        
        self.mock_page.query_selector_all.return_value = [from_field, to_field]
        
        test_date = datetime(2024, 1, 15)
        result = self.scraper._fill_date_fields(test_date, test_date)
        
        self.assertTrue(result)
        from_field.fill.assert_called_with("01/15/2024")
        to_field.fill.assert_called_with("01/15/2024")


if __name__ == '__main__':
    # Run tests with verbose output
    unittest.main(verbosity=2)