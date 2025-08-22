#!/usr/bin/env python3
"""
MN Public Notice Scraper - Selenium Version
Scrapes foreclosure and bankruptcy notices from mnpublicnotice.com using browser automation
"""

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import TimeoutException, NoSuchElementException
import csv
import re
from datetime import datetime, timedelta
import time
import logging
import os
import glob

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class MNNoticeScraperSelenium:
    def __init__(self, headless=False):
        self.setup_driver(headless)
        self.base_url = "https://www.mnpublicnotice.com"
        self.search_url = f"{self.base_url}/Search.aspx"
        self.results = []
        self.captcha_skipped = 0
        
    def setup_driver(self, headless=False):
        """Setup Chrome driver with options"""
        chrome_options = Options()
        if headless:
            chrome_options.add_argument("--headless")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--window-size=1920,1080")
        
        try:
            self.driver = webdriver.Chrome(options=chrome_options)
            self.wait = WebDriverWait(self.driver, 10)
        except Exception as e:
            logger.error(f"Failed to setup Chrome driver: {e}")
            logger.info("Make sure you have ChromeDriver installed")
            raise
    
    def search_notices(self, keyword, days_back=1):
        """Navigate to search page and perform search"""
        logger.info(f"Searching for '{keyword}' in last {days_back} days")
        
        # Navigate to search page
        self.driver.get(self.search_url)
        
        # Wait for page to fully load
        self.wait.until(EC.presence_of_element_located((By.TAG_NAME, "form")))
        
        # Additional wait for JavaScript to finish loading
        time.sleep(3)
        logger.info("Page loaded, waiting for elements to be interactive")
        
        # Set date range
        end_date = datetime.now()
        if days_back == 1:
            start_date = end_date  # Same day search
        else:
            start_date = end_date - timedelta(days=days_back)
        
        # Fill in keyword field
        try:
            # Wait for keyword field to be clickable
            keyword_field = self.wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "input[type='text']")))
            keyword_field.clear()  # Clear any existing content
            keyword_field.send_keys(keyword)
            logger.info(f"Entered keyword(s): {keyword}")
        except TimeoutException:
            logger.warning("Keyword field not found or not clickable within timeout")
        except Exception as e:
            logger.warning(f"Error with keyword field: {e}")
        
        # Set "Any Words" radio button BEFORE clicking Go
        try:
            # Wait for radio button to be present
            any_words_radio = self.wait.until(EC.presence_of_element_located((By.ID, "ctl00_ContentPlaceHolder1_as1_rdoType_1")))
            
            # Check if it's already selected
            if any_words_radio.is_selected():
                logger.info("'Any Words' option already selected")
            else:
                # If not selected, use JavaScript to click it (more reliable for radio buttons)
                self.driver.execute_script("arguments[0].scrollIntoView(true);", any_words_radio)
                time.sleep(1)
                self.driver.execute_script("arguments[0].click();", any_words_radio)
                logger.info("Selected 'Any Words' option using JavaScript")
                
                # Wait for any loading/postback to complete after radio button change
                time.sleep(3)
                logger.info("Waiting for page to stabilize after radio button change")
                
        except TimeoutException:
            logger.warning("'Any Words' radio button not found within timeout")
        except Exception as e:
            logger.warning(f"Error with 'Any Words' radio button: {e}")
        
        # Fill date fields
        try:
            # First, click to open the date range selector
            date_range_div = self.wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "#ctl00_ContentPlaceHolder1_as1_divDateRange")))
            self.driver.execute_script("arguments[0].scrollIntoView(true);", date_range_div)
            time.sleep(1)
            date_range_div.click()
            logger.info("Opened date range selector")
            
            # Wait for date fields to become visible after opening and any loading to complete
            time.sleep(3)
            logger.info("Waiting for date range selector to fully load")
            
            # Toggle the range radio button
            try:
                range_radio = self.wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "#ctl00_ContentPlaceHolder1_as1_rbRange")))
                range_radio.click()
                logger.info("Selected range radio button")
                time.sleep(1)
            except Exception as e:
                logger.warning(f"Error clicking range radio button: {e}")
            
            # Look for date input fields
            date_inputs = self.driver.find_elements(By.CSS_SELECTOR, "input[type='text']")
            for input_field in date_inputs:
                try:
                    # Check if element is interactable
                    if not input_field.is_displayed() or not input_field.is_enabled():
                        continue
                        
                    field_name = input_field.get_attribute("name") or ""
                    field_id = input_field.get_attribute("id") or ""
                    
                    if "from" in field_name.lower() or "from" in field_id.lower():
                        # Scroll to element and wait
                        self.driver.execute_script("arguments[0].scrollIntoView(true);", input_field)
                        time.sleep(1)
                        
                        # Wait for element to be clickable
                        self.wait.until(EC.element_to_be_clickable(input_field))
                        input_field.clear()
                        input_field.send_keys(start_date.strftime("%m/%d/%Y"))
                        logger.info(f"Set from date: {start_date.strftime('%m/%d/%Y')}")
                        
                    elif "to" in field_name.lower() or "to" in field_id.lower():
                        # Scroll to element and wait
                        self.driver.execute_script("arguments[0].scrollIntoView(true);", input_field)
                        time.sleep(1)
                        
                        # Wait for element to be clickable
                        self.wait.until(EC.element_to_be_clickable(input_field))
                        input_field.clear()
                        input_field.send_keys(end_date.strftime("%m/%d/%Y"))
                        logger.info(f"Set to date: {end_date.strftime('%m/%d/%Y')}")
                        
                except Exception as field_error:
                    logger.warning(f"Error with individual date field: {field_error}")
                    continue
                    
        except Exception as e:
            logger.warning(f"Error setting date fields: {e}")
        
        # Click search button LAST
        try:
            # Wait for Go button to be clickable
            search_button = self.wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "#ctl00_ContentPlaceHolder1_as1_btnGo")))
            logger.info("Found Go button")
            
            # Scroll to button and make sure it's visible
            self.driver.execute_script("arguments[0].scrollIntoView(true);", search_button)
            time.sleep(1)
            
            # Try clicking with JavaScript if regular click fails
            try:
                search_button.click()
                logger.info("Clicked Go button")
            except Exception as e:
                logger.warning(f"Regular click failed, trying JavaScript click: {e}")
                self.driver.execute_script("arguments[0].click();", search_button)
                logger.info("Clicked Go button with JavaScript")
            
            # Wait for results to load
            time.sleep(5)
            
        except TimeoutException:
            logger.error("Search button not clickable within timeout")
            return False
        except Exception as e:
            logger.error(f"Error clicking search button: {e}")
            return False
        
        return True
    
    def get_view_buttons(self):
        """Find all view buttons on the current page"""
        try:
            view_buttons = self.driver.find_elements(By.CLASS_NAME, "viewButton")
            logger.info(f"Found {len(view_buttons)} view buttons")
            return view_buttons
        except Exception as e:
            logger.error(f"Error finding view buttons: {e}")
            return []
    
    def click_view_button(self, button):
        """Click a view button and return the resulting page source"""
        try:
            # Scroll button into view
            self.driver.execute_script("arguments[0].scrollIntoView(true);", button)
            time.sleep(1)
            
            # Click the button
            button.click()
            
            # Wait for page to load
            time.sleep(2)
            
            return True
            
        except Exception as e:
            logger.error(f"Error clicking view button: {e}")
            return False
    
    def check_for_captcha(self):
        """Check if current page has a captcha"""
        try:
            page_source = self.driver.page_source
            
            # Check for reCAPTCHA elements
            if "You must complete the reCAPTCHA" in page_source:
                logger.warning("reCAPTCHA detected - MN Public Notice captcha page")
                return True
            
            # Check for reCAPTCHA iframe or div
            recaptcha_elements = self.driver.find_elements(By.CSS_SELECTOR, "[id*='recaptcha'], [class*='recaptcha']")
            if recaptcha_elements:
                logger.warning("reCAPTCHA elements found")
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Error checking for captcha: {e}")
            return False
    
    def extract_notice_data(self, source_url=""):
        """Extract required fields from current page"""
        data = {
            'first_name': '',
            'last_name': '',
            'street': '',
            'city': '',
            'state': 'MN',
            'zip': '',
            'date_filed': '',
            'plaintiff': '',
            'link': source_url
        }
        
        try:
            page_text = self.driver.page_source
            
            # Extract name using flexible patterns for legal notices
            name_patterns = [
                r'(?:MORTGAGOR|DEBTOR|DEFENDANT)(?:\(S\))?:\s*([A-Z][a-zA-Z\'\-\.]+)\s+([A-Z][a-zA-Z\'\-\.]+)',
                r'(?:vs?\.?|versus)\s+([A-Z][a-zA-Z\'\-\.]+)\s+([A-Z][a-zA-Z\'\-\.]+)',
                r'([A-Z][a-zA-Z\'\-\.]+)\s+([A-Z][a-zA-Z\'\-\.]+),?\s+(?:vs?\.?|versus)',
                r'([A-Z][a-zA-Z\'\-\.]+)\s+([A-Z][a-zA-Z\'\-\.]+)(?:,?\s+(?:and|&))',
                r'(?:Defendant|Debtor)s?:\s*([A-Z][a-zA-Z\'\-\.]+)\s+([A-Z][a-zA-Z\'\-\.]+)',
                r'([A-Z][a-zA-Z\'\-\.]+)\s+([A-Z][a-zA-Z\'\-\.]+),?\s+(?:Defendant|Debtor)',
            ]
            
            for pattern in name_patterns:
                match = re.search(pattern, page_text, re.IGNORECASE)
                if match:
                    data['first_name'] = match.group(1).strip()
                    data['last_name'] = match.group(2).strip()
                    break
            
            # Extract address - flexible patterns for Minnesota
            address_patterns = [
                r'(?:PROPERTY\s+ADDRESS|ADDRESS|LOCATED\s+AT|PREMISES):\s*(\d+[^,\n]+?),\s*([^,\n]+?),\s*(?:MN|Minnesota)\s*(\d{5}(?:-\d{4})?)',
                r'(\d+\s+[A-Za-z0-9\s\#\.\-]+?),\s*([A-Za-z\s]+?),\s*(?:MN|Minnesota)\s*(\d{5}(?:-\d{4})?)',
                r'(?:situated|located)(?:\s+at)?:?\s*(\d+[^,\n]+?),\s*([^,\n]+?),\s*(?:MN|Minnesota)\s*(\d{5}(?:-\d{4})?)',
            ]
            
            for pattern in address_patterns:
                match = re.search(pattern, page_text, re.IGNORECASE)
                if match:
                    data['street'] = match.group(1).strip()
                    data['city'] = match.group(2).strip()
                    data['zip'] = match.group(3).strip()
                    break
            
            # Extract date filed - flexible patterns
            date_patterns = [
                r'(?:Filed|Recorded|Entered)(?:\s+on)?\s+([A-Z][a-z]+\s+\d{1,2},\s+\d{4})',
                r'(?:Filed|Date\s+Filed|Filed\s+on|Recorded|Date):\s*(\d{1,2}/\d{1,2}/\d{4})',
                r'(?:Filed|Date\s+Filed|Filed\s+on|Recorded|Date):\s*([A-Z][a-z]+\s+\d{1,2},\s+\d{4})',
                r'(\d{1,2}/\d{1,2}/\d{4})',
                r'([A-Z][a-z]+\s+\d{1,2},\s+\d{4})',
            ]
            
            for pattern in date_patterns:
                match = re.search(pattern, page_text)
                if match:
                    data['date_filed'] = match.group(1)
                    break
            
            # Extract plaintiff/creditor - flexible patterns
            plaintiff_patterns = [
                r'(?:Assignee\s+of\s+Mortgagee|Current\s+Holder|Servicer|Lender)(?:[^:]*)?:\s*([^,\n<]+)',
                r'(?:MORTGAGEE|CREDITOR|PLAINTIFF|LENDER):\s*([^,\n<]+)',
                r'(?:Plaintiff|Creditor|Petitioner)(?:\(s\))?:\s*([^,\n]+)',
                r'([^,\n\vs]+?)\s+(?:vs?\.?|versus)',
                r'([A-Z][A-Za-z\s]+?(?:Bank|Credit|Financial|Corp|Inc|LLC|Company|Fund|Trust|Association)[^,\n]*)',
            ]
            
            for pattern in plaintiff_patterns:
                match = re.search(pattern, page_text, re.IGNORECASE)
                if match:
                    plaintiff = match.group(1).strip()
                    plaintiff = re.sub(r'\s+', ' ', plaintiff)
                    data['plaintiff'] = plaintiff
                    break
            
        except Exception as e:
            logger.error(f"Error extracting notice data: {e}")
        
        return data
    
    def scrape_notices(self, keywords=['foreclosure', 'bankruptcy'], days_back=1):
        """Main scraping function"""
        logger.info(f"Starting scrape for keywords: {keywords}")
        
        # Combine keywords into single search
        combined_keywords = ' '.join(keywords)
        
        try:
            # Perform single search with all keywords
            if not self.search_notices(combined_keywords, days_back):
                logger.error(f"Search failed for keywords: {combined_keywords}")
                return
            
            # Get view buttons
            view_buttons = self.get_view_buttons()
            logger.info(f"Found {len(view_buttons)} view buttons for '{combined_keywords}'")
            
            # Process each view button by index (to avoid stale element issues)
            for i in range(len(view_buttons)):
                logger.info(f"Processing notice {i+1}/{len(view_buttons)}")
                
                # Re-find view buttons to avoid stale element reference
                current_view_buttons = self.get_view_buttons()
                if i >= len(current_view_buttons):
                    logger.warning(f"View button {i+1} no longer exists")
                    break
                
                button = current_view_buttons[i]
                
                # Click view button
                if not self.click_view_button(button):
                    logger.warning(f"Failed to click view button {i+1}")
                    continue
                
                # Check for captcha
                if self.check_for_captcha():
                    logger.warning(f"Captcha detected on notice {i+1} - skipping for now")
                    self.captcha_skipped += 1
                    self.driver.back()  # Go back to search results
                    time.sleep(2)
                    continue
                
                # Extract data
                current_url = self.driver.current_url
                data = self.extract_notice_data(current_url)
                
                # Add all notices, even if incomplete
                self.results.append(data)
                if data['first_name'] and data['last_name']:
                    logger.info(f"Extracted: {data['first_name']} {data['last_name']}")
                else:
                    logger.info(f"Extracted notice with incomplete name data")
                
                # Go back to search results
                self.driver.back()
                time.sleep(2)
            
        except Exception as e:
            logger.error(f"Error scraping keywords '{combined_keywords}': {e}")
    
    def save_to_csv(self, filename=None):
        """Save results to CSV file in csvs folder, keeping only one file"""
        # Create csvs directory if it doesn't exist
        csvs_dir = "csvs"
        if not os.path.exists(csvs_dir):
            os.makedirs(csvs_dir)
            logger.info(f"Created {csvs_dir} directory")
        
        # Remove any existing CSV files in the csvs folder
        existing_csvs = glob.glob(os.path.join(csvs_dir, "*.csv"))
        for csv_file in existing_csvs:
            try:
                os.remove(csv_file)
                logger.info(f"Removed old CSV file: {csv_file}")
            except Exception as e:
                logger.warning(f"Could not remove {csv_file}: {e}")
        
        # Generate new filename
        if not filename:
            filename = f"mn_notices_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        
        # Full path to csvs folder
        full_path = os.path.join(csvs_dir, filename)
        
        fieldnames = ['first_name', 'last_name', 'street', 'city', 'state', 'zip', 'date_filed', 'plaintiff', 'link']
        
        with open(full_path, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(self.results)
        
        logger.info(f"Saved {len(self.results)} records to {full_path}")
        return full_path
    
    def close(self):
        """Close the browser"""
        if hasattr(self, 'driver'):
            self.driver.quit()

def main():
    scraper = None
    try:
        scraper = MNNoticeScraperSelenium(headless=False)  # Set to True for headless mode
        scraper.scrape_notices(['foreclosure', 'bankruptcy'], days_back=1)
        filename = scraper.save_to_csv()
        print(f"Scraping complete. Results saved to: {filename}")
        print(f"Total records extracted: {len(scraper.results)}")
        print(f"Notices skipped due to captcha: {scraper.captcha_skipped}")
    except Exception as e:
        logger.error(f"Scraper failed: {e}")
    finally:
        if scraper:
            scraper.close()

if __name__ == "__main__":
    main()