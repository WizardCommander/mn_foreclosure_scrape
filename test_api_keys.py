#!/usr/bin/env python3
"""
API key validation script for MN Public Notice Scraper
"""

import os
from dotenv import load_dotenv

def main():
    # Load environment variables
    load_dotenv()
    
    # Test 2captcha key
    captcha_key = os.getenv('TWO_CAPTCHA_API_KEY')
    if not captcha_key or len(captcha_key) < 10:
        print('Warning: 2captcha API key appears invalid')
    else:
        print('2captcha API key format looks good')
    
    # Test OpenAI key  
    openai_key = os.getenv('OPENAI_API_KEY')
    if not openai_key or not openai_key.startswith('sk-'):
        print('Warning: OpenAI API key appears invalid')
    else:
        print('OpenAI API key format looks good')

if __name__ == '__main__':
    main()