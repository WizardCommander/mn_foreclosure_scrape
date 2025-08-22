#!/usr/bin/env python3
"""
MN Public Notice Scraper - Clean Version
Scrapes foreclosure and bankruptcy notices from mnpublicnotice.com
"""

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import Select
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

class MNNoticeScraperClean:
    def __init__(self, headless=False):
        self.setup_driver(headless)
        self.base_url = "https://www.mnpublicnotice.com"
        self.search_url = f"{self.base_url}/Search.aspx"
        self.results = []
        self.captcha_solved = 0
        self.captcha_skipped = 0
        
    def setup_driver(self, headless=False):
        """Setup Chrome driver with minimal options"""
        chrome_options = Options()
        if headless:
            chrome_options.add_argument("--headless")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--window-size=1920,1080")
        chrome_options.add_experimental_option("useAutomationExtension", False)
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        
        try:
            self.driver = webdriver.Chrome(options=chrome_options)
            self.wait = WebDriverWait(self.driver, 10)
        except Exception as e:
            logger.error(f"Failed to setup Chrome driver: {e}")
            raise
    
    def search_notices(self, keyword, days_back=1):
        """Navigate to search page and perform search"""
        logger.info(f"Searching for '{keyword}' in last {days_back} days")
        
        # Navigate to search page
        self.driver.get(self.search_url)
        
        # Wait for page to fully load
        self.wait.until(EC.presence_of_element_located((By.TAG_NAME, "form")))
        time.sleep(3)
        
        # Set date range
        end_date = datetime.now()
        if days_back == 1:
            start_date = end_date  # Same day search
        else:
            start_date = end_date - timedelta(days=days_back)
        
        # Fill in keyword field
        try:
            keyword_field = self.wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "input[type='text']")))
            keyword_field.clear()
            keyword_field.send_keys(keyword)
            logger.info(f"Entered keyword(s): {keyword}")
        except Exception as e:
            logger.warning(f"Error with keyword field: {e}")
        
        # Set "Any Words" radio button
        try:
            any_words_radio = self.wait.until(EC.presence_of_element_located((By.ID, "ctl00_ContentPlaceHolder1_as1_rdoType_1")))
            if not any_words_radio.is_selected():
                self.driver.execute_script("arguments[0].click();", any_words_radio)
                logger.info("Selected 'Any Words' option")
                time.sleep(3)  # Wait for postback
        except Exception as e:
            logger.warning(f"Error with 'Any Words' radio button: {e}")
        
        # Fill date fields
        try:
            # Open date range selector
            date_range_div = self.wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "#ctl00_ContentPlaceHolder1_as1_divDateRange")))
            date_range_div.click()
            time.sleep(3)
            
            # Select range radio button
            range_radio = self.wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "#ctl00_ContentPlaceHolder1_as1_rbRange")))
            range_radio.click()
            time.sleep(1)
            
            # Fill date inputs
            date_inputs = self.driver.find_elements(By.CSS_SELECTOR, "input[type='text']")
            for input_field in date_inputs:
                if not input_field.is_displayed() or not input_field.is_enabled():
                    continue
                    
                field_name = input_field.get_attribute("name") or ""
                field_id = input_field.get_attribute("id") or ""
                
                if "from" in field_name.lower() or "from" in field_id.lower():
                    input_field.clear()
                    input_field.send_keys(start_date.strftime("%m/%d/%Y"))
                    logger.info(f"Set from date: {start_date.strftime('%m/%d/%Y')}")
                elif "to" in field_name.lower() or "to" in field_id.lower():
                    input_field.clear()
                    input_field.send_keys(end_date.strftime("%m/%d/%Y"))
                    logger.info(f"Set to date: {end_date.strftime('%m/%d/%Y')}")
                    
        except Exception as e:
            logger.warning(f"Error setting date fields: {e}")
        
        # Click search button
        try:
            search_button = self.wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "#ctl00_ContentPlaceHolder1_as1_btnGo")))
            search_button.click()
            logger.info("Clicked Go button")
            time.sleep(5)  # Wait for results
            return True
        except Exception as e:
            logger.error(f"Error clicking search button: {e}")
            return False
    
    def set_results_per_page(self, per_page=50):
        """Set results per page AFTER search results appear"""
        try:
            results_dropdown_selector = "#ctl00_ContentPlaceHolder1_WSExtendedGridNP1_GridView1_ctl01_ddlPerPage"
            results_dropdown = self.wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, results_dropdown_selector)))
            
            select = Select(results_dropdown)
            current_selection = select.first_selected_option.get_attribute('value')
            if current_selection == str(per_page):
                logger.info(f"Results per page already set to {per_page}")
                return True
            
            select.select_by_value(str(per_page))
            logger.info(f"Set results per page to {per_page}")
            time.sleep(5)  # Wait for page reload
            return True
            
        except Exception as e:
            logger.warning(f"Error setting results per page to {per_page}: {e}")
            return False
    
    def get_view_buttons(self):
        """Find all view buttons on the current page - only from results table"""
        try:
            # Use specific selector for view buttons inside the results table
            view_buttons = self.driver.find_elements(
                By.CSS_SELECTOR, 
                "#ctl00_ContentPlaceHolder1_WSExtendedGridNP1_GridView1 .viewButton"
            )
            
            # Debug: also check total viewButton count
            all_view_buttons = self.driver.find_elements(By.CLASS_NAME, "viewButton")
            logger.info(f"Found {len(view_buttons)} view buttons in results table, {len(all_view_buttons)} total on page")
            
            # Only return the ones from the results table
            return view_buttons
        except Exception as e:
            logger.error(f"Error finding view buttons: {e}")
            return []
    
    def check_for_captcha(self):
        """Check if current page has a captcha"""
        page_source = self.driver.page_source
        return "You must complete the reCAPTCHA" in page_source
    
    def solve_captcha_simple(self):
        """Solve captcha by clicking checkbox and View Notice button"""
        try:
            logger.info("Attempting to solve reCAPTCHA...")
            
            # Find reCAPTCHA iframe
            iframes = self.driver.find_elements(By.CSS_SELECTOR, "#recaptcha iframe")
            
            for iframe in iframes:
                try:
                    self.driver.switch_to.frame(iframe)
                    
                    # Find and click checkbox
                    checkbox_selectors = ["#recaptcha-anchor", ".rc-anchor-checkbox", "span[role='checkbox']"]
                    
                    for selector in checkbox_selectors:
                        try:
                            checkbox = self.driver.find_element(By.CSS_SELECTOR, selector)
                            if checkbox.is_displayed():
                                checkbox.click()
                                logger.info("Clicked reCAPTCHA checkbox")
                                break
                        except:
                            continue
                    
                    # Switch back to main content
                    self.driver.switch_to.default_content()
                    time.sleep(3)
                    
                    # Click View Notice button
                    view_notice_btn = self.wait.until(
                        EC.element_to_be_clickable((By.ID, "ctl00_ContentPlaceHolder1_PublicNoticeDetailsBody1_btnViewNotice"))
                    )
                    view_notice_btn.click()
                    logger.info("Clicked 'View Notice' button")
                    time.sleep(3)
                    
                    # Check if captcha solved
                    if "You must complete the reCAPTCHA" not in self.driver.page_source:
                        logger.info("Successfully solved captcha!")
                        self.captcha_solved += 1
                        return True
                    
                except Exception as e:
                    self.driver.switch_to.default_content()
                    continue
            
            return False
            
        except Exception as e:
            logger.error(f"Error solving captcha: {e}")
            self.driver.switch_to.default_content()
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
            
            # Extract name
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
            
            # Extract address
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
            
            # Extract date filed
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
            
            # Extract plaintiff/creditor
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
    
    def navigate_back_to_results(self):
        """Navigate back to search results page"""
        try:
            # Look for "Back" link or use browser back
            back_links = self.driver.find_elements(By.LINK_TEXT, "Back")
            if back_links:
                back_links[0].click()
                logger.info("Clicked back link to return to results")
            else:
                self.driver.back()
                logger.info("Used browser back to return to results")
            
            time.sleep(2)
            return True
        except Exception as e:
            logger.error(f"Error navigating back to results: {e}")
            return False
    
    def scrape_notices(self, keywords=['foreclosure', 'bankruptcy'], days_back=1):
        """Main scraping function"""
        logger.info(f"Starting scrape for keywords: {keywords}")
        
        combined_keywords = ' '.join(keywords)
        
        try:
            # Perform search
            if not self.search_notices(combined_keywords, days_back):
                logger.error(f"Search failed for keywords: {combined_keywords}")
                return
            
            # Set results per page to 50
            self.set_results_per_page(50)
            
            # Get initial view buttons count
            view_buttons = self.get_view_buttons()
            total_notices = len(view_buttons)
            logger.info(f"Found {total_notices} view buttons for '{combined_keywords}'")
            
            # Process each notice
            for i in range(total_notices):
                logger.info(f"Processing notice {i+1}/{total_notices}")
                
                # Re-find view buttons to get fresh elements
                current_view_buttons = self.get_view_buttons()
                if i >= len(current_view_buttons):
                    logger.warning(f"View button {i+1} no longer exists")
                    break
                
                button = current_view_buttons[i]
                
                # Click view button
                try:
                    button.click()
                    time.sleep(2)
                except Exception as e:
                    logger.warning(f"Failed to click view button {i+1}: {e}")
                    continue
                
                # Handle captcha if present
                if self.check_for_captcha():
                    logger.warning(f"Captcha detected on notice {i+1}")
                    if self.solve_captcha_simple():
                        logger.info(f"Captcha solved for notice {i+1}")
                    else:
                        logger.warning(f"Failed to solve captcha for notice {i+1} - skipping")
                        self.captcha_skipped += 1
                        self.navigate_back_to_results()
                        continue
                
                # Extract data
                current_url = self.driver.current_url
                data = self.extract_notice_data(current_url)
                self.results.append(data)
                
                if data['first_name'] and data['last_name']:
                    logger.info(f"Extracted: {data['first_name']} {data['last_name']}")
                else:
                    logger.info(f"Extracted notice with incomplete name data")
                
                # Navigate back to results for next iteration
                self.navigate_back_to_results()
            
        except Exception as e:
            logger.error(f"Error scraping keywords '{combined_keywords}': {e}")
    
    def save_to_csv(self, filename=None):
        """Save results to CSV file"""
        csvs_dir = "csvs"
        if not os.path.exists(csvs_dir):
            os.makedirs(csvs_dir)
        
        # Remove old CSV files
        existing_csvs = glob.glob(os.path.join(csvs_dir, "*.csv"))
        for csv_file in existing_csvs:
            try:
                os.remove(csv_file)
                logger.info(f"Removed old CSV file: {csv_file}")
            except Exception as e:
                logger.warning(f"Could not remove {csv_file}: {e}")
        
        if not filename:
            filename = f"mn_notices_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        
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
        scraper = MNNoticeScraperClean(headless=False)
        scraper.scrape_notices(['foreclosure', 'bankruptcy'], days_back=1)
        filename = scraper.save_to_csv()
        print(f"Scraping complete. Results saved to: {filename}")
        print(f"Total records extracted: {len(scraper.results)}")
        print(f"Captchas solved: {scraper.captcha_solved}")
        print(f"Notices skipped due to unsolved captcha: {scraper.captcha_skipped}")
    except Exception as e:
        logger.error(f"Scraper failed: {e}")
    finally:
        if scraper:
            scraper.close()

if __name__ == "__main__":
    main()