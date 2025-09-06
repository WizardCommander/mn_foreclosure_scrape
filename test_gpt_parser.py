#!/usr/bin/env python3
"""
Unit tests for GPT Parser using built-in unittest module
"""

import unittest
from unittest.mock import Mock, patch
import sys
import os

# Add current directory to path for imports
sys.path.insert(0, os.path.dirname(__file__))

from gpt_parser import GPTParser


class TestGPTParserPureFunctions(unittest.TestCase):
    """Test pure functions in GPT Parser"""
    
    def setUp(self):
        """Set up test fixtures"""
        self.parser = GPTParser()
    
    def test_is_meaningful_data_with_first_name(self):
        """Test meaningful data detection with first name"""
        data = {
            'first_name': 'John',
            'last_name': '',
            'street': '',
            'city': '',
            'state': 'MN',
            'zip': '',
            'date_filed': '',
            'plaintiff': '',
            'link': ''
        }
        
        result = self.parser._is_meaningful_data(data)
        self.assertTrue(result)
    
    def test_is_meaningful_data_with_last_name(self):
        """Test meaningful data detection with last name only"""
        data = {
            'first_name': '',
            'last_name': 'Doe',
            'street': '',
            'city': '',
            'state': 'MN',
            'zip': '',
            'date_filed': '',
            'plaintiff': '',
            'link': ''
        }
        
        result = self.parser._is_meaningful_data(data)
        self.assertTrue(result)
    
    def test_is_meaningful_data_with_both_names(self):
        """Test meaningful data detection with both names"""
        data = {
            'first_name': 'John',
            'last_name': 'Doe',
            'street': '123 Main St',
            'city': 'Minneapolis',
            'state': 'MN',
            'zip': '55401',
            'date_filed': '12/31/2024',
            'plaintiff': 'First Bank',
            'link': 'http://example.com'
        }
        
        result = self.parser._is_meaningful_data(data)
        self.assertTrue(result)
    
    def test_is_meaningful_data_empty(self):
        """Test meaningful data detection with empty data"""
        data = {
            'first_name': '',
            'last_name': '',
            'street': '',
            'city': '',
            'state': 'MN',
            'zip': '',
            'date_filed': '',
            'plaintiff': '',
            'link': ''
        }
        
        result = self.parser._is_meaningful_data(data)
        self.assertFalse(result)
    
    def test_clean_notice_text_removes_html(self):
        """Test HTML tag removal from notice text"""
        html_text = "<p>This is a <b>foreclosure</b> notice for <span>John Doe</span></p>"
        
        cleaned = self.parser._clean_notice_text(html_text)
        
        self.assertEqual(cleaned, "This is a foreclosure notice for John Doe")
        self.assertNotIn('<', cleaned)
        self.assertNotIn('>', cleaned)
    
    def test_clean_notice_text_removes_css_artifacts(self):
        """Test CSS artifact removal"""
        css_text = "Notice text cssfontface more text csstransitions final text fontface"
        
        cleaned = self.parser._clean_notice_text(css_text)
        
        self.assertEqual(cleaned, "Notice text more text final text")
    
    def test_clean_notice_text_normalizes_whitespace(self):
        """Test whitespace normalization"""
        messy_text = "Too    much\n\n\nwhitespace\t\there"
        
        cleaned = self.parser._clean_notice_text(messy_text)
        
        self.assertEqual(cleaned, "Too much whitespace here")
    
    def test_clean_notice_text_truncates_long_text(self):
        """Test long text truncation"""
        long_text = "x" * 4000  # Longer than 3000 character limit
        
        cleaned = self.parser._clean_notice_text(long_text)
        
        self.assertTrue(len(cleaned) <= 3003)  # 3000 + "..."
        self.assertTrue(cleaned.endswith("..."))
    
    def test_empty_data_structure(self):
        """Test empty data structure creation"""
        test_url = "http://example.com/notice"
        
        empty_data = self.parser._empty_data_structure(test_url)
        
        expected_keys = ['first_name', 'last_name', 'street', 'city', 'state', 'zip', 'date_filed', 'plaintiff', 'link']
        
        for key in expected_keys:
            self.assertIn(key, empty_data)
            if key == 'link':
                self.assertEqual(empty_data[key], test_url)
            elif key == 'state':
                self.assertEqual(empty_data[key], 'MN')
            else:
                self.assertEqual(empty_data[key], '')


