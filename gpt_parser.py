#!/usr/bin/env python3
"""
GPT-based text parser for extracting structured data from public notices
"""

import json
import os
import logging
import re
from typing import Dict, Optional

logger = logging.getLogger(__name__)

# Load environment variables
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Python 3.13 compatibility fix for collections
import collections
try:
    collections.MutableSet
except AttributeError:
    import collections.abc
    collections.MutableSet = collections.abc.MutableSet
    collections.MutableMapping = collections.abc.MutableMapping

# Try to import OpenAI
try:
    from openai import OpenAI
    HAS_OPENAI = True
    logger.info("OpenAI library loaded successfully")
except ImportError:
    HAS_OPENAI = False
    logger.warning("OpenAI library not installed - GPT parsing will be skipped")

class GPTParser:
    def __init__(self):
        self.client = None
        self.enabled = False
        self.gpt_calls = 0
        self.regex_fallbacks = 0
        
        if HAS_OPENAI:
            api_key = os.getenv('OPENAI_API_KEY')
            if api_key:
                try:
                    self.client = OpenAI(api_key=api_key)
                    self.enabled = True
                    logger.info("GPT parser initialized successfully")
                except Exception as e:
                    logger.error(f"Failed to initialize OpenAI client: {e}")
            else:
                logger.warning("OPENAI_API_KEY not found in environment variables")
    
    def extract_notice_data(self, notice_text: str, source_url: str = "") -> Dict[str, str]:
        """
        Extract structured data from notice text using GPT
        """
        if not self.enabled:
            logger.debug("🔄 GPT parser not enabled, using regex fallback")
            self.regex_fallbacks += 1
            return self._regex_fallback(notice_text, source_url, reason="GPT disabled")
        
        try:
            # Clean the notice text
            cleaned_text = self._clean_notice_text(notice_text)
            
            # Create prompt for GPT
            prompt = self._create_extraction_prompt(cleaned_text)
            
            # Call GPT API
            logger.debug("🤖 Calling GPT for text parsing...")
            response = self.client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "You are a legal document parser that extracts structured information from foreclosure and bankruptcy notices."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=300,
                temperature=0.1
            )
            
            self.gpt_calls += 1
            
            # Parse response
            result_text = response.choices[0].message.content.strip()
            parsed_data = self._parse_gpt_response(result_text, source_url)
            
            # Check if GPT parsing was successful
            if self._is_meaningful_data(parsed_data):
                logger.debug("✅ GPT parsing successful")
                
                # Add regex-extracted date to GPT results
                regex_date = self._extract_date_with_regex(notice_text)
                if regex_date:
                    parsed_data['date_of_sale'] = regex_date
                    logger.info(f"🗓️  REGEX found date_of_sale: '{regex_date}'")
                else:
                    logger.info("🗓️  REGEX could not find date of sale")
                
                return parsed_data
            else:
                logger.warning("⚠️ GPT returned empty/invalid data, using regex fallback")
                self.regex_fallbacks += 1
                return self._regex_fallback(notice_text, source_url, reason="GPT returned empty data")
            
        except Exception as e:
            logger.warning(f"❌ GPT parsing failed: {e}, using regex fallback")
            self.regex_fallbacks += 1
            return self._regex_fallback(notice_text, source_url, reason=f"GPT error: {str(e)}")
    
    def _is_meaningful_data(self, data: Dict[str, str]) -> bool:
        """Check if parsed data contains meaningful information"""
        # At least first name or last name should be present
        return bool(data.get('first_name') or data.get('last_name'))
    
    def _extract_date_with_regex(self, text: str) -> str:
        """Extract date of sale using regex patterns"""
        # Pattern for "DATE AND TIME OF SALE: September 23, 2025" format
        patterns = [
            r'DATE\s+(?:AND\s+TIME\s+)?OF\s+SALE:?\s*([A-Za-z]+ \d{1,2}, \d{4})',
            r'DATE\s+(?:AND\s+TIME\s+)?OF\s+SALE:?\s*(\d{1,2}[/-]\d{1,2}[/-]\d{4})',
            r'DATE\s+(?:AND\s+TIME\s+)?OF\s+SALE:?\s*(\d{4}[/-]\d{1,2}[/-]\d{1,2})',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(1).strip()
        
        return ""
    
    def _clean_notice_text(self, text: str) -> str:
        """Clean notice text for GPT processing"""
        # Remove HTML tags
        text = re.sub(r'<[^>]+>', '', text)
        
        # Remove CSS artifacts and hidden spans
        text = re.sub(r'<span[^>]*display:\s*none[^>]*>.*?</span>', '', text, flags=re.DOTALL)
        text = re.sub(r'cssfontface|csstransitions|fontface', '', text, flags=re.IGNORECASE)
        
        # Clean up whitespace
        text = re.sub(r'\s+', ' ', text)
        
        # Limit length for API efficiency
        if len(text) > 3000:
            text = text[:3000] + "..."
        
        return text.strip()
    
    def _create_extraction_prompt(self, text: str) -> str:
        """Create prompt for GPT to extract data"""
        return f"""
Extract the following information from this foreclosure/bankruptcy notice and return ONLY a JSON object:

TEXT:
{text}

Extract these fields:
- first_name: The debtor/mortgagor's first name
- last_name: The debtor/mortgagor's last name  
- street: Property street address (number and street name)
- city: Property city
- zip: Property ZIP code
- plaintiff: The creditor/bank/financial institution name

Return ONLY valid JSON in this exact format:
{{
    "first_name": "John",
    "last_name": "Doe", 
    "street": "123 Main St",
    "city": "Minneapolis",
    "zip": "55401",
    "plaintiff": "First National Bank"
}}

If a field cannot be found, use an empty string "".
"""

    def _parse_gpt_response(self, response_text: str, source_url: str) -> Dict[str, str]:
        """Parse GPT response into structured data"""
        try:
            # Try to extract JSON from response
            json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
            if json_match:
                json_str = json_match.group(0)
                data = json.loads(json_str)
                
                # Ensure all required fields exist (no date - handled by regex)
                result = {
                    'first_name': str(data.get('first_name', '')).strip(),
                    'last_name': str(data.get('last_name', '')).strip(),
                    'street': str(data.get('street', '')).strip(),
                    'city': str(data.get('city', '')).strip(),
                    'state': 'MN',  # Always MN for this scraper
                    'zip': str(data.get('zip', '')).strip(),
                    'date_of_sale': '',  # Will be filled by regex
                    'plaintiff': str(data.get('plaintiff', '')).strip(),
                    'link': source_url
                }
                
                return result
                
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse GPT JSON response: {e}")
        
        # If JSON parsing fails, return empty data
        return self._empty_data_structure(source_url)
    
    def _regex_fallback(self, text: str, source_url: str, reason: str = "Unknown") -> Dict[str, str]:
        """Fallback regex parsing (simplified version of original)"""
        logger.info(f"🔄 Using regex fallback parsing (Reason: {reason})")
        data = self._empty_data_structure(source_url)
        
        try:
            # Simple name extraction
            name_pattern = r'(?:MORTGAGOR|DEBTOR)(?:\(S\))?:\s*([A-Z][a-zA-Z\'\-\.]+)\s+([A-Z][a-zA-Z\'\-\.]+)'
            match = re.search(name_pattern, text, re.IGNORECASE)
            if match:
                data['first_name'] = match.group(1).strip()
                data['last_name'] = match.group(2).strip()
                logger.debug(f"📝 Regex found name: {data['first_name']} {data['last_name']}")
            else:
                logger.debug("📝 Regex could not find name")
            
            # Simple address extraction
            address_pattern = r'(\d+\s+[A-Za-z0-9\s\#\.\-]+?),\s*([A-Za-z\s]+?),\s*(?:MN|Minnesota)\s*(\d{5}(?:-\d{4})?)'
            match = re.search(address_pattern, text, re.IGNORECASE)
            if match:
                data['street'] = match.group(1).strip()
                data['city'] = match.group(2).strip() 
                data['zip'] = match.group(3).strip()
                logger.debug(f"📝 Regex found address: {data['street']}, {data['city']} {data['zip']}")
            else:
                logger.debug("📝 Regex could not find address")
            
            # Extract date of sale from "DATE AND TIME OF SALE:" pattern
            # Look for patterns like "DATE AND TIME OF SALE: September 23, 2025 at 10:00 AM"
            date_of_sale_pattern = r'DATE\s+(?:AND\s+TIME\s+)?OF\s+SALE:?\s*([A-Za-z]+ \d{1,2}, \d{4})'
            match = re.search(date_of_sale_pattern, text, re.IGNORECASE)
            if match:
                data['date_of_sale'] = match.group(1)
                logger.info(f"🗓️  REGEX found date of sale: '{data['date_of_sale']}'")
            else:
                # Fallback to simple date pattern
                date_pattern = r'(\d{1,2}/\d{1,2}/\d{4})'
                match = re.search(date_pattern, text)
                if match:
                    data['date_of_sale'] = match.group(1)
                    logger.info(f"🗓️  REGEX fallback date: '{data['date_of_sale']}'")
                else:
                    logger.info("🗓️  REGEX could not find any date of sale")
                
            # Simple plaintiff extraction
            plaintiff_pattern = r'(?:MORTGAGEE|CREDITOR|PLAINTIFF):\s*([^,\n<]+)'
            match = re.search(plaintiff_pattern, text, re.IGNORECASE)
            if match:
                data['plaintiff'] = match.group(1).strip()
                logger.debug(f"📝 Regex found plaintiff: {data['plaintiff']}")
            else:
                logger.debug("📝 Regex could not find plaintiff")
                
        except Exception as e:
            logger.warning(f"❌ Regex fallback parsing error: {e}")
        
        return data
    
    def _empty_data_structure(self, source_url: str) -> Dict[str, str]:
        """Return empty data structure"""
        return {
            'first_name': '',
            'last_name': '',
            'street': '',
            'city': '',
            'state': 'MN',
            'zip': '',
            'date_of_sale': '',
            'plaintiff': '',
            'link': source_url
        }
    
    def get_stats(self) -> Dict[str, int]:
        """Get parsing statistics"""
        total_calls = self.gpt_calls + self.regex_fallbacks
        return {
            'total_parses': total_calls,
            'gpt_successful': self.gpt_calls,
            'regex_fallbacks': self.regex_fallbacks,
            'gpt_success_rate': round((self.gpt_calls / total_calls * 100) if total_calls > 0 else 0, 1)
        }

# Global instance
gpt_parser = GPTParser()

def extract_notice_data_gpt(notice_text: str, source_url: str = "") -> Dict[str, str]:
    """
    Convenience function for extracting notice data using GPT
    """
    return gpt_parser.extract_notice_data(notice_text, source_url)

def get_parsing_stats() -> Dict[str, int]:
    """
    Get parsing statistics
    """
    return gpt_parser.get_stats()