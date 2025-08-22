#!/usr/bin/env python3
"""
Test script to launch browser with Buster and pause for manual inspection
"""

from playwright.sync_api import sync_playwright
import os
import time
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def get_buster_extension_path():
    """Get path to Buster extension directory"""
    buster_id = "mpbjkejclgfgadiemmefgebjfooflfhl"
    
    possible_paths = [
        './buster_extension',
        './extensions/buster',
        os.path.expanduser(f'~\\AppData\\Local\\Google\\Chrome\\User Data\\Default\\Extensions\\{buster_id}'),  # Windows
        os.path.expanduser(f'~/.config/google-chrome/Default/Extensions/{buster_id}'),  # Linux
        os.path.expanduser(f'~/Library/Application Support/Google/Chrome/Default/Extensions/{buster_id}'),  # macOS
    ]
    
    for path in possible_paths:
        if os.path.exists(path):
            # For Chrome extension paths, find version subdirectory
            if 'Extensions' in path and buster_id in path:
                try:
                    version_dirs = [d for d in os.listdir(path) 
                                  if os.path.isdir(os.path.join(path, d))]
                    if version_dirs:
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
    
    logger.warning("Buster extension not found")
    return None

def main():
    """Launch test browser with Buster extension"""
    
    # Get Buster extension path
    buster_path = get_buster_extension_path()
    
    if not buster_path:
        print("❌ Buster extension not found!")
        input("Press Enter to continue without Buster...")
    
    # Setup Playwright
    playwright = sync_playwright().start()
    
    # Launch arguments
    launch_args = [
        '--no-sandbox',
        '--disable-dev-shm-usage',
        '--disable-blink-features=AutomationControlled'
    ]
    
    # Add Buster extension if found
    if buster_path:
        launch_args.extend([
            f'--load-extension={buster_path}',
            f'--disable-extensions-except={buster_path}',
            '--disable-web-security',
            '--allow-running-insecure-content'
        ])
        print(f"✅ Loading Buster extension from: {buster_path}")
    
    try:
        # Launch browser with persistent context
        if buster_path:
            context = playwright.chromium.launch_persistent_context(
                user_data_dir='./test_chrome_profile',
                headless=False,  # Always visible for testing
                args=launch_args,
                viewport={'width': 1920, 'height': 1080}
            )
            browser = None
        else:
            browser = playwright.chromium.launch(
                headless=False,
                args=launch_args
            )
            context = browser.new_context(viewport={'width': 1920, 'height': 1080})
        
        page = context.new_page()
        
        print("🌐 Browser launched!")
        print("📋 Instructions:")
        print("1. Navigate to: https://www.mnpublicnotice.com/Search.aspx")
        print("2. Search for 'foreclosure bankruptcy'") 
        print("3. Click a View button to trigger captcha")
        print("4. When complex captcha appears, right-click and 'Inspect Element'")
        print("5. Look for Buster-related elements in the DOM")
        print("6. Note down the selectors (button class/id/title)")
        print()
        
        # Navigate to the search page to get started
        page.goto("https://www.mnpublicnotice.com/Search.aspx")
        
        print("🔍 Page loaded. Follow the instructions above.")
        print("⏸️  Press Enter when you're done inspecting...")
        
        # Wait for user input
        input()
        
        print("🔍 Getting current page state...")
        
        # Try to find any Buster-related elements
        buster_elements = page.query_selector_all("*[title*='buster' i], *[class*='buster' i], *[id*='buster' i]")
        if buster_elements:
            print(f"✅ Found {len(buster_elements)} Buster-related elements:")
            for i, elem in enumerate(buster_elements):
                try:
                    tag = elem.evaluate('el => el.tagName')
                    title = elem.get_attribute('title') or ''
                    class_name = elem.get_attribute('class') or ''
                    id_attr = elem.get_attribute('id') or ''
                    text = elem.text_content()[:50] or ''
                    print(f"  [{i+1}] {tag}: title='{title}' class='{class_name}' id='{id_attr}' text='{text}'")
                except Exception as e:
                    print(f"  [{i+1}] Error reading element: {e}")
        else:
            print("❌ No Buster elements found")
            
        # Also check for any buttons in captcha area
        captcha_buttons = page.query_selector_all(".rc-footer button, .rc-imageselect button, button[title]")
        if captcha_buttons:
            print(f"\n🎯 Found {len(captcha_buttons)} buttons in captcha area:")
            for i, btn in enumerate(captcha_buttons):
                try:
                    title = btn.get_attribute('title') or ''
                    class_name = btn.get_attribute('class') or ''
                    id_attr = btn.get_attribute('id') or ''
                    text = btn.text_content()[:30] or ''
                    print(f"  [{i+1}] title='{title}' class='{class_name}' id='{id_attr}' text='{text}'")
                except Exception as e:
                    print(f"  [{i+1}] Error reading button: {e}")
        
        print("\n✅ Inspection complete!")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        
    finally:
        print("🧹 Cleaning up...")
        try:
            if 'page' in locals():
                page.close()
            if 'context' in locals():
                context.close()
            if 'browser' in locals() and browser:
                browser.close()
            playwright.stop()
        except:
            pass

if __name__ == "__main__":
    main()