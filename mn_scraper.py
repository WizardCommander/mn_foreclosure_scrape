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

logging.basicConfig(
    level=logging.INFO,
    format='%(message)s'  # Simplified format, no timestamps or module names
)
logger = logging.getLogger(__name__)

# Load environment variables from .env file
try:
    from dotenv import load_dotenv
    load_dotenv()
    logger.info("🔧 .env file loaded")
except ImportError:
    logger.warning("⚠️  python-dotenv not installed - install with: py -m pip install python-dotenv")

# 2captcha integration
try:
    from twocaptcha import TwoCaptcha
    HAS_2CAPTCHA = True
    logger.info("2captcha-python library loaded successfully")
except ImportError:
    HAS_2CAPTCHA = False
    logger.warning("2captcha-python not installed - image captcha solving will be skipped")

class MNNoticeScraperClean:
    def __init__(self, headless=False):
        self.base_url = "https://www.mnpublicnotice.com"
        self.search_url = f"{self.base_url}/Search.aspx"
        self.results = []
        self.captcha_solved = 0
        self.captcha_skipped = 0
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None
        self.automation_detected = False
        
        # 2captcha configuration
        self.twocaptcha_api_key = os.getenv('TWO_CAPTCHA_API_KEY')
        self.solver = None
        
        # Debug API key loading
        if self.twocaptcha_api_key:
            logger.info(f"🔑 2captcha API key loaded (ends with: ...{self.twocaptcha_api_key[-6:]})")
        else:
            logger.error("❌ TWO_CAPTCHA_API_KEY not found in environment variables")
            logger.info("💡 Make sure your .env file contains: TWO_CAPTCHA_API_KEY=your_key_here")
        
        if self.twocaptcha_api_key and HAS_2CAPTCHA:
            try:
                self.solver = TwoCaptcha(
                    apiKey=self.twocaptcha_api_key,
                    defaultTimeout=120,  # 2 minutes timeout
                    recaptchaTimeout=600,  # 10 minutes for reCAPTCHA
                    pollingInterval=10  # Check every 10 seconds
                )
                logger.info("✅ 2captcha solver initialized successfully")
            except Exception as e:
                logger.error(f"❌ Failed to initialize 2captcha solver: {e}")
                self.solver = None
        elif not HAS_2CAPTCHA:
            logger.warning("⚠️  2captcha-python library not available")
        elif not self.twocaptcha_api_key:
            logger.warning("⚠️  No 2captcha API key - image captchas will be skipped")
            
        self.setup_browser(headless)
    
        
    def setup_browser(self, headless=False):
        """Setup Playwright browser with stealth mode"""
        try:
            self.playwright = sync_playwright().start()
            
            # Stealth browser launch arguments to avoid detection
            launch_args = [
                '--no-sandbox',
                '--disable-dev-shm-usage',
                '--disable-blink-features=AutomationControlled',
                '--disable-web-security',
                '--disable-features=VizDisplayCompositor',
                '--disable-plugins-discovery',
                '--no-first-run',
                '--no-default-browser-check',
                '--disable-default-apps',
                '--disable-popup-blocking',
                '--disable-translate',
                '--disable-background-timer-throttling',
                '--disable-backgrounding-occluded-windows',
                '--disable-renderer-backgrounding',
                '--disable-field-trial-config',
                '--disable-back-forward-cache',
                '--disable-ipc-flooding-protection',
                '--enable-features=NetworkService,NetworkServiceLogging',
                '--disable-hang-monitor',
                '--disable-prompt-on-repost',
                '--disable-component-update',
                '--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            ]
            
            # Launch browser with standard configuration
            self.browser = self.playwright.chromium.launch(
                headless=headless,
                args=launch_args
            )
            self.context = self.browser.new_context(
                viewport={'width': 1920, 'height': 1080},
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            )
            
            self.page = self.context.new_page()
            
            # Stealth JavaScript to hide automation markers
            stealth_js = """
            // Override webdriver detection
            Object.defineProperty(navigator, 'webdriver', {
                get: () => false,
            });
            
            // Override chrome detection
            window.chrome = {
                runtime: {},
            };
            
            // Override permissions
            const originalQuery = window.navigator.permissions.query;
            window.navigator.permissions.query = (parameters) => (
                parameters.name === 'notifications' ?
                    Promise.resolve({ state: Notification.permission }) :
                    originalQuery(parameters)
            );
            
            // Override plugins
            Object.defineProperty(navigator, 'plugins', {
                get: () => [1, 2, 3, 4, 5],
            });
            
            // Override languages
            Object.defineProperty(navigator, 'languages', {
                get: () => ['en-US', 'en'],
            });
            
            // Add realistic screen properties
            Object.defineProperty(screen, 'availTop', {
                get: () => 0,
            });
            """
            
            # Add stealth script to every page
            self.page.add_init_script(stealth_js)
            
            # Set default timeout
            self.page.set_default_timeout(10000)
            
            logger.info("🌐 Browser setup complete")
        except Exception as e:
            logger.error(f"Failed to setup Playwright browser: {e}")
            raise
    
    
    
    def search_notices(self, keyword, days_back=1):
        """Navigate to search page and perform search"""
        logger.info(f"🔍 Searching for '{keyword}' (last {days_back} day{'s' if days_back > 1 else ''})")
        
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
        # Reduced logging for form filling
        except Exception as e:
            logger.warning(f"Error with keyword field: {e}")
        
        # Set "Any Words" radio button
        try:
            any_words_radio = self.page.wait_for_selector("#ctl00_ContentPlaceHolder1_as1_rdoType_1")
            if not any_words_radio.is_checked():
                self.page.evaluate("(element) => element.click()", any_words_radio)
        # Selected Any Words option
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
                    pass  # Set from date
                elif "to" in field_name.lower() or "to" in field_id.lower():
                    input_field.fill(end_date.strftime("%m/%d/%Y"))
                    pass  # Set to date
                    
        except Exception as e:
            logger.warning(f"Error setting date fields: {e}")
        
        # Click search button
        try:
            search_button = self.page.wait_for_selector("#ctl00_ContentPlaceHolder1_as1_btnGo")
            search_button.click()
        # Search submitted
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
        # Set results per page
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
            
        # Found view buttons in results
            
            # Only return the ones from the results table
            return view_buttons
        except Exception as e:
            logger.error(f"Error finding view buttons: {e}")
            return []
    
    def check_for_captcha(self):
        """Check if current page has a captcha"""
        page_source = self.page.content()
        return "You must complete the reCAPTCHA" in page_source
    
    def check_automation_detection(self):
        """Check if reCAPTCHA has detected automation - looks in frames"""
        try:
            automation_messages = [
                "automated processes",
                "looks like your browser is using automated processes", 
                "automated traffic",
                "unusual traffic",
                "automated queries"
            ]
            
            # Check main page content first
            page_source = self.page.content().lower()
            for message in automation_messages:
                if message.lower() in page_source:
                    logger.warning(f"Automation detected on main page: {message}")
                    self.automation_detected = True
                    return True
            
            # Check all frames (especially reCAPTCHA frames)
            frames = self.page.frames
            for frame in frames:
                frame_url = frame.url.lower()
                if "recaptcha" in frame_url or "google" in frame_url:
                    try:
                        frame_content = frame.content().lower()
                        for message in automation_messages:
                            if message.lower() in frame_content:
                                logger.warning(f"Automation detected in frame {frame_url}: {message}")
                                self.automation_detected = True
                                return True
                    except Exception as e:
                        logger.debug(f"Could not check frame content: {e}")
                        continue
                        
            return False
        except Exception as e:
            logger.error(f"Error checking automation detection: {e}")
            return False
    
    def find_recaptcha_frame(self):
        """Find reCAPTCHA frame once and reuse to avoid duplication"""
        frames = self.page.frames
        for frame in frames:
            if "recaptcha" in frame.url.lower():
                return frame
        return None
    
    def solve_captcha_simple(self):
        """Solve captcha by clicking checkbox, prepare for 2captcha integration for image challenges"""
        try:
            logger.info("🤖 Attempting to solve reCAPTCHA...")
            
            # Find reCAPTCHA iframe
            iframe_selector = "#recaptcha iframe"
            self.page.wait_for_selector(iframe_selector)
            
            # Find the reCAPTCHA frame using consolidated method
            recaptcha_frame = self.find_recaptcha_frame()
            
            if recaptcha_frame:
                # Find and click checkbox
                checkbox_selectors = ["#recaptcha-anchor", ".rc-anchor-checkbox", "span[role='checkbox']"]
                
                for selector in checkbox_selectors:
                    try:
                        checkbox = recaptcha_frame.query_selector(selector)
                        if checkbox and checkbox.is_visible():
                            checkbox.click()
                            logger.info("✅ Clicked reCAPTCHA checkbox")
                            break
                    except:
                        continue
                
                # Wait for captcha processing
                LONG_WAIT = random.uniform(4.78, 11.1)
                time.sleep(LONG_WAIT)
                
                # Wait a bit more and check for challenges
                MID_WAIT = random.uniform(2.0, 4.0)
                time.sleep(MID_WAIT)
                
                # Check for automation detection first
                if self.check_automation_detection():
                    logger.error("reCAPTCHA has detected automation - this session is compromised")
                    return False
                
                if self.has_image_challenge():
                    logger.warning("Image challenge detected - attempting 2captcha solving")
                    
                    if self.solver:
                        # Use 2captcha to solve the image challenge
                        captcha_response = self.solve_recaptcha_with_2captcha()
                        if captcha_response:
                            # Submit the solved captcha response
                            if self.submit_captcha_response(captcha_response):
                                logger.info("Image challenge solved with 2captcha!")
                                self.captcha_solved += 1
                                return True
                            else:
                                logger.error("Failed to submit 2captcha response")
                                return False
                        else:
                            logger.error("2captcha failed to solve image challenge")
                            return False
                    else:
                        logger.error("2captcha solver not available - skipping image challenge")
                        return False
                else:
                    logger.info("✅ Simple checkbox captcha solved")
                
                # Check if captcha was solved
                if "You must complete the reCAPTCHA" not in self.page.content():
                    logger.info("Captcha appears solved")
                    self.captcha_solved += 1
                    return True
                
                # Click View Notice button if still needed
                try:
                    view_notice_btn = self.page.wait_for_selector(
                        "#ctl00_ContentPlaceHolder1_PublicNoticeDetailsBody1_btnViewNotice", 
                        timeout=5000
                    )
                    view_notice_btn.click()
                    logger.info("Clicked 'View Notice' button")
                    time.sleep(3)
                    
                    # Check if captcha solved
                    if "You must complete the reCAPTCHA" not in self.page.content():
                        logger.info("Successfully solved captcha!")
                        self.captcha_solved += 1
                        return True
                except Exception as e:
                    logger.error(f"Could not click View Notice button: {e}")
                    return False
            
            return False
            
        except Exception as e:
            logger.error(f"Error solving captcha: {e}")
            return False
    
    def has_image_challenge(self):
        """Check if reCAPTCHA has image challenge (complex captcha) - looks inside iframe"""
        try:
            # First find all frames on the page
            frames = self.page.frames
        # Checking frames for image challenge
            
            # Look for image challenge indicators inside reCAPTCHA frames
            image_challenge_selectors = [
                "#rc-imageselect",  # Main image challenge container
                ".rc-imageselect",
                ".rc-imageselect-payload", # The payload area
                ".rc-imageselect-table"
            ]
            
            for frame in frames:
                frame_url = frame.url.lower()
        # Checking reCAPTCHA frames
                
                # Only check reCAPTCHA-related frames
                if "recaptcha" in frame_url or "google" in frame_url:
        # Found reCAPTCHA frame
                    
                    for selector in image_challenge_selectors:
                        try:
                            element = frame.query_selector(selector)
                            if element and element.is_visible():
                                logger.info("🖼️  Image challenge detected")
                                return True
                        except Exception as e:
                            logger.debug(f"Error checking selector {selector} in frame {frame_url}: {e}")
                            continue
            
            # Also check main page as fallback
            for selector in image_challenge_selectors:
                try:
                    element = self.page.query_selector(selector)
                    if element and element.is_visible():
                        logger.info("🖼️  Image challenge detected")
                        return True
                except:
                    continue
                    
            return False
        except Exception as e:
            logger.error(f"Error in has_image_challenge: {e}")
            return False
    
    def extract_recaptcha_details(self):
        """Extract reCAPTCHA site key needed for 2captcha API"""
        try:
            # Get current page URL
            page_url = self.page.url
            
            # Extract site key from reCAPTCHA div or script
            site_key = None
            
            # Method 1: Check for data-sitekey attribute in divs
            recaptcha_divs = self.page.query_selector_all('[data-sitekey]')
            if recaptcha_divs:
                site_key = recaptcha_divs[0].get_attribute('data-sitekey')
                logger.info(f"Found site key from div: {site_key}")
            
            # Method 2: Check frame sources for site key parameter
            if not site_key:
                frames = self.page.frames
                for frame in frames:
                    frame_url = frame.url
                    if "recaptcha" in frame_url.lower():
                        # Extract from URL parameters (k= parameter)
                        site_key_match = re.search(r'[?&]k=([^&]+)', frame_url)
                        if site_key_match:
                            site_key = site_key_match.group(1)
                            logger.info(f"Found site key from frame URL: {site_key}")
                            break
            
            # Method 3: Check script tags for grecaptcha calls
            if not site_key:
                scripts = self.page.query_selector_all('script')
                for script in scripts:
                    script_content = script.text_content() or ""
                    # Look for sitekey in various formats
                    patterns = [
                        r'[\'"]sitekey[\'"]:\s*[\'"]([^\'\"]+)[\'"]',
                        r'grecaptcha\.render\([^}]*[\'"]sitekey[\'"]:\s*[\'"]([^\'\"]+)[\'"]',
                        r'data-sitekey=[\'"]([^\'\"]+)[\'"]'
                    ]
                    
                    for pattern in patterns:
                        site_key_match = re.search(pattern, script_content)
                        if site_key_match:
                            site_key = site_key_match.group(1)
                            logger.info(f"Found site key from script: {site_key}")
                            break
                    if site_key:
                        break
            
            if not site_key:
                logger.error("Could not extract reCAPTCHA site key")
                return None
                
            return {
                'websiteURL': page_url,
                'websiteKey': site_key
            }
            
        except Exception as e:
            logger.error(f"Error extracting reCAPTCHA details: {e}")
            return None
    
    def solve_recaptcha_with_2captcha(self):
        """Solve reCAPTCHA using 2captcha service with enhanced error handling"""
        if not self.solver:
            logger.error("2captcha solver not initialized")
            return None
            
        try:
            # Extract reCAPTCHA details
            captcha_details = self.extract_recaptcha_details()
            if not captcha_details:
                logger.error("Could not extract reCAPTCHA details")
                return None
            
            logger.info(f"Submitting reCAPTCHA to 2captcha service...")
            logger.info(f"Site URL: {captcha_details['websiteURL']}")
            logger.info(f"Site key: {captcha_details['websiteKey'][:20]}...")  # Hide full key for security
            
            # Submit captcha to 2captcha service with timeout handling
            start_time = time.time()
            
            try:
                result = self.solver.recaptcha(
                    sitekey=captcha_details['websiteKey'],
                    url=captcha_details['websiteURL']
                )
                
                solve_time = time.time() - start_time
                logger.info(f"2captcha solve completed in {solve_time:.1f} seconds")
                
                if result and result.get('code'):
                    logger.info("✅ 2captcha successfully solved reCAPTCHA")
                    logger.info(f"Response token length: {len(result['code'])} characters")
                    return result['code']  # This is the g-recaptcha-response token
                else:
                    logger.error("❌ 2captcha returned empty result")
                    return None
                    
            except Exception as solve_error:
                solve_time = time.time() - start_time
                logger.error(f"❌ 2captcha API error after {solve_time:.1f}s: {solve_error}")
                
                # Check for specific error types
                error_str = str(solve_error).lower()
                if 'insufficient funds' in error_str or 'zero balance' in error_str:
                    logger.error("💰 2captcha account has insufficient funds")
                elif 'invalid api key' in error_str:
                    logger.error("🔑 2captcha API key is invalid")
                elif 'timeout' in error_str:
                    logger.error("⏱️ 2captcha solving timed out (captcha too complex)")
                elif 'no slot available' in error_str:
                    logger.error("🚫 2captcha service overloaded, no workers available")
                
                return None
                
        except Exception as e:
            logger.error(f"❌ Critical error solving reCAPTCHA with 2captcha: {e}")
            return None
    
    def submit_captcha_response(self, captcha_response):
        """Submit the solved captcha response using 2captcha's recommended method"""
        try:
            logger.info("📝 Submitting 2captcha response to page...")
            
            # Sanitize the captcha response to prevent JavaScript injection
            safe_response = captcha_response.replace('\\', '\\\\').replace("'", "\\'").replace('"', '\\"')
            
            # Method from 2captcha docs: Find g-recaptcha-response element
            submission_script = f"""
            (function() {{
                // Step 1: Find the g-recaptcha-response element (by ID or name)
                var responseElement = document.getElementById('g-recaptcha-response') || 
                                    document.querySelector('textarea[name="g-recaptcha-response"]');
                
                if (responseElement) {{
                    // Step 2: Make it visible (remove display:none)
                    responseElement.style.display = 'block';
                    responseElement.style.visibility = 'visible';
                    
                    // Step 3: Set the token using innerHTML (as per 2captcha docs)
                    responseElement.innerHTML = '{safe_response}';
                    responseElement.value = '{safe_response}';
                    
                    console.log('✅ Set reCAPTCHA response token');
                    
                    // Step 4: Try to find and execute callback function
                    try {{
                        // Look for callback in reCAPTCHA configuration
                        if (window.___grecaptcha_cfg && window.___grecaptcha_cfg.clients) {{
                            var client = window.___grecaptcha_cfg.clients[0];
                            if (client && client.callback && typeof client.callback === 'function') {{
                                console.log('🔄 Executing reCAPTCHA callback');
                                client.callback('{safe_response}');
                            }}
                        }}
                        
                        // Alternative: Try global callback functions
                        if (typeof grecaptchaCallback === 'function') {{
                            grecaptchaCallback('{safe_response}');
                        }}
                        if (typeof onRecaptchaSuccess === 'function') {{
                            onRecaptchaSuccess('{safe_response}');
                        }}
                        
                    }} catch(callbackError) {{
                        console.log('⚠️ Callback execution failed:', callbackError);
                    }}
                    
                    // Step 5: Trigger events
                    var changeEvent = new Event('change', {{ bubbles: true }});
                    responseElement.dispatchEvent(changeEvent);
                    
                    var inputEvent = new Event('input', {{ bubbles: true }});
                    responseElement.dispatchEvent(inputEvent);
                    
                    return 'success';
                }} else {{
                    return 'element_not_found';
                }}
            }})();
            """
            
            result = self.page.evaluate(submission_script)
            
            if result == 'success':
                logger.info("✅ Token submitted successfully")
            elif result == 'element_not_found':
                logger.error("❌ Could not find g-recaptcha-response element")
                return False
            
            # Wait for reCAPTCHA to process the token
            logger.info("⏳ Waiting for reCAPTCHA to process token...")
            
            # Wait up to 10 seconds for captcha to clear
            for wait_time in range(10):
                time.sleep(1)
                page_content = self.page.content()
                
                # Check if captcha error message is gone
                if "You must complete the reCAPTCHA" not in page_content:
                    logger.info(f"🎉 reCAPTCHA cleared after {wait_time + 1} seconds!")
                    break
                    
                # Also check if we can see success indicators
                success_indicators = self.page.query_selector_all('.rc-anchor-checkbox-checked, [aria-checked="true"]')
                if success_indicators:
                    logger.info("✅ Found reCAPTCHA success indicator")
                    break
            else:
                logger.warning("⚠️ reCAPTCHA did not clear within 10 seconds")
            
            time.sleep(1)  # Brief pause before trying to click button
            
            # Try clicking the View Notice button with multiple methods to bypass overlay
            logger.info("🔘 Attempting to click View Notice button...")
            
            try:
                view_notice_btn = self.page.wait_for_selector(
                    "#ctl00_ContentPlaceHolder1_PublicNoticeDetailsBody1_btnViewNotice", 
                    timeout=5000
                )
                
                # Method 1: Try regular click first
                try:
                    view_notice_btn.click(timeout=3000)
                    logger.info("✅ Clicked View Notice button (method 1 - regular click)")
                except:
                    # Method 2: Force click using JavaScript
                    try:
                        self.page.evaluate("(element) => element.click()", view_notice_btn)
                        logger.info("✅ Clicked View Notice button (method 2 - JavaScript click)")
                    except:
                        # Method 3: Click at coordinates to bypass overlay
                        try:
                            bbox = view_notice_btn.bounding_box()
                            if bbox:
                                # Click at button center coordinates
                                self.page.mouse.click(bbox['x'] + bbox['width']/2, bbox['y'] + bbox['height']/2)
                                logger.info("✅ Clicked View Notice button (method 3 - coordinate click)")
                            else:
                                # Method 4: Try clicking by selector with force
                                self.page.evaluate("""
                                    document.querySelector('#ctl00_ContentPlaceHolder1_PublicNoticeDetailsBody1_btnViewNotice').click();
                                """)
                                logger.info("✅ Clicked View Notice button (method 4 - direct selector)")
                        except Exception as final_error:
                            logger.error(f"❌ All click methods failed: {final_error}")
                            return False
                
                time.sleep(3)
                
                # Check if we successfully accessed the notice
                page_content = self.page.content()
                if "You must complete the reCAPTCHA" not in page_content:
                    logger.info("🎉 2captcha response accepted! Notice accessed successfully.")
                    return True
                else:
                    logger.error("❌ Still seeing captcha message after clicking")
                    return False
                    
            except Exception as e:
                logger.error(f"❌ Could not find View Notice button: {e}")
                return False
                
        except Exception as e:
            logger.error(f"Error submitting captcha response: {e}")
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
            # Use the specific back link ID from the page source
            back_link_selector = "#ctl00_ContentPlaceHolder1_PublicNoticeDetailsBody1_hlBackFromBodyTop"
            
            logger.info("Attempting to navigate back to search results...")
            
            try:
                back_link = self.page.wait_for_selector(back_link_selector, timeout=5000)
                if back_link and back_link.is_visible():
                    back_link.click()
                    logger.info("Clicked specific back link to return to results")
                    time.sleep(3)  # Wait for navigation
                    return True
                else:
                    logger.warning("Back link found but not visible")
            except Exception as e:
                logger.warning(f"Specific back link failed: {e}")
            
            # Fallback: try browser back
            logger.info("Back link failed, trying browser back...")
            self.page.go_back()
            logger.info("Used browser back to return to results")
            time.sleep(3)
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
            logger.info(f"🌯 Found {total_notices} notices to process")
            
            # Process each notice
            for i in range(total_notices):
                if i == 0 or (i+1) % 10 == 0:  # Log every 10th notice
                    logger.info(f"📄 Processing notice {i+1}/{total_notices}")
                
                
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
                    logger.info(f"🤖 Captcha on notice #{i+1}")
                    if self.solve_captcha_simple():
                        logger.info(f"✅ Captcha solved for notice #{i+1}")
                    else:
                        logger.warning(f"❌ Failed to solve captcha for notice #{i+1} - skipping")
                        self.captcha_skipped += 1
                        self.navigate_back_to_results()
                        continue
                
                # Extract data
                current_url = self.page.url
                data = self.extract_notice_data(current_url)
                self.results.append(data)
                
                if data['first_name'] and data['last_name']:
                    if (i+1) % 5 == 0:  # Log every 5th extraction
                        logger.info(f"✅ Extracted: {data['first_name']} {data['last_name']}")
                else:
                    logger.debug(f"Incomplete data for notice #{i+1}")
                
                # Navigate back to results for next iteration
                if not self.navigate_back_to_results():
                    logger.error(f"Failed to navigate back to results after notice {i+1}")
                    break
                
                # Wait for results page to load properly
                try:
                    self.page.wait_for_selector("#ctl00_ContentPlaceHolder1_WSExtendedGridNP1_GridView1 .viewButton", timeout=10000)
                    time.sleep(2)  # Additional wait for stability
                except Exception as e:
                    logger.error(f"Results page did not load properly after notice {i+1}: {e}")
                    break
            
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
        
        logger.info(f"📁 Saved {len(self.results)} records to {filename}")
        return full_path
    
    def close(self):
        """Close the browser"""
        try:
            if self.page:
                self.page.close()
            if self.context:
                self.context.close()
            if self.browser:
                self.browser.close()
            if self.playwright:
                self.playwright.stop()
        except Exception as e:
            logger.warning(f"Error during cleanup: {e}")

def main():
    """
    Main function to run the scraper
    Set TWOCAPTCHA_API_KEY environment variable or pass it directly to the scraper
    """
    scraper = None
    try:
        scraper = MNNoticeScraperClean(headless=False)
        
        scraper.scrape_notices(['foreclosure', 'bankruptcy'], days_back=1)
        filename = scraper.save_to_csv()
        
        print(f"\n🎉 Scraping complete! Results saved to: {filename}")
        print(f"📊 Total records extracted: {len(scraper.results)}")
        print(f"✅ Captchas solved: {scraper.captcha_solved}")
        print(f"⏭️  Notices skipped due to unsolved captcha: {scraper.captcha_skipped}")
        
        if scraper.solver:
            print(f"💰 Estimated 2captcha cost: ~${(scraper.captcha_solved * 0.003):.3f}")
        
    except Exception as e:
        logger.error(f"Scraper failed: {e}")
    finally:
        if scraper:
            scraper.close()

if __name__ == "__main__":
    main()