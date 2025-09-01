#!/usr/bin/env python3
"""
Unit tests for GPT-based text parser
"""

import unittest
from unittest.mock import Mock, patch, MagicMock
import json
import os

# Load environment variables before importing gpt_parser
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from gpt_parser import GPTParser, extract_notice_data_gpt, get_parsing_stats


class TestGPTParser(unittest.TestCase):
    
    def setUp(self):
        """Set up test fixtures"""
        # Reset the global parser stats
        from gpt_parser import gpt_parser
        gpt_parser.gpt_calls = 0
        gpt_parser.regex_fallbacks = 0
    
    def test_initialization_with_valid_api_key(self):
        """Should initialize successfully with valid OpenAI API key"""
        with patch.dict(os.environ, {'OPENAI_API_KEY': 'sk-test-key'}):
            with patch('gpt_parser.OpenAI') as mock_openai:
                mock_client = Mock()
                mock_openai.return_value = mock_client
                
                parser = GPTParser()
                
                self.assertTrue(parser.enabled)
                self.assertEqual(parser.client, mock_client)
                mock_openai.assert_called_once_with(api_key='sk-test-key')
    
    def test_initialization_without_api_key(self):
        """Should disable GPT parsing when no API key provided"""
        with patch.dict(os.environ, {}, clear=True):
            parser = GPTParser()
            
            self.assertFalse(parser.enabled)
            self.assertIsNone(parser.client)
    
    def test_initialization_with_openai_import_error(self):
        """Should disable GPT parsing when OpenAI library not available"""
        with patch('gpt_parser.HAS_OPENAI', False):
            parser = GPTParser()
            
            self.assertFalse(parser.enabled)
            self.assertIsNone(parser.client)
    
    def test_extract_notice_data_gpt_disabled(self):
        """Should use regex fallback when GPT is disabled"""
        parser = GPTParser()
        parser.enabled = False
        
        test_text = "MORTGAGOR: John Doe, 123 Main St, Minneapolis, MN 55401"
        result = parser.extract_notice_data(test_text, "http://test.com")
        
        # Should return valid structure with MN state
        self.assertEqual(result['state'], 'MN')
        self.assertEqual(result['link'], 'http://test.com')
        self.assertEqual(parser.regex_fallbacks, 1)
        self.assertEqual(parser.gpt_calls, 0)
    
    @patch('gpt_parser.OpenAI')
    def test_extract_notice_data_gpt_success(self, mock_openai):
        """Should extract data successfully when GPT returns valid JSON"""
        # Setup mock OpenAI client
        mock_client = Mock()
        mock_response = Mock()
        mock_choice = Mock()
        mock_message = Mock()
        mock_message.content = '''
        {
            "first_name": "John",
            "last_name": "Doe",
            "street": "123 Main St",
            "city": "Minneapolis",
            "zip": "55401",
            "date_filed": "12/31/2024",
            "plaintiff": "First National Bank"
        }
        '''
        mock_choice.message = mock_message
        mock_response.choices = [mock_choice]
        mock_client.chat.completions.create.return_value = mock_response
        mock_openai.return_value = mock_client
        
        with patch.dict(os.environ, {'OPENAI_API_KEY': 'sk-test-key'}):
            parser = GPTParser()
            
            test_text = "MORTGAGOR: John Doe lives at 123 Main St, Minneapolis, MN 55401"
            result = parser.extract_notice_data(test_text, "http://test.com")
            
            # Verify extracted data
            self.assertEqual(result['first_name'], 'John')
            self.assertEqual(result['last_name'], 'Doe')
            self.assertEqual(result['street'], '123 Main St')
            self.assertEqual(result['city'], 'Minneapolis')
            self.assertEqual(result['state'], 'MN')
            self.assertEqual(result['zip'], '55401')
            self.assertEqual(result['date_filed'], '12/31/2024')
            self.assertEqual(result['plaintiff'], 'First National Bank')
            self.assertEqual(result['link'], 'http://test.com')
            
            # Verify API was called correctly
            mock_client.chat.completions.create.assert_called_once()
            call_args = mock_client.chat.completions.create.call_args
            self.assertEqual(call_args[1]['model'], 'gpt-3.5-turbo')
            self.assertEqual(call_args[1]['temperature'], 0.1)
            self.assertEqual(call_args[1]['max_tokens'], 300)
            
            # Verify stats
            self.assertEqual(parser.gpt_calls, 1)
            self.assertEqual(parser.regex_fallbacks, 0)
    
    @patch('gpt_parser.OpenAI')
    def test_extract_notice_data_gpt_api_error(self, mock_openai):
        """Should fallback to regex when GPT API fails"""
        # Setup mock OpenAI client that raises exception
        mock_client = Mock()
        mock_client.chat.completions.create.side_effect = Exception("API Error")
        mock_openai.return_value = mock_client
        
        with patch.dict(os.environ, {'OPENAI_API_KEY': 'sk-test-key'}):
            parser = GPTParser()
            
            test_text = "MORTGAGOR: Jane Smith, 456 Oak Ave, Minneapolis, MN 55402"
            result = parser.extract_notice_data(test_text, "http://test.com")
            
            # Should use regex fallback
            self.assertEqual(result['state'], 'MN')
            self.assertEqual(result['link'], 'http://test.com')
            self.assertEqual(parser.gpt_calls, 0)
            self.assertEqual(parser.regex_fallbacks, 1)
    
    @patch('gpt_parser.OpenAI')
    def test_extract_notice_data_invalid_json(self, mock_openai):
        """Should fallback to regex when GPT returns invalid JSON"""
        # Setup mock OpenAI client with invalid JSON response
        mock_client = Mock()
        mock_response = Mock()
        mock_choice = Mock()
        mock_message = Mock()
        mock_message.content = "This is not valid JSON"
        mock_choice.message = mock_message
        mock_response.choices = [mock_choice]
        mock_client.chat.completions.create.return_value = mock_response
        mock_openai.return_value = mock_client
        
        with patch.dict(os.environ, {'OPENAI_API_KEY': 'sk-test-key'}):
            parser = GPTParser()
            
            test_text = "MORTGAGOR: Bob Johnson"
            result = parser.extract_notice_data(test_text, "http://test.com")
            
            # Should fallback to regex
            self.assertEqual(result['state'], 'MN')
            self.assertEqual(result['link'], 'http://test.com')
            self.assertEqual(parser.regex_fallbacks, 1)
    
    @patch('gpt_parser.OpenAI')
    def test_extract_notice_data_empty_gpt_response(self, mock_openai):
        """Should fallback to regex when GPT returns empty/meaningless data"""
        # Setup mock OpenAI client with empty response
        mock_client = Mock()
        mock_response = Mock()
        mock_choice = Mock()
        mock_message = Mock()
        mock_message.content = '''
        {
            "first_name": "",
            "last_name": "",
            "street": "",
            "city": "",
            "zip": "",
            "date_filed": "",
            "plaintiff": ""
        }
        '''
        mock_choice.message = mock_message
        mock_response.choices = [mock_choice]
        mock_client.chat.completions.create.return_value = mock_response
        mock_openai.return_value = mock_client
        
        with patch.dict(os.environ, {'OPENAI_API_KEY': 'sk-test-key'}):
            parser = GPTParser()
            
            test_text = "MORTGAGOR: Alice Brown, 789 Pine St, Minneapolis, MN"
            result = parser.extract_notice_data(test_text, "http://test.com")
            
            # Should fallback to regex due to empty data
            self.assertEqual(parser.regex_fallbacks, 1)
    
    def test_clean_notice_text(self):
        """Should clean HTML and CSS artifacts from notice text"""
        parser = GPTParser()
        
        dirty_text = '''
        <html>
        <span style="display: none">hidden content</span>
        <div class="cssfontface">CSS artifact</div>
        <p>MORTGAGOR: John    Doe</p>
        <span>Multiple     spaces    here</span>
        </html>
        ''' + "x" * 4000  # Long text to test truncation
        
        cleaned = parser._clean_notice_text(dirty_text)
        
        # Should remove HTML tags
        self.assertNotIn('<html>', cleaned)
        self.assertNotIn('<span', cleaned)
        self.assertNotIn('<div', cleaned)
        self.assertNotIn('<p>', cleaned)
        
        # Should remove CSS artifacts and spans with display:none style
        self.assertNotIn('cssfontface', cleaned.lower())
        # The regex only removes spans with "display: none" style, not all spans
        # So "hidden content" should be removed but regular span content remains
        
        # Should normalize whitespace
        self.assertNotIn('    ', cleaned)  # No multiple spaces
        
        # Should be truncated to reasonable length
        self.assertLessEqual(len(cleaned), 3003)  # 3000 + "..."
        
        # Should contain actual content
        self.assertIn('MORTGAGOR: John Doe', cleaned)
        
        # Content from regular spans should remain (HTML removed but content kept)
        self.assertIn('Multiple spaces here', cleaned)
    
    def test_regex_fallback_name_extraction(self):
        """Should extract names using regex patterns"""
        parser = GPTParser()
        
        test_cases = [
            {
                'text': 'MORTGAGOR: John Doe',
                'expected_first': 'John',
                'expected_last': 'Doe'
            },
            {
                'text': 'DEBTOR(S): Jane Smith-Johnson',
                'expected_first': 'Jane',
                'expected_last': 'Smith-Johnson'
            },
            {
                'text': "MORTGAGOR: Mary O'Connor",
                'expected_first': 'Mary',
                'expected_last': "O'Connor"
            }
        ]
        
        for case in test_cases:
            result = parser._regex_fallback(case['text'], 'http://test.com', 'test')
            self.assertEqual(result['first_name'], case['expected_first'])
            self.assertEqual(result['last_name'], case['expected_last'])
    
    def test_regex_fallback_address_extraction(self):
        """Should extract addresses using regex patterns"""
        parser = GPTParser()
        
        test_text = "Property located at 123 Main Street, Minneapolis, MN 55401-1234"
        result = parser._regex_fallback(test_text, 'http://test.com', 'test')
        
        self.assertEqual(result['street'], '123 Main Street')
        self.assertEqual(result['city'], 'Minneapolis')
        self.assertEqual(result['zip'], '55401-1234')
        self.assertEqual(result['state'], 'MN')
    
    def test_regex_fallback_date_extraction(self):
        """Should extract dates using regex patterns"""
        parser = GPTParser()
        
        test_text = "Filed on 12/31/2024 in district court"
        result = parser._regex_fallback(test_text, 'http://test.com', 'test')
        
        self.assertEqual(result['date_filed'], '12/31/2024')
    
    def test_regex_fallback_plaintiff_extraction(self):
        """Should extract plaintiff using regex patterns"""
        parser = GPTParser()
        
        test_text = "MORTGAGEE: First National Bank of America"
        result = parser._regex_fallback(test_text, 'http://test.com', 'test')
        
        self.assertEqual(result['plaintiff'], 'First National Bank of America')
    
    def test_is_meaningful_data(self):
        """Should correctly identify meaningful vs empty data"""
        parser = GPTParser()
        
        # Meaningful data - has first name
        meaningful_data = {
            'first_name': 'John',
            'last_name': '',
            'street': ''
        }
        self.assertTrue(parser._is_meaningful_data(meaningful_data))
        
        # Meaningful data - has last name
        meaningful_data2 = {
            'first_name': '',
            'last_name': 'Doe',
            'street': '123 Main St'
        }
        self.assertTrue(parser._is_meaningful_data(meaningful_data2))
        
        # Empty data
        empty_data = {
            'first_name': '',
            'last_name': '',
            'street': '123 Main St'
        }
        self.assertFalse(parser._is_meaningful_data(empty_data))
    
    def test_get_stats(self):
        """Should return correct parsing statistics"""
        parser = GPTParser()
        parser.gpt_calls = 8
        parser.regex_fallbacks = 2
        
        stats = parser.get_stats()
        
        self.assertEqual(stats['total_parses'], 10)
        self.assertEqual(stats['gpt_successful'], 8)
        self.assertEqual(stats['regex_fallbacks'], 2)
        self.assertEqual(stats['gpt_success_rate'], 80.0)
    
    def test_get_stats_no_parses(self):
        """Should handle zero parses gracefully"""
        parser = GPTParser()
        parser.gpt_calls = 0
        parser.regex_fallbacks = 0
        
        stats = parser.get_stats()
        
        self.assertEqual(stats['total_parses'], 0)
        self.assertEqual(stats['gpt_success_rate'], 0)
    
    def test_convenience_functions(self):
        """Should test module-level convenience functions"""
        # Test extract_notice_data_gpt function
        with patch('gpt_parser.gpt_parser') as mock_parser:
            mock_parser.extract_notice_data.return_value = {'test': 'data'}
            
            result = extract_notice_data_gpt("test text", "http://test.com")
            
            mock_parser.extract_notice_data.assert_called_once_with("test text", "http://test.com")
            self.assertEqual(result, {'test': 'data'})
        
        # Test get_parsing_stats function
        with patch('gpt_parser.gpt_parser') as mock_parser:
            mock_parser.get_stats.return_value = {'stats': 'data'}
            
            result = get_parsing_stats()
            
            mock_parser.get_stats.assert_called_once()
            self.assertEqual(result, {'stats': 'data'})


class TestIntegrationScenarios(unittest.TestCase):
    """Integration tests for complex scenarios"""
    
    def test_full_gpt_to_regex_fallback_flow(self):
        """Should demonstrate complete GPT→regex fallback workflow"""
        test_notice = '''
        <html><body>
        <span class="cssfontface">CSS JUNK</span>
        <div>MORTGAGOR: John Smith</div>
        <div>Property: 456 Oak Street, Minneapolis, MN 55403</div>
        <div>MORTGAGEE: Wells Fargo Bank</div>
        <div>Filed: 01/15/2024</div>
        </body></html>
        '''
        
        # Test with GPT disabled (should use regex)
        parser = GPTParser()
        parser.enabled = False
        
        result = parser.extract_notice_data(test_notice, "http://example.com/notice123")
        
        # Verify basic structure
        self.assertEqual(result['state'], 'MN')
        self.assertEqual(result['link'], 'http://example.com/notice123')
        
        # Should have used regex fallback
        stats = parser.get_stats()
        self.assertEqual(stats['regex_fallbacks'], 1)
        self.assertEqual(stats['gpt_successful'], 0)


if __name__ == '__main__':
    # Run with verbose output
    unittest.main(verbosity=2)