class TestGPTParserRegexFallback(unittest.TestCase):
    """Test regex fallback parsing functionality"""
    
    def setUp(self):
        """Set up test fixtures"""
        self.parser = GPTParser()
        self.test_url = "http://example.com/notice"
    
    def test_regex_fallback_extracts_names(self):
        """Test regex extraction of debtor names"""
        notice_text = """
        MORTGAGOR: John Smith
        Property: 123 Main Street, Minneapolis, MN 55401
        """
        
        result = self.parser._regex_fallback(notice_text, self.test_url)
        
        self.assertEqual(result['first_name'], 'John')
        self.assertEqual(result['last_name'], 'Smith')
        self.assertEqual(result['link'], self.test_url)
    
    def test_regex_fallback_extracts_debtor_names(self):
        """Test regex extraction with DEBTOR keyword"""
        notice_text = """
        DEBTOR(S): Jane Doe
        Address: 456 Oak Ave, St Paul, MN 55102-1234
        """
        
        result = self.parser._regex_fallback(notice_text, self.test_url)
        
        self.assertEqual(result['first_name'], 'Jane')
        self.assertEqual(result['last_name'], 'Doe')
    
    def test_regex_fallback_extracts_address(self):
        """Test regex extraction of property address"""
        notice_text = """
        MORTGAGOR: John Smith
        Property located at: 789 Pine Street, Minneapolis, MN 55401
        """
        
        result = self.parser._regex_fallback(notice_text, self.test_url)
        
        self.assertEqual(result['street'], '789 Pine Street')
        self.assertEqual(result['city'], 'Minneapolis')
        self.assertEqual(result['zip'], '55401')
        self.assertEqual(result['state'], 'MN')
    
    def test_regex_fallback_extracts_date(self):
        """Test regex extraction of filed date"""
        notice_text = """
        MORTGAGOR: John Smith
        Filed on: 12/31/2024
        Property: 123 Main St, Minneapolis, MN 55401
        """
        
        result = self.parser._regex_fallback(notice_text, self.test_url)
        
        self.assertEqual(result['date_filed'], '12/31/2024')
    
    def test_regex_fallback_extracts_plaintiff(self):
        """Test regex extraction of plaintiff/creditor"""
        notice_text = """
        MORTGAGOR: John Smith
        MORTGAGEE: First National Bank
        Property: 123 Main St, Minneapolis, MN 55401
        """
        
        result = self.parser._regex_fallback(notice_text, self.test_url)
        
        self.assertEqual(result['plaintiff'], 'First National Bank')
    
    def test_regex_fallback_handles_no_matches(self):
        """Test regex fallback with text that has no matches"""
        notice_text = "This is random text with no structured information"
        
        result = self.parser._regex_fallback(notice_text, self.test_url)
        
        # Should return empty structure but not fail
        self.assertEqual(result['first_name'], '')
        self.assertEqual(result['last_name'], '')
        self.assertEqual(result['state'], 'MN')  # Always MN
        self.assertEqual(result['link'], self.test_url)
    
    def test_regex_fallback_handles_exceptions(self):
        """Test regex fallback handles malformed text gracefully"""
        # Test with None (edge case)
        result = self.parser._regex_fallback(None, self.test_url)
        
        self.assertEqual(result['link'], self.test_url)
        self.assertEqual(result['state'], 'MN')


class TestGPTParserStats(unittest.TestCase):
    """Test statistics tracking"""
    
    def setUp(self):
        """Set up test fixtures"""
        self.parser = GPTParser()
    
    def test_initial_stats(self):
        """Test initial statistics are zero"""
        stats = self.parser.get_stats()
        
        self.assertEqual(stats['total_parses'], 0)
        self.assertEqual(stats['gpt_successful'], 0)
        self.assertEqual(stats['regex_fallbacks'], 0)
        self.assertEqual(stats['gpt_success_rate'], 0)
    
    def test_stats_calculation(self):
        """Test statistics calculation with sample data"""
        # Simulate some parsing activity
        self.parser.gpt_calls = 8
        self.parser.regex_fallbacks = 2
        
        stats = self.parser.get_stats()
        
        self.assertEqual(stats['total_parses'], 10)
        self.assertEqual(stats['gpt_successful'], 8)
        self.assertEqual(stats['regex_fallbacks'], 2)
        self.assertEqual(stats['gpt_success_rate'], 80.0)


if __name__ == '__main__':
    # Run tests with verbose output
    unittest.main(verbosity=2)