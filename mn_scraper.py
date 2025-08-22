#!/usr/bin/env python3
"""
MN Public Notice Scraper
Scrapes foreclosure and bankruptcy notices from mnpublicnotice.com
"""

from playwright.sync_api import sync_playwright, Page, Browser, BrowserContext
import csv
import re
from datetime import datetime, timedelta
import time
import logging
import os
import glob
import random

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class MNNoticeScraperClean:
    def __init__(self, headless=False, use_buster=True):
        self.base_url = "https://www.mnpublicnotice.com"
        self.search_url = f"{self.base_url}/Search.aspx"
        self.results = []
        self.captcha_solved = 0
        self.captcha_skipped = 0
        self.use_buster = use_buster
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None
        self.setup_browser(headless)
    
        
    def setup_browser(self, headless=False):
        """Setup Playwright browser with optional Buster extension"""
        try:
            self.playwright = sync_playwright().start()
            
            # Prepare browser launch arguments
            launch_args = [
                '--no-sandbox',
                '--disable-dev-shm-usage',
                '--disable-blink-features=AutomationControlled'
            ]
            
            # Add Buster extension if enabled and available
            if self.use_buster:
                buster_path = self.get_buster_extension_path()
                if buster_path:
                    launch_args.append(f'--load-extension={buster_path}')
                    launch_args.append('--disable-extensions-except={}'.format(buster_path))
                    logger.info(f"Loading Buster extension from: {buster_path}")
                else:
                    logger.warning("Buster extension not found, continuing without it")
                    self.use_buster = False
            
            # Use persistent context if using extensions (before launching browser)
            if self.use_buster:
                self.context = self.playwright.chromium.launch_persistent_context(
                    user_data_dir='./chrome_profile_buster',
                    headless=headless,
                    args=launch_args,
                    viewport={'width': 1920, 'height': 1080},
                    user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
                )
                self.browser = None  # No separate browser object with persistent context
            else:
                self.browser = self.playwright.chromium.launch(
                    headless=headless,
                    args=launch_args
                )
                self.context = self.browser.new_context(
                    viewport={'width': 1920, 'height': 1080},
                    user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
                )
            
            self.page = self.context.new_page()
            
            # Set default timeout
            self.page.set_default_timeout(10000)
            
            logger.info("Playwright browser setup successfully")
        except Exception as e:
            logger.error(f"Failed to setup Playwright browser: {e}")
            raise
    
    def get_buster_extension_path(self):
        """Get path to Buster extension directory"""
        possible_paths = [
            './buster_extension',
            './extensions/buster',
            os.path.expanduser('~/.config/google-chrome/Default/Extensions/mpbjkejclgfgadiemmefgebjfooflfhl'),  # Linux
            os.path.expanduser('~\\AppData\\Local\\Google\\Chrome\\User Data\\Default\\Extensions\\mpbjkejclgfgadiemmefgebjfooflfhl'),  # Windows
            os.path.expanduser('~/Library/Application Support/Google/Chrome/Default/Extensions/mpbjkejclgfgadiemmefgebjfooflfhl'),  # macOS
        ]
        
        for path in possible_paths:
            if os.path.exists(path):
                # For Chrome extension paths, we need to find the version subdirectory
                if 'Extensions' in path and 'mpbjkejclgfgadiemmefgebjfooflfhl' in path:
                    try:
                        # List version directories
                        version_dirs = [d for d in os.listdir(path) 
                                      if os.path.isdir(os.path.join(path, d))]
                        if version_dirs:
                            # Use the latest version
                            latest_version = sorted(version_dirs, reverse=True)[0]
                            full_path = os.path.join(path, latest_version)
                            logger.info(f"Found Buster extension at: {full_path} (version {latest_version})")
                            return full_path
                    except Exception as e:
                        logger.warning(f"Error accessing Buster extension directory: {e}")
                        continue
                else:
                    logger.info(f"Found Buster extension at: {path}")
                    return path
        
        # Try to create a simple extension directory with instructions
        self.create_buster_instructions()
        return None
    
    def create_buster_instructions(self):
        """Create instructions file for manual Buster extension setup"""
        instructions = """
# Buster Extension Setup Instructions

1. Download Buster extension from Chrome Web Store or GitHub:
   - Chrome Store: https://chrome.google.com/webstore/detail/buster-captcha-solver-for/mpbjkejclgfgadiemmefgebjfooflfhl
   - GitHub: https://github.com/dessant/buster

2. For manual setup, create a 'buster_extension' directory with unpacked extension files.

3. The scraper will automatically use the extension if found in any of these paths:
   - ./buster_extension
   - ./extensions/buster
   - Your Chrome profile extensions directory

The scraper will continue without Buster if not found.
"""
        try:
            with open('BUSTER_SETUP.md', 'w') as f:
                f.write(instructions)
            logger.info("Created BUSTER_SETUP.md with extension setup instructions")
        except Exception as e:
            logger.warning(f"Could not create setup instructions: {e}")
    
    def search_notices(self, keyword, days_back=1):
        """Navigate to search page and perform search"""
        logger.info(f"Searching for '{keyword}' in last {days_back} days")
        
        # Navigate to search page
        self.page.goto(self.search_url)
        
        # Wait for page to fully load
        self.page.wait_for_selector("form")
        time.sleep(3)
        
        # Set date range
        end_date = datetime.now()
        if days_back == 1:
            start_date = end_date  # Same day search
        else:
            start_date = end_date - timedelta(days=days_back)
        
        # Fill in keyword field
        try:
            keyword_field = self.page.wait_for_selector("input[type='text']")
            keyword_field.fill(keyword)  # fill() auto-clears in Playwright
            logger.info(f"Entered keyword(s): {keyword}")
        except Exception as e:
            logger.warning(f"Error with keyword field: {e}")
        
        # Set "Any Words" radio button
        try:
            any_words_radio = self.page.wait_for_selector("#ctl00_ContentPlaceHolder1_as1_rdoType_1")
            if not any_words_radio.is_checked():
                self.page.evaluate("(element) => element.click()", any_words_radio)
                logger.info("Selected 'Any Words' option")
                time.sleep(3)  # Wait for postback
        except Exception as e:
            logger.warning(f"Error with 'Any Words' radio button: {e}")
        
        # Fill date fields
        try:
            # Open date range selector
            date_range_div = self.page.wait_for_selector("#ctl00_ContentPlaceHolder1_as1_divDateRange")
            date_range_div.click()
            time.sleep(3)
            
            # Select range radio button
            range_radio = self.page.wait_for_selector("#ctl00_ContentPlaceHolder1_as1_rbRange")
            range_radio.click()
            time.sleep(1)
            
            # Fill date inputs
            date_inputs = self.page.query_selector_all("input[type='text']")
            for input_field in date_inputs:
                if not input_field.is_visible() or not input_field.is_enabled():
                    continue
                    
                field_name = input_field.get_attribute("name") or ""
                field_id = input_field.get_attribute("id") or ""
                
                if "from" in field_name.lower() or "from" in field_id.lower():
                    input_field.fill(start_date.strftime("%m/%d/%Y"))
                    logger.info(f"Set from date: {start_date.strftime('%m/%d/%Y')}")
                elif "to" in field_name.lower() or "to" in field_id.lower():
                    input_field.fill(end_date.strftime("%m/%d/%Y"))
                    logger.info(f"Set to date: {end_date.strftime('%m/%d/%Y')}")
                    
        except Exception as e:
            logger.warning(f"Error setting date fields: {e}")
        
        # Click search button
        try:
            search_button = self.page.wait_for_selector("#ctl00_ContentPlaceHolder1_as1_btnGo")
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
            results_dropdown = self.page.wait_for_selector(results_dropdown_selector)
            
            # Check current selection (for select elements, use get_attribute)
            current_selection = results_dropdown.get_attribute("value")
            if current_selection == str(per_page):
                logger.info(f"Results per page already set to {per_page}")
                return True
            
            results_dropdown.select_option(str(per_page))
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
            view_buttons = self.page.query_selector_all(
                "#ctl00_ContentPlaceHolder1_WSExtendedGridNP1_GridView1 .viewButton"
            )
            
            # Debug: also check total viewButton count
            all_view_buttons = self.page.query_selector_all(".viewButton")
            logger.info(f"Found {len(view_buttons)} view buttons in results table, {len(all_view_buttons)} total on page")
            
            # Only return the ones from the results table
            return view_buttons
        except Exception as e:
            logger.error(f"Error finding view buttons: {e}")
            return []
    
    def check_for_captcha(self):
        """Check if current page has a captcha"""
        page_source = self.page.content()
        return "You must complete the reCAPTCHA" in page_source
    
    def solve_captcha_simple(self):
        """Solve captcha by clicking checkbox, with Buster fallback for complex captchas"""
        try:
            logger.info("Attempting to solve reCAPTCHA...")
            
            # Find reCAPTCHA iframe
            iframe_selector = "#recaptcha iframe"
            self.page.wait_for_selector(iframe_selector)
            
            # Get all frames and find the reCAPTCHA frame
            frames = self.page.frames
            recaptcha_frame = None
            
            for frame in frames:
                if "recaptcha" in frame.url.lower():
                    recaptcha_frame = frame
                    break
            
            if recaptcha_frame:
                # Find and click checkbox
                checkbox_selectors = ["#recaptcha-anchor", ".rc-anchor-checkbox", "span[role='checkbox']"]
                
                for selector in checkbox_selectors:
                    try:
                        checkbox = recaptcha_frame.query_selector(selector)
                        if checkbox and checkbox.is_visible():
                            checkbox.click()
                            logger.info("Clicked reCAPTCHA checkbox")
                            break
                    except:
                        continue
                
                time.sleep(5)  # Wait longer for captcha processing
                
                # Check if image challenge appeared (complex captcha)
                if self.has_image_challenge():
                    logger.warning("Image challenge detected - trying Buster extension")
                    if self.use_buster and self.try_buster_solve():
                        logger.info("Buster solved the image challenge!")
                    else:
                        logger.warning("Could not solve image challenge")
                        return False
                
                # Click View Notice button
                view_notice_btn = self.page.wait_for_selector(
                    "#ctl00_ContentPlaceHolder1_PublicNoticeDetailsBody1_btnViewNotice"
                )
                view_notice_btn.click()
                logger.info("Clicked 'View Notice' button")
                time.sleep(3)
                
                # Check if captcha solved
                if "You must complete the reCAPTCHA" not in self.page.content():
                    logger.info("Successfully solved captcha!")
                    self.captcha_solved += 1
                    return True
            
            return False
            
        except Exception as e:
            logger.error(f"Error solving captcha: {e}")
            return False
    
    def has_image_challenge(self):
        """Check if reCAPTCHA has image challenge (complex captcha)"""
        try:
            # Look for common image challenge indicators
            image_challenge_selectors = [
                ".rc-imageselect",
                ".rc-imageselect-table", 
                ".rc-button-audio",
                "iframe[src*='bframe']"
            ]
            
            for selector in image_challenge_selectors:
                if self.page.query_selector(selector):
                    return True
            return False
        except:
            return False
    
    def try_buster_solve(self):
        """Try to solve captcha using Buster extension"""
        try:
            logger.info("Attempting to solve with Buster extension...")
            
            # Wait a bit for Buster to load and analyze the captcha
            time.sleep(3)
            
            # Debug: Log all elements that might be Buster-related
            self.debug_buster_elements()
            
            # Look for Buster solve button (common patterns)
            buster_selectors = [
                # Common Buster button patterns
                "button[title*='Buster']",
                "button[title*='buster']", 
                ".buster-button",
                "#buster-button",
                "button[aria-label*='solve']",
                "button[aria-label*='Solve']",
                "#buster-solve-button",
                
                # Generic patterns that might match
                "button[title*='Solve']",
                "button[title*='Audio']",
                ".rc-button-default",
                
                # Look for any buttons in the captcha area
                ".rc-footer button",
                ".rc-imageselect-payload button",
            ]
            
            logger.info(f"Trying {len(buster_selectors)} different selectors for Buster button...")
            
            for i, selector in enumerate(buster_selectors):
                try:
                    logger.debug(f"Trying selector {i+1}: {selector}")
                    buster_btn = self.page.query_selector(selector)
                    if buster_btn and buster_btn.is_visible():
                        title = buster_btn.get_attribute('title') or ''
                        aria_label = buster_btn.get_attribute('aria-label') or ''
                        class_name = buster_btn.get_attribute('class') or ''
                        logger.info(f"Found potential Buster button with selector '{selector}':")
                        logger.info(f"  Title: '{title}'")
                        logger.info(f"  Aria-label: '{aria_label}'")
                        logger.info(f"  Class: '{class_name}'")
                        
                        buster_btn.click()
                        logger.info("Clicked potential Buster button")
                        
                        # Wait for Buster to work (can take 10-30 seconds)
                        logger.info("Waiting for Buster to solve captcha (15 seconds)...")
                        time.sleep(15)
                        
                        # Check if solved
                        if not self.has_image_challenge():
                            logger.info("Captcha appears to be solved!")
                            return True
                        else:
                            logger.info("Captcha still present, trying next selector...")
                except Exception as e:
                    logger.debug(f"Selector '{selector}' failed: {e}")
                    continue
            
            # If no button found, Buster might work automatically
            logger.info("No Buster button found, waiting to see if it works automatically...")
            time.sleep(10)
            return not self.has_image_challenge()
            
        except Exception as e:
            logger.error(f"Error using Buster: {e}")
            return False
    
    def debug_buster_elements(self):
        """Debug function to log all potential Buster-related elements"""
        try:
            logger.info("=== DEBUG: Looking for Buster elements ===")
            
            # Look for any elements with 'buster' in various attributes
            debug_selectors = [
                "*[title*='buster' i]",
                "*[title*='Buster' i]", 
                "*[aria-label*='buster' i]",
                "*[class*='buster' i]",
                "*[id*='buster' i]",
                "button[title]",  # All buttons with titles
                ".rc-footer *",   # Everything in reCAPTCHA footer
            ]
            
            for selector in debug_selectors:
                elements = self.page.query_selector_all(selector)
                if elements:
                    logger.info(f"Found {len(elements)} elements matching '{selector}':")
                    for i, elem in enumerate(elements[:3]):  # Only log first 3
                        try:
                            tag = elem.evaluate('el => el.tagName')
                            title = elem.get_attribute('title') or ''
                            aria = elem.get_attribute('aria-label') or ''
                            class_name = elem.get_attribute('class') or ''
                            text = elem.text_content()[:50] or ''
                            logger.info(f"  [{i+1}] {tag}: title='{title}' aria='{aria}' class='{class_name}' text='{text}'")
                        except:
                            continue
            
            logger.info("=== END DEBUG ===")
                            
        except Exception as e:
            logger.warning(f"Debug logging failed: {e}")
    
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
            page_text = self.page.content()
            
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
            back_links = self.page.query_selector_all('a:has-text("Back")')
            if back_links:
                back_links[0].click()
                logger.info("Clicked back link to return to results")
            else:
                self.page.go_back()
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
        try:
            if self.page:
                self.page.close()
            if self.context:
                self.context.close()
            if self.browser:  # Only exists when not using persistent context
                self.browser.close()
            if self.playwright:
                self.playwright.stop()
        except Exception as e:
            logger.warning(f"Error during cleanup: {e}")

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