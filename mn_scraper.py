#!/usr/bin/env python3
"""
MN Public Notice Scraper
Scrapes foreclosure and bankruptcy notices from mnpublicnotice.com
"""

import argparse
import csv
import gc
import glob
import logging
import os
import random
import re
import sys
import time
from datetime import datetime, timedelta
from typing import Optional

from playwright.sync_api import sync_playwright
from mullvad_manager import MullvadManager

logging.basicConfig(
    level=logging.INFO, format="%(message)s"
)  # Simplified format, no timestamps or module names
logger = logging.getLogger(__name__)

# Load environment variables from .env file BEFORE importing gpt_parser
try:
    from dotenv import load_dotenv

    load_dotenv()
    logger.info("🔧 .env file loaded")
except ImportError:
    logger.warning(
        "⚠️  python-dotenv not installed - install with: py -m pip install python-dotenv"
    )

# Import GPT parser after .env is loaded
from gpt_parser import extract_notice_data_gpt, get_parsing_stats
from star_tribune_scraper import StarTribuneScraper

# 2captcha integration
try:
    from twocaptcha import TwoCaptcha

    HAS_2CAPTCHA = True
    logger.info("2captcha-python library loaded successfully")
except ImportError:
    HAS_2CAPTCHA = False
    logger.warning(
        "2captcha-python not installed - image captcha solving will be skipped"
    )


class MNNoticeScraperClean:
    def __init__(self, headless=False):
        self.base_url = "https://www.mnpublicnotice.com"
        self.search_url = f"{self.base_url}/Search.aspx"
        self.results = []
        self.captcha_solved = 0
        self.captcha_skipped = 0
        self.csv_writer = None
        self.csv_file = None
        self.records_written = 0
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None
        self.automation_detected = False

        # Rate limiting configuration
        self.min_delay = 3.0  # Minimum delay between requests (seconds)
        self.max_delay = 8.0  # Maximum delay between requests (seconds)
        self.long_pause_every = 10  # Take a longer pause every N notices
        self.long_pause_duration = (
            5,
            10,
        )  # Long pause range (seconds) - reduced to prevent session issues

        # User agent rotation
        self.user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/121.0",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/120.0",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15",
        ]

        # 2captcha configuration
        self.twocaptcha_api_key = os.getenv("TWO_CAPTCHA_API_KEY")
        self.solver = None

        # Debug API key loading
        if self.twocaptcha_api_key:
            logger.info(
                f"🔑 2captcha API key loaded (ends with: ...{self.twocaptcha_api_key[-6:]})"
            )
        else:
            logger.error("❌ TWO_CAPTCHA_API_KEY not found in environment variables")
            logger.info(
                "💡 Make sure your .env file contains: TWO_CAPTCHA_API_KEY=your_key_here"
            )

        if self.twocaptcha_api_key and HAS_2CAPTCHA:
            try:
                self.solver = TwoCaptcha(
                    apiKey=self.twocaptcha_api_key,
                    defaultTimeout=120,  # 2 minutes timeout
                    recaptchaTimeout=600,  # 10 minutes for reCAPTCHA
                    pollingInterval=10,  # Check every 10 seconds
                )
                logger.info("✅ 2captcha solver initialized successfully")
            except Exception as e:
                logger.error(f"❌ Failed to initialize 2captcha solver: {e}")
                self.solver = None
        elif not HAS_2CAPTCHA:
            logger.warning("⚠️  2captcha-python library not available")
        elif not self.twocaptcha_api_key:
            logger.warning("⚠️  No 2captcha API key - image captchas will be skipped")

        # VPN Management - Disable auto_connect to prevent early connection issues
        self.vpn_manager = MullvadManager(
            enabled=True, auto_connect=False
        )  # Set enabled=False to disable VPN

        self.setup_browser(headless)

    def setup_browser(self, headless=False):
        """Setup Playwright browser with stealth mode"""
        try:
            self.playwright = sync_playwright().start()

            # Stealth browser launch arguments to avoid detection
            launch_args = [
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled",
                "--disable-web-security",
                "--disable-features=VizDisplayCompositor",
                "--disable-plugins-discovery",
                "--no-first-run",
                "--no-default-browser-check",
                "--disable-default-apps",
                "--disable-popup-blocking",
                "--disable-translate",
                "--disable-background-timer-throttling",
                "--disable-backgrounding-occluded-windows",
                "--disable-renderer-backgrounding",
                "--disable-field-trial-config",
                "--disable-back-forward-cache",
                "--disable-ipc-flooding-protection",
                "--enable-features=NetworkService,NetworkServiceLogging",
                "--disable-hang-monitor",
                "--disable-prompt-on-repost",
                "--disable-component-update",
                "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            ]

            # Launch browser with standard configuration
            self.browser = self.playwright.chromium.launch(
                headless=headless, args=launch_args
            )

            # Select random user agent for this session
            selected_user_agent = random.choice(self.user_agents)
            logger.debug(f"🎭 Using user agent: {selected_user_agent[:50]}...")

            self.context = self.browser.new_context(
                viewport={"width": 1920, "height": 1080}, user_agent=selected_user_agent
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

    def _calculate_search_dates(self):
        """Calculate search dates - pure function for easy testing"""
        end_date = datetime.now() - timedelta(days=1)  # Yesterday
        start_date = end_date  # Search for yesterday's notices only
        return start_date, end_date

    def _fill_keyword_field(self, keyword):
        """Fill in keyword field"""
        try:
            keyword_field = self.page.wait_for_selector("input[type='text']")
            keyword_field.fill(keyword)  # fill() auto-clears in Playwright
            return True
        except Exception as e:
            logger.warning(f"Error with keyword field: {e}")
            return False

    def _set_any_words_radio(self):
        """Set 'Any Words' radio button"""
        try:
            any_words_radio = self.page.wait_for_selector(
                "#ctl00_ContentPlaceHolder1_as1_rdoType_1"
            )
            if not any_words_radio.is_checked():
                self.page.evaluate("(element) => element.click()", any_words_radio)
                time.sleep(3)  # Wait for postback
            return True
        except Exception as e:
            logger.warning(f"Error with 'Any Words' radio button: {e}")
            return False

    def _fill_date_fields(self, start_date, end_date):
        """Fill date fields"""
        try:
            # Open date range selector
            date_range_div = self.page.wait_for_selector(
                "#ctl00_ContentPlaceHolder1_as1_divDateRange"
            )
            date_range_div.click()
            time.sleep(3)

            # Select range radio button
            range_radio = self.page.wait_for_selector(
                "#ctl00_ContentPlaceHolder1_as1_rbRange"
            )
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
                    input_field.fill(start_date.strftime("%m/%d/%Y"))
                elif "to" in field_name.lower() or "to" in field_id.lower():
                    input_field.fill(end_date.strftime("%m/%d/%Y"))
                    input_field.fill(end_date.strftime("%m/%d/%Y"))

            return True
        except Exception as e:
            logger.warning(f"Error setting date fields: {e}")
            return False

    def _click_search_button(self):
        """Click search button and wait for results"""
        try:
            search_button = self.page.wait_for_selector(
                "#ctl00_ContentPlaceHolder1_as1_btnGo"
            )
            search_button.click()
            time.sleep(5)  # Wait for results
            return True
        except Exception as e:
            logger.error(f"Error clicking search button: {e}")
            return False

    def search_notices(self, keyword, days_back=1):
        """Navigate to search page and perform search - orchestrates extracted functions"""
        logger.info(
            f"🔍 Searching for '{keyword}' (last {days_back} day{'s' if days_back > 1 else ''})"
        )

        # Navigate to search page
        self.page.goto(self.search_url)

        # Wait for page to fully load
        self.page.wait_for_selector("form")
        time.sleep(3)

        # Calculate search dates
        start_date, end_date = self._calculate_search_dates()
        self._search_date = start_date  # Store search date for CSV filename
        logger.info(f"🗓️ Searching for notices on {start_date.strftime('%m/%d/%Y')}")

        # Execute search steps using extracted functions
        success = True
        success &= self._fill_keyword_field(keyword)
        success &= self._set_any_words_radio()
        success &= self._fill_date_fields(start_date, end_date)

        if success:
            return self._click_search_button()
        else:
            logger.error("Search form preparation failed")
            return False

    def set_results_per_page(self, per_page=50):
        """Set results per page AFTER search results appear"""
        try:
            results_dropdown_selector = "#ctl00_ContentPlaceHolder1_WSExtendedGridNP1_GridView1_ctl01_ddlPerPage"

            # Wait longer for the dropdown to appear and be ready
            results_dropdown = self.page.wait_for_selector(
                results_dropdown_selector, timeout=15000
            )

            # Check current selection (for select elements, use get_attribute)
            current_selection = results_dropdown.get_attribute("value")
            logger.debug(f"Current results per page: {current_selection}")

            if current_selection == str(per_page):
                logger.info(f"Results per page already set to {per_page}")
                return True

            # Select the option and trigger change
            results_dropdown.select_option(str(per_page))
            logger.info(f"Set results per page to {per_page}")

            # Wait for page reload and verify the change took effect
            time.sleep(5)

            # Verify the setting worked by counting results
            time.sleep(2)  # Additional wait for stability
            view_buttons = self.page.query_selector_all(
                "#ctl00_ContentPlaceHolder1_WSExtendedGridNP1_GridView1 input[id*='btnView2'].viewButton"
            )
            actual_count = len(view_buttons)
            logger.info(
                f"After setting per_page={per_page}, found {actual_count} buttons"
            )

            return True

        except Exception as e:
            logger.warning(f"Error setting results per page to {per_page}: {e}")
            return False

    def get_view_buttons(self):
        """Find all view buttons on the current page - only from results table"""
        try:
            # Wait for the results table to be stable
            self.page.wait_for_selector(
                "#ctl00_ContentPlaceHolder1_WSExtendedGridNP1_GridView1", timeout=15000
            )
            time.sleep(
                1
            )  # Reduced wait time since we're not doing expensive operations

            # Use specific selector for ONLY the visible btnView2 buttons (not hidden btnView buttons)
            view_buttons = self.page.query_selector_all(
                "#ctl00_ContentPlaceHolder1_WSExtendedGridNP1_GridView1 input[id*='btnView2'].viewButton"
            )

            logger.debug(f"Found {len(view_buttons)} view buttons")

            # Extract and log button IDs from onclick events for debugging
            button_ids = []
            unique_ids = set()
            for i, button in enumerate(view_buttons):
                try:
                    onclick = button.get_attribute("onclick") or ""
                    # Extract ID from onclick like: javascript:location.href='Details.aspx?SID=...&ID=852667'
                    id_match = re.search(r"ID=([0-9]+)", onclick)
                    button_id = id_match.group(1) if id_match else f"unknown_{i}"
                    button_ids.append(button_id)
                    unique_ids.add(button_id)
                except:
                    button_ids.append(f"error_{i}")

            logger.debug(
                f"Button IDs found: {button_ids[:10]}{'...' if len(button_ids) > 10 else ''}"
            )
            logger.debug(
                f"Unique IDs: {len(unique_ids)} out of {len(button_ids)} buttons"
            )

            # Validate we have diverse button IDs (not all the same)
            if len(unique_ids) < max(
                1, len(button_ids) // 10
            ):  # Should have at least 10% unique IDs
                logger.warning(
                    f"⚠️ Possible stale DOM - only {len(unique_ids)} unique IDs from {len(button_ids)} buttons"
                )
                logger.warning(f"⚠️ All button IDs: {button_ids}")

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
                "automated queries",
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
                                logger.warning(
                                    f"Automation detected in frame {frame_url}: {message}"
                                )
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
            self.page.wait_for_selector(iframe_selector, timeout=10000)

            # Find the reCAPTCHA frame
            recaptcha_frame = self.find_recaptcha_frame()

            if recaptcha_frame:
                # Wait specifically for checkbox to be ready and interactive
                checkbox_found = False
                checkbox_selectors = [
                    "#recaptcha-anchor",
                    ".rc-anchor-checkbox",
                    "span[role='checkbox']",
                ]

                logger.debug(
                    "⏳ Waiting for captcha checkbox to be fully loaded and interactive..."
                )

                # Wait up to 15 seconds for checkbox to be ready
                for attempt in range(
                    10
                ):  # 10 attempts, 1.5 seconds each = 15 seconds max
                    for selector in checkbox_selectors:
                        try:
                            # Wait for element to exist and be visible
                            checkbox = recaptcha_frame.wait_for_selector(
                                selector, timeout=1500
                            )
                            if checkbox and checkbox.is_visible():
                                # Verify it's actually interactive by checking if it has proper attributes
                                aria_checked = checkbox.get_attribute("aria-checked")
                                if (
                                    aria_checked is not None
                                ):  # Checkbox is fully loaded with ARIA attributes
                                    # Additional small wait to ensure full interactivity
                                    time.sleep(0.5)
                                    checkbox.click()
                                    logger.info("✅ Clicked reCAPTCHA checkbox")
                                    checkbox_found = True
                                    break
                        except:
                            continue

                    if checkbox_found:
                        break
                    else:
                        logger.debug(
                            f"⏳ Waiting for checkbox to be interactive... attempt {attempt + 1}/10"
                        )
                        time.sleep(1.5)

                if not checkbox_found:
                    logger.warning(
                        "⚠️ Checkbox not ready after 15 seconds - trying fallback click"
                    )
                    # Fallback: try clicking without full verification
                    for selector in checkbox_selectors:
                        try:
                            checkbox = recaptcha_frame.query_selector(selector)
                            if checkbox:
                                checkbox.click()
                                logger.info("✅ Clicked reCAPTCHA checkbox (fallback)")
                                checkbox_found = True
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
                    logger.error(
                        "reCAPTCHA has detected automation - this session is compromised"
                    )
                    return False

                if self.has_image_challenge():
                    logger.warning(
                        "Image challenge detected - attempting 2captcha solving"
                    )

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
                        logger.error(
                            "2captcha solver not available - skipping image challenge"
                        )
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
                        timeout=5000,
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
                ".rc-imageselect-payload",  # The payload area
                ".rc-imageselect-table",
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
                            logger.debug(
                                f"Error checking selector {selector} in frame {frame_url}: {e}"
                            )
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
            recaptcha_divs = self.page.query_selector_all("[data-sitekey]")
            if recaptcha_divs:
                site_key = recaptcha_divs[0].get_attribute("data-sitekey")
                logger.info(f"Found site key from div: {site_key}")

            # Method 2: Check frame sources for site key parameter
            if not site_key:
                frames = self.page.frames
                for frame in frames:
                    frame_url = frame.url
                    if "recaptcha" in frame_url.lower():
                        # Extract from URL parameters (k= parameter)
                        site_key_match = re.search(r"[?&]k=([^&]+)", frame_url)
                        if site_key_match:
                            site_key = site_key_match.group(1)
                            logger.info(f"Found site key from frame URL: {site_key}")
                            break

            # Method 3: Check script tags for grecaptcha calls
            if not site_key:
                scripts = self.page.query_selector_all("script")
                for script in scripts:
                    script_content = script.text_content() or ""
                    # Look for sitekey in various formats
                    patterns = [
                        r'[\'"]sitekey[\'"]:\s*[\'"]([^\'\"]+)[\'"]',
                        r'grecaptcha\.render\([^}]*[\'"]sitekey[\'"]:\s*[\'"]([^\'\"]+)[\'"]',
                        r'data-sitekey=[\'"]([^\'\"]+)[\'"]',
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

            return {"websiteURL": page_url, "websiteKey": site_key}

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
            logger.info(
                f"Site key: {captcha_details['websiteKey'][:20]}..."
            )  # Hide full key for security

            # Submit captcha to 2captcha service with timeout handling
            start_time = time.time()

            try:
                result = self.solver.recaptcha(
                    sitekey=captcha_details["websiteKey"],
                    url=captcha_details["websiteURL"],
                )

                solve_time = time.time() - start_time
                logger.info(f"2captcha solve completed in {solve_time:.1f} seconds")

                if result and result.get("code"):
                    logger.info("✅ 2captcha successfully solved reCAPTCHA")
                    logger.info(
                        f"Response token length: {len(result['code'])} characters"
                    )
                    return result["code"]  # This is the g-recaptcha-response token
                else:
                    logger.error("❌ 2captcha returned empty result")
                    return None

            except Exception as solve_error:
                solve_time = time.time() - start_time
                logger.error(
                    f"❌ 2captcha API error after {solve_time:.1f}s: {solve_error}"
                )

                # Check for specific error types
                error_str = str(solve_error).lower()
                if "insufficient funds" in error_str or "zero balance" in error_str:
                    logger.error("💰 2captcha account has insufficient funds")
                elif "invalid api key" in error_str:
                    logger.error("🔑 2captcha API key is invalid")
                elif "timeout" in error_str:
                    logger.error("⏱️ 2captcha solving timed out (captcha too complex)")
                elif "no slot available" in error_str:
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
            safe_response = (
                captcha_response.replace("\\", "\\\\")
                .replace("'", "\\'")
                .replace('"', '\\"')
            )

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

            if result == "success":
                logger.info("✅ Token submitted successfully")
            elif result == "element_not_found":
                logger.error("❌ Could not find g-recaptcha-response element")
                return False

            # Wait for reCAPTCHA to process the token
            logger.info("⏳ Waiting for reCAPTCHA to process token...")

            # Brief wait for token to be processed, then click immediately
            time.sleep(2)
            logger.debug(
                "🔘 Proceeding to click View Notice button without waiting for captcha to clear"
            )

            time.sleep(1)  # Brief pause before trying to click button

            # Try clicking the View Notice button with multiple methods to bypass overlay
            logger.info("🔘 Attempting to click View Notice button...")

            try:
                view_notice_btn = self.page.wait_for_selector(
                    "#ctl00_ContentPlaceHolder1_PublicNoticeDetailsBody1_btnViewNotice",
                    timeout=5000,
                )

                # Method 1: Try regular click first
                try:
                    view_notice_btn.click(timeout=3000)
                    logger.info(
                        "✅ Clicked View Notice button (method 1 - regular click)"
                    )
                except:
                    # Method 2: Force click using JavaScript
                    try:
                        self.page.evaluate(
                            "(element) => element.click()", view_notice_btn
                        )
                        logger.info(
                            "✅ Clicked View Notice button (method 2 - JavaScript click)"
                        )
                    except:
                        # Method 3: Click at coordinates to bypass overlay
                        try:
                            bbox = view_notice_btn.bounding_box()
                            if bbox:
                                # Click at button center coordinates
                                self.page.mouse.click(
                                    bbox["x"] + bbox["width"] / 2,
                                    bbox["y"] + bbox["height"] / 2,
                                )
                                logger.info(
                                    "✅ Clicked View Notice button (method 3 - coordinate click)"
                                )
                            else:
                                # Method 4: Try clicking by selector with force
                                self.page.evaluate(
                                    """
                                    document.querySelector('#ctl00_ContentPlaceHolder1_PublicNoticeDetailsBody1_btnViewNotice').click();
                                """
                                )
                                logger.info(
                                    "✅ Clicked View Notice button (method 4 - direct selector)"
                                )
                        except Exception as final_error:
                            logger.error(f"❌ All click methods failed: {final_error}")
                            return False

                time.sleep(3)

                # Check if we successfully accessed the notice
                page_content = self.page.content()
                if "You must complete the reCAPTCHA" not in page_content:
                    logger.info(
                        "🎉 2captcha response accepted! Notice accessed successfully."
                    )
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
        """Extract required fields from current page using GPT parser"""
        try:
            # Get the raw page text
            page_text = self.page.content()

            # Use GPT parser to extract structured data
            logger.debug(f"🔍 Extracting data from notice...")
            data = extract_notice_data_gpt(page_text, source_url)

            # Log what we extracted for debugging
            if data["first_name"] and data["last_name"]:
                logger.debug(
                    f"✅ Extracted: {data['first_name']} {data['last_name']} @ {data['street']}"
                )
            else:
                logger.warning(f"⚠️ No name extracted from notice")

            return data

        except Exception as e:
            logger.error(f"❌ Error extracting notice data: {e}")
            # Return empty structure on error
            return {
                "first_name": "",
                "last_name": "",
                "street": "",
                "city": "",
                "state": "MN",
                "zip": "",
                "date_of_sale": "",
                "plaintiff": "",
                "link": source_url,
            }

    def human_like_delay(self, notice_num=None):
        """Add human-like delays to avoid detection"""
        # Regular delay between requests
        delay = random.uniform(self.min_delay, self.max_delay)
        logger.debug(f"⏱️  Human-like delay: {delay:.1f}s")
        time.sleep(delay)

        # Longer pause every N notices
        if notice_num and notice_num % self.long_pause_every == 0:
            long_delay = random.uniform(*self.long_pause_duration)
            logger.info(
                f"☕ Taking longer break after {notice_num} notices: {long_delay:.1f}s"
            )
            time.sleep(long_delay)

    def verify_on_results_page(self, timeout=5000):
        """Verify we're on the search results page with view buttons"""
        try:
            # Quick URL check first
            current_url = self.page.url
            if "Search.aspx" not in current_url:
                logger.debug(f"URL check failed: {current_url}")
                return False

            # Wait for results table to be present
            try:
                self.page.wait_for_selector(
                    "#ctl00_ContentPlaceHolder1_WSExtendedGridNP1_GridView1",
                    timeout=timeout,
                )
            except Exception:
                logger.debug("Results table not found")
                return False

            # Verify we have view buttons
            view_buttons = self.page.query_selector_all(
                "#ctl00_ContentPlaceHolder1_WSExtendedGridNP1_GridView1 input[id*='btnView2'].viewButton"
            )

            if len(view_buttons) >= 10:  # Should have many buttons on results page
                logger.debug(
                    f"✅ Results page verified - {len(view_buttons)} buttons found"
                )
                return True
            else:
                logger.debug(f"Insufficient buttons found: {len(view_buttons)}")
                return False

        except Exception as e:
            logger.debug(f"Results page verification failed: {e}")
            return False

    def navigate_back_to_results(self):
        """Navigate back to search results page using browser back (handles captcha case)"""
        try:
            # Try up to 2 back clicks to handle captcha navigation
            for attempt in range(2):
                logger.debug(f"🔙 Browser back attempt {attempt + 1}/2")
                self.page.go_back()
                time.sleep(3)

                # Check if we're back on results page
                if self.verify_on_results_page():
                    logger.debug(
                        f"✅ Successfully navigated back after {attempt + 1} back click(s)"
                    )
                    return True
                else:
                    logger.debug(f"Not on results page yet (attempt {attempt + 1}/2)")

            # Failed after 2 attempts
            logger.error("❌ Failed to navigate back to results after 2 back clicks")
            return False

        except Exception as e:
            logger.error(f"❌ Browser back navigation error: {e}")
            return False

    def has_next_page(self):
        """Check if there's a next page available"""
        try:
            # Look for next page button - common selectors for ASP.NET GridView pagination
            next_selectors = [
                "input[id*='btnNext']",
                "input[value='Next']",
                "input[title*='Next']",
                "a[title*='Next']",
                ".pager input[type='image'][title*='Next']",
                ".pagination input[type='image'][title*='Next']",
                "input[type='image'][src*='next']",
                "input[type='image'][src*='Next']",
            ]

            for selector in next_selectors:
                try:
                    next_button = self.page.query_selector(selector)
                    if next_button and next_button.is_enabled():
                        logger.debug(f"✅ Found enabled next page button: {selector}")
                        return True
                except Exception:
                    continue

            logger.debug(
                "📄 No next page button found or button is disabled - likely last page"
            )
            return False

        except Exception as e:
            logger.debug(f"Error checking for next page: {e}")
            return False

    def get_current_page_info(self):
        """Get current page information if available"""
        try:
            # Look for page information text like "Page 1 of 5 Pages"
            page_info_selectors = [
                ".pager",
                ".pagination",
                "*:has-text('Page ')",
                "*:has-text(' of ')",
                "span:has-text('Page')",
                "td:has-text('Page')",
            ]

            for selector in page_info_selectors:
                try:
                    element = self.page.query_selector(selector)
                    if element:
                        text = element.inner_text()
                        if "Page" in text and "of" in text:
                            return text.strip()
                except Exception:
                    continue

            return "Page info not found"

        except Exception as e:
            logger.debug(f"Error getting page info: {e}")
            return "Page info error"

    def click_next_page(self):
        """Click the next page button and wait for results to load"""
        try:
            next_selectors = [
                "input[id*='btnNext']",
                "input[value='Next']",
                "input[title*='Next']",
                "a[title*='Next']",
                ".pager input[type='image'][title*='Next']",
                ".pagination input[type='image'][title*='Next']",
                "input[type='image'][src*='next']",
                "input[type='image'][src*='Next']",
            ]

            for selector in next_selectors:
                try:
                    next_button = self.page.query_selector(selector)
                    if next_button and next_button.is_enabled():
                        logger.info(f"🔄 Clicking next page button...")

                        # Add human-like delay before clicking
                        time.sleep(random.uniform(1, 3))

                        next_button.click(timeout=10000)
                        time.sleep(3)  # Wait for page transition

                        # Wait for new results table to load
                        self.page.wait_for_selector(
                            "#ctl00_ContentPlaceHolder1_WSExtendedGridNP1_GridView1",
                            timeout=15000,
                        )

                        # Additional wait for view buttons to be ready
                        self.page.wait_for_selector(
                            "#ctl00_ContentPlaceHolder1_WSExtendedGridNP1_GridView1 input[id*='btnView2'].viewButton",
                            timeout=10000,
                        )

                        time.sleep(2)  # Final stabilization wait
                        logger.info(f"✅ Successfully navigated to next page")
                        return True

                except Exception as e:
                    logger.debug(f"Next button click failed with {selector}: {e}")
                    continue

            logger.warning("❌ No working next page button found")
            return False

        except Exception as e:
            logger.error(f"Error clicking next page: {e}")
            return False

    def scrape_notices(self, keywords=["foreclosure", "bankruptcy"], days_back=1):
        """Main scraping function with pagination support"""
        logger.info(f"Starting scrape for keywords: {keywords}")

        # Ensure VPN connection before scraping (with better retry logic)
        if hasattr(self, "vpn_manager") and self.vpn_manager.enabled:
            if not self.vpn_manager.ensure_connected():
                logger.warning(
                    "⚠️ VPN connection could not be established - continuing without VPN protection"
                )
                logger.warning(
                    "📝 Note: Scraping without VPN may result in IP blocking if running frequently"
                )
            else:
                logger.info(
                    f"✅ VPN ready for scraping: {self.vpn_manager.get_status()}"
                )
        else:
            logger.info("🌐 VPN disabled - scraper running without IP protection")

        combined_keywords = " ".join(keywords)

        # Store search keywords for recovery purposes
        self._last_search_keywords = combined_keywords

        try:
            # Perform search first to get the search date
            if not self.search_notices(combined_keywords, days_back):
                logger.error(f"Search failed for keywords: {combined_keywords}")
                return

            # Initialize CSV writer with search date for filename
            search_date_str = self._search_date.strftime("%Y-%m-%d")
            filename = f"mn_notices_{search_date_str}.csv"
            self.init_csv_writer(filename)

            # Set results per page to 50
            self.set_results_per_page(50)

            # Initialize pagination tracking
            page_number = 1
            total_notices_all_pages = 0

            # Process all pages
            while True:
                logger.info(f"📄 Processing page {page_number}")
                page_info = self.get_current_page_info()
                if page_info != "Page info not found":
                    logger.info(f"📊 {page_info}")

                # Get view buttons for current page
                view_buttons = self.get_view_buttons()
                total_notices = len(view_buttons)
                logger.info(f"🌯 Found {total_notices} notices on page {page_number}")

                # Validate page results
                if total_notices == 0:
                    logger.error(f"❌ No view buttons found on page {page_number}!")
                    break
                elif total_notices > 50:
                    logger.error(
                        f"❌ Found {total_notices} buttons but expected max 50 per page!"
                    )
                    logger.error(
                        "This suggests a selector issue or page loading problem."
                    )
                    break
                elif total_notices < 50 and self.has_next_page():
                    logger.warning(
                        f"⚠️ Found only {total_notices} notices but next page exists - possible loading issue"
                    )
                elif total_notices < 50:
                    logger.info(f"📄 Last page detected with {total_notices} notices")

                # Track processed notice IDs to avoid duplicates (per-page like original)
                processed_notice_ids = set()

                # Process each notice using ID-based iteration (not index-based)
                notices_processed = 0
                while notices_processed < total_notices:
                    logger.info(
                        f"📄 Processing notice {notices_processed + 1}/{total_notices} on page {page_number}"
                    )

                    # Get fresh view buttons
                    current_view_buttons = self.get_view_buttons()
                    if not current_view_buttons:
                        logger.warning("No view buttons found - ending processing")
                        break

                    # Find the next unprocessed notice
                    button = None
                    notice_id = None

                    for candidate_button in current_view_buttons:
                        # Extract notice ID from button onclick
                        onclick = candidate_button.get_attribute("onclick") or ""
                        id_match = re.search(r"ID=([0-9]+)", onclick)
                        candidate_id = id_match.group(1) if id_match else None

                        if candidate_id and candidate_id not in processed_notice_ids:
                            # Found an unprocessed notice
                            button = candidate_button
                            notice_id = candidate_id
                            logger.debug(f"🔍 Found unprocessed notice ID: {notice_id}")
                            break

                    if not button or not notice_id:
                        logger.warning(
                            "No more unprocessed notices found on current page"
                        )
                        break

                    # Track this notice as being processed
                    processed_notice_ids.add(notice_id)
                    notices_processed += 1
                    total_notices_all_pages += 1

                    # Add human-like delay before clicking button
                    self.human_like_delay(notice_num=notices_processed)

                    # Click view button with multiple methods
                    try:
                        # Method 1: Regular click
                        button.click(timeout=5000)
                        logger.debug(
                            f"✅ Clicked view button for notice {notice_id} (regular click)"
                        )
                        time.sleep(2)
                    except Exception as e:
                        logger.debug(
                            f"Regular click failed for notice {notice_id}: {e}"
                        )
                        try:
                            # Method 2: JavaScript click to bypass overlays
                            self.page.evaluate("(element) => element.click()", button)
                            logger.debug(
                                f"✅ Clicked view button for notice {notice_id} (JavaScript click)"
                            )
                            time.sleep(2)
                        except Exception as e2:
                            logger.warning(
                                f"❌ Failed to click view button for notice {notice_id} with all methods: {e2}"
                            )
                            continue

                    # Handle captcha if present
                    if self.check_for_captcha():
                        logger.info(f"🤖 Captcha on notice #{notice_id}")
                        if self.solve_captcha_simple():
                            logger.info(f"✅ Captcha solved for notice #{notice_id}")
                        else:
                            logger.warning(
                                f"❌ Failed to solve captcha for notice #{notice_id} - skipping"
                            )
                            self.captcha_skipped += 1
                            self.navigate_back_to_results()
                            continue

                    # Extract data
                    current_url = self.page.url
                    logger.debug(f"Current URL: {current_url}")

                    # Extract notice ID from URL for additional duplicate checking
                    url_id_match = re.search(r"ID=([0-9]+)", current_url)
                    url_notice_id = url_id_match.group(1) if url_id_match else "unknown"

                    data = self.extract_notice_data(current_url)
                    data["notice_id"] = url_notice_id  # Add for debugging

                    # Write record immediately instead of accumulating in memory
                    if self.write_record_immediately(data):
                        if data["first_name"] and data["last_name"]:
                            logger.info(
                                f"✅ Extracted #{self.records_written}: {data['first_name']} {data['last_name']} (ID: {url_notice_id})"
                            )
                        else:
                            logger.warning(
                                f"❌ Incomplete data for notice #{notice_id} (ID: {url_notice_id})"
                            )
                    else:
                        logger.error(
                            f"❌ Failed to write record for notice #{notice_id} (ID: {url_notice_id})"
                        )
                        # Fallback: add to memory if immediate writing fails
                        self.results.append(data)

                    # Navigate back to results for next iteration with retry logic
                    navigation_success = False
                    for nav_attempt in range(2):  # Try navigation twice
                        if self.navigate_back_to_results():
                            navigation_success = True
                            logger.debug(
                                f"✅ Navigation successful on attempt {nav_attempt + 1}"
                            )
                            time.sleep(random.uniform(1, 3))
                            break
                        else:
                            logger.warning(
                                f"⚠️ Navigation attempt {nav_attempt + 1}/2 failed for notice {notice_id}"
                            )
                            if (
                                nav_attempt == 0
                            ):  # Give it one more try with a longer wait
                                time.sleep(5)

                    if not navigation_success:
                        logger.error(
                            f"❌ All navigation attempts failed after notice {notice_id}"
                        )
                        logger.error(
                            f"📊 Partial results: Successfully processed {self.records_written} notices"
                        )

                        # Try one last recovery attempt - full session restoration
                        logger.info("🔄 Attempting full session recovery...")
                        try:
                            if self.navigate_back_to_results():
                                logger.info(
                                    "✅ Session recovery successful - continuing..."
                                )
                                navigation_success = True
                            else:
                                logger.error(
                                    "❌ Session recovery failed - ending scrape"
                                )
                                break
                        except Exception as recovery_error:
                            logger.error(
                                f"❌ Recovery attempt failed: {recovery_error}"
                            )
                            break

                    # Memory management: garbage collection every 25 notices
                    if self.records_written % 25 == 0:
                        logger.debug(
                            f"🧹 Running garbage collection after {self.records_written} records"
                        )
                        gc.collect()

                    # Wait for results page to load properly with more robust checks
                    try:
                        # Wait for the results table container first
                        self.page.wait_for_selector(
                            "#ctl00_ContentPlaceHolder1_WSExtendedGridNP1_GridView1",
                            timeout=20000,
                        )
                        time.sleep(2)

                        # Then wait for view buttons to be ready
                        self.page.wait_for_selector(
                            "#ctl00_ContentPlaceHolder1_WSExtendedGridNP1_GridView1 input[id*='btnView2'].viewButton",
                            timeout=20000,
                        )
                        time.sleep(3)  # Additional wait for stability

                        # Verify the page is fully loaded by checking for multiple elements
                        buttons_ready = False
                        for attempt in range(3):
                            current_buttons = self.page.query_selector_all(
                                "#ctl00_ContentPlaceHolder1_WSExtendedGridNP1_GridView1 input[id*='btnView2'].viewButton"
                            )

                            if len(current_buttons) >= (
                                total_notices - 5
                            ):  # Allow some tolerance
                                buttons_ready = True
                                logger.debug(
                                    f"✅ Results page ready with {len(current_buttons)} buttons"
                                )
                                break
                            else:
                                logger.debug(
                                    f"⏳ Waiting for buttons to load... ({len(current_buttons)}/{total_notices})"
                                )
                                time.sleep(2)

                        if not buttons_ready:
                            logger.warning(
                                f"⚠️ Results page may not be fully loaded after notice {notice_id}"
                            )

                    except Exception as e:
                        logger.error(
                            f"Results page did not load properly after notice {notice_id}: {e}"
                        )
                        logger.error("Attempting to continue anyway...")
                        time.sleep(5)  # Give it more time before continuing

                # Page completed - check for next page
                logger.info(
                    f"✅ Completed page {page_number} - processed {notices_processed} notices"
                )

                # Check if there are more pages
                if self.has_next_page():
                    logger.info(
                        f"🔄 Next page available - moving to page {page_number + 1}"
                    )
                    if self.click_next_page():
                        page_number += 1
                        continue  # Continue to next page
                    else:
                        logger.error(
                            "❌ Failed to navigate to next page - ending pagination"
                        )
                        break
                else:
                    logger.info(f"📄 Reached last page - no more pages to process")
                    break

            # Final pagination summary with immediate writing stats
            logger.info(
                f"🎉 Pagination complete! Processed {page_number} pages with {self.records_written} total notices written to CSV"
            )

            # Close CSV writer
            self.close_csv_writer()

        except Exception as e:
            logger.error(f"Error scraping keywords '{combined_keywords}': {e}")
            # Ensure CSV writer is closed on error
            if self.csv_writer:
                self.close_csv_writer()

    def save_to_csv(self, filename=None):
        """Save results to CSV file"""
        csvs_dir = "csvs"
        if not os.path.exists(csvs_dir):
            os.makedirs(csvs_dir)

        if not filename:
            # Use search date if available, otherwise use current date
            date_to_use = getattr(self, "_search_date", datetime.now())
            filename = f"mn_notices_{date_to_use.strftime('%Y-%m-%d')}.csv"

        full_path = os.path.join(csvs_dir, filename)
        fieldnames = [
            "first_name",
            "last_name",
            "street",
            "city",
            "state",
            "zip",
            "date_of_sale",
            "plaintiff",
            "link",
            "notice_id",
        ]

        with open(full_path, "w", newline="", encoding="utf-8") as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(self.results)

        # Debug: Check for duplicates in final results
        seen_ids = set()
        duplicate_count = 0
        for result in self.results:
            notice_id = result.get("notice_id", "unknown")
            if notice_id in seen_ids:
                duplicate_count += 1
                logger.warning(f"Duplicate in final results - ID {notice_id}")
            seen_ids.add(notice_id)

        if duplicate_count > 0:
            logger.warning(f"Found {duplicate_count} duplicates in final results")

        logger.info(f"📁 Saved {len(self.results)} records to {filename}")
        return full_path

    def init_csv_writer(self, filename=None):
        """Initialize CSV file for immediate writing"""
        csvs_dir = "csvs"
        if not os.path.exists(csvs_dir):
            os.makedirs(csvs_dir)

        if not filename:
            # Use search date if available, otherwise use current date
            date_to_use = getattr(self, "_search_date", datetime.now())
            filename = f"mn_notices_{date_to_use.strftime('%Y-%m-%d')}.csv"

        full_path = os.path.join(csvs_dir, filename)
        fieldnames = [
            "first_name",
            "last_name",
            "street",
            "city",
            "state",
            "zip",
            "date_of_sale",
            "plaintiff",
            "link",
            "notice_id",
        ]

        # Open CSV file and write header
        self.csv_file = open(full_path, "w", newline="", encoding="utf-8")
        self.csv_writer = csv.DictWriter(self.csv_file, fieldnames=fieldnames)
        self.csv_writer.writeheader()
        self.csv_file.flush()  # Ensure header is written immediately

        logger.info(f"📄 Initialized CSV file: {filename}")
        return full_path

    def write_record_immediately(self, data):
        """Write a single record to CSV immediately"""
        if self.csv_writer is None:
            logger.error("❌ CSV writer not initialized. Call init_csv_writer() first.")
            return False

        try:
            self.csv_writer.writerow(data)
            self.csv_file.flush()  # Ensure data is written to disk
            self.records_written += 1
            return True
        except Exception as e:
            logger.error(f"❌ Failed to write record to CSV: {e}")
            return False

    def close_csv_writer(self):
        """Close CSV file writer"""
        if self.csv_file:
            self.csv_file.close()
            self.csv_file = None
            self.csv_writer = None
            logger.info(
                f"📁 CSV file closed. Total records written: {self.records_written}"
            )

    def close(self):
        """Close the browser and disconnect VPN"""
        try:
            # Close CSV writer if still open
            if self.csv_writer:
                self.close_csv_writer()

            if self.page:
                self.page.close()
            if self.context:
                self.context.close()
            if self.browser:
                self.browser.close()
            if self.playwright:
                self.playwright.stop()

            # Disconnect VPN
            if hasattr(self, "vpn_manager"):
                self.vpn_manager.disconnect()

        except Exception as e:
            logger.warning(f"Error during cleanup: {e}")


def run_mn_public_notice_scrape(headless: bool):
    scraper = None
    try:
        scraper = MNNoticeScraperClean(headless=headless)
        scraper.scrape_notices(["foreclosure", "bankruptcy"], days_back=1)

        print(f"\n🎉 MN Public Notice scraping complete! CSV saved with immediate writing")
        print(f"📊 Total records extracted: {scraper.records_written}")
        print(f"✅ Captchas solved: {scraper.captcha_solved}")
        print(f"⏭️  Notices skipped due to unsolved captcha: {scraper.captcha_skipped}")

        if scraper.records_written > 0:
            avg_delay = (scraper.min_delay + scraper.max_delay) / 2
            total_minutes = (scraper.records_written * avg_delay) / 60
            print(
                f"🐌 Rate limiting added ~{total_minutes:.1f} minutes to prevent IP blocks"
            )

        if scraper.solver:
            print(
                f"💰 Estimated 2captcha cost: ~${(scraper.captcha_solved * 0.003):.3f}"
            )
    except Exception as e:
        logger.error(f"MN Public Notice scraper failed: {e}")
    finally:
        if scraper:
            scraper.close()


def run_star_tribune_scrape():
    scraper = None
    try:
        scraper = StarTribuneScraper()
        scraper.scrape_latest_notices()
        print("\n📰 Star Tribune scraping complete!")
        print(f"📊 Total records extracted: {scraper.records_written}")
        if scraper.output_path:
            print(f"📁 CSV saved to: {scraper.output_path}")
    except Exception as e:
        logger.error(f"Star Tribune scraper failed: {e}")
    finally:
        if scraper:
            scraper.close()


def parse_arguments():
    parser = argparse.ArgumentParser(
        description="Scrape foreclosure notices from MN Public Notice and Star Tribune."
    )
    parser.add_argument(
        "--site",
        choices=["mn", "star", "both"],
        help="Choose which site(s) to scrape. Defaults to interactive prompt.",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Run the MN Public Notice Playwright browser in headless mode.",
    )
    return parser.parse_args()


def prompt_site_choice() -> str:
    options = (
        "\nSelect the site(s) to scrape:\n"
        "  1) MN Public Notice (mnpublicnotice.com)\n"
        "  2) Star Tribune Foreclosures (classifieds.startribune.com)\n"
        "  3) Both\n"
    )
    print(options)
    mapping = {"1": "mn", "2": "star", "3": "both"}
    while True:
        choice = input("Enter 1, 2, or 3 [default 1]: ").strip() or "1"
        if choice in mapping:
            return mapping[choice]
        print("Please enter 1, 2, or 3.")


def resolve_site_choice(cli_choice: Optional[str]) -> str:
    if cli_choice:
        return cli_choice

    env_choice = os.getenv("SCRAPER_SITE_CHOICE")
    if env_choice and env_choice.lower() in {"mn", "star", "both"}:
        return env_choice.lower()

    if not sys.stdin.isatty():
        logger.info(
            "🛈 No interactive terminal detected; defaulting to MN Public Notice."
        )
        return "mn"

    return prompt_site_choice()


def print_parsing_summary():
    parsing_stats = get_parsing_stats()
    if parsing_stats["total_parses"] == 0:
        return

    print(
        f"\n🤖 GPT parsing success rate: {parsing_stats['gpt_success_rate']}% "
        f"({parsing_stats['gpt_successful']}/{parsing_stats['total_parses']})"
    )
    if parsing_stats["regex_fallbacks"] > 0:
        print(f"🔄 Regex fallbacks used: {parsing_stats['regex_fallbacks']} times")

    gpt_cost = parsing_stats["gpt_successful"] * 0.002  # ~$0.002 per GPT call
    if gpt_cost > 0:
        print(f"🧠 Estimated GPT cost: ~${gpt_cost:.3f}")


def main():
    args = parse_arguments()
    site_choice = resolve_site_choice(args.site)
    run_mn = site_choice in {"mn", "both"}
    run_star = site_choice in {"star", "both"}

    if run_mn:
        run_mn_public_notice_scrape(headless=args.headless)
    if run_star:
        run_star_tribune_scrape()

    print_parsing_summary()


if __name__ == "__main__":
    main()
