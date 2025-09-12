#!/usr/bin/env python3
"""
Mullvad VPN Manager
Handles automatic VPN server rotation for web scraping to avoid IP blocks
"""

import subprocess
import time
import logging
import random

logger = logging.getLogger(__name__)

class MullvadManager:
    def __init__(self, enabled=True, auto_connect=True):
        self.enabled = enabled
        self.auto_connect = auto_connect
        self.used_servers = []  # Track used servers to avoid repetition
        self.current_server = None
        self.connection_established = False
        
        if self.enabled and self.auto_connect:
            self.setup()
    
    def setup(self, retries=3):
        """Initialize Mullvad connection with retry logic"""
        if not self.enabled:
            return True
            
        for attempt in range(retries):
            try:
                logger.info(f"🌐 Setting up Mullvad VPN connection... (attempt {attempt + 1}/{retries})")
                
                # Check if Mullvad is installed
                result = subprocess.run(['mullvad', '--help'], 
                                      capture_output=True, text=True, timeout=10)
                if result.returncode != 0:
                    logger.error("❌ Mullvad CLI not found. Please install Mullvad VPN.")
                    self.enabled = False
                    return False
                
                # Connect to a random server
                if self.rotate_server():
                    self.connection_established = True
                    logger.info("✅ VPN connection established successfully")
                    return True
                else:
                    if attempt < retries - 1:
                        logger.warning(f"⚠️ VPN connection failed, retrying in 10 seconds... (attempt {attempt + 1}/{retries})")
                        time.sleep(10)
                    else:
                        logger.error("❌ Failed to establish VPN connection after all retries")
                        self.enabled = False
                        return False
                    
            except subprocess.TimeoutExpired:
                if attempt < retries - 1:
                    logger.warning(f"⚠️ Mullvad CLI timeout, retrying in 10 seconds... (attempt {attempt + 1}/{retries})")
                    time.sleep(10)
                else:
                    logger.error("❌ Mullvad CLI timeout after all retries - please check installation")
                    self.enabled = False
                    return False
            except Exception as e:
                if attempt < retries - 1:
                    logger.warning(f"⚠️ VPN setup failed: {e}, retrying in 10 seconds... (attempt {attempt + 1}/{retries})")
                    time.sleep(10)
                else:
                    logger.error(f"❌ VPN setup failed after all retries: {e}")
                    self.enabled = False
                    return False
        
        return False
    
    def get_available_servers(self):
        """Get list of reliable US servers for web scraping"""
        # Actual available US WireGuard servers from mullvad.net
        us_servers = [
            'us-qas-wg-001',  # Ashburn/DC area
            'us-qas-wg-002',
            'us-qas-wg-003', 
            'us-qas-wg-004',
            'us-qas-wg-101',
            'us-qas-wg-102',
            'us-qas-wg-103',
            'us-qas-wg-201',
            'us-qas-wg-202',
            'us-qas-wg-203',
            'us-qas-wg-204',
            'us-atl-wg-001',  # Atlanta
            'us-atl-wg-002',
            'us-atl-wg-301',
        ]
        
        # Filter out already used servers for this session
        available = [server for server in us_servers if server not in self.used_servers]
        
        # Reset if all servers have been used
        if not available:
            logger.info("🔄 Resetting used servers list - all servers have been tried")
            self.used_servers.clear()
            available = us_servers
            
        return available
    
    def rotate_server(self, max_wait_time=30):
        """Connect to a new VPN server with enhanced stability"""
        if not self.enabled:
            return True
            
        try:
            available_servers = self.get_available_servers()
            if not available_servers:
                logger.error("❌ No available VPN servers")
                return False
            
            # Pick random server
            selected_server = random.choice(available_servers)
            self.used_servers.append(selected_server)
            
            logger.info(f"🔄 Connecting to Mullvad server: {selected_server}")
            
            # Disconnect first with longer timeout
            logger.info("📤 Disconnecting from current VPN connection...")
            disconnect_result = subprocess.run(['mullvad', 'disconnect'], 
                                             capture_output=True, text=True, timeout=15)
            time.sleep(3)  # Longer wait to ensure clean disconnect
            
            # Set relay to specific server
            logger.info(f"🎯 Setting relay to {selected_server}...")
            set_result = subprocess.run(['mullvad', 'relay', 'set', 'hostname', selected_server],
                                      capture_output=True, text=True, timeout=15)
            
            if set_result.returncode != 0:
                logger.error(f"❌ Failed to set relay to {selected_server}: {set_result.stderr}")
                return False
            
            # Connect with longer timeout
            logger.info(f"🔗 Connecting to {selected_server}...")
            connect_result = subprocess.run(['mullvad', 'connect'], 
                                          capture_output=True, text=True, timeout=20)
            
            if connect_result.returncode != 0:
                logger.error(f"❌ Failed to connect to VPN: {connect_result.stderr}")
                return False
            
            # Wait for connection to establish with progress feedback
            logger.info(f"⏳ Waiting for VPN connection to stabilize (up to {max_wait_time} seconds)...")
            for i in range(max_wait_time):
                time.sleep(1)
                if self.verify_connection(silent=True):
                    self.current_server = selected_server
                    self.connection_established = True
                    logger.info(f"✅ Successfully connected to {selected_server} (took {i+1} seconds)")
                    return True
                if (i + 1) % 5 == 0:  # Progress update every 5 seconds
                    logger.info(f"🔄 Still connecting... ({i+1}/{max_wait_time} seconds)")
            
            logger.error(f"❌ VPN connection verification failed for {selected_server} after {max_wait_time} seconds")
            return False
                
        except subprocess.TimeoutExpired:
            logger.error("❌ VPN connection timeout")
            return False
        except Exception as e:
            logger.error(f"❌ VPN rotation failed: {e}")
            return False
    
    def verify_connection(self, silent=False):
        """Verify VPN is connected and working"""
        if not self.enabled:
            return True
            
        try:
            # Check Mullvad status
            result = subprocess.run(['mullvad', 'status'], 
                                  capture_output=True, text=True, timeout=10)
            
            if result.returncode == 0 and 'Connected' in result.stdout:
                status_info = result.stdout.strip()
                if not silent:
                    logger.info(f"🔗 VPN Status: {status_info}")
                return True
            else:
                if not silent:
                    logger.error(f"❌ VPN not connected: {result.stdout}")
                return False
                
        except Exception as e:
            if not silent:
                logger.error(f"❌ VPN verification failed: {e}")
            return False
    
    def disconnect(self):
        """Disconnect VPN when done"""
        if self.enabled:
            try:
                logger.info("🔌 Disconnecting VPN...")
                result = subprocess.run(['mullvad', 'disconnect'], 
                                      capture_output=True, text=True, timeout=10)
                if result.returncode == 0:
                    logger.info("✅ VPN disconnected")
                else:
                    logger.warning(f"⚠️ VPN disconnect warning: {result.stderr}")
            except Exception as e:
                logger.error(f"❌ VPN disconnect failed: {e}")
    
    def ensure_connected(self, retries=2):
        """Ensure VPN is connected before scraping starts"""
        if not self.enabled:
            return True
            
        logger.info("🔍 Ensuring VPN connection is active before starting scraper...")
        
        # If we haven't established a connection yet, try to connect
        if not self.connection_established:
            logger.info("🌐 No active VPN connection found, establishing new connection...")
            return self.setup(retries=retries)
        
        # Verify existing connection
        if self.verify_connection():
            logger.info("✅ Existing VPN connection verified and active")
            return True
        else:
            logger.warning("⚠️ Existing VPN connection lost, attempting to reconnect...")
            self.connection_established = False
            return self.setup(retries=retries)
    
    def get_status(self):
        """Get current VPN status"""
        if not self.enabled:
            return "VPN disabled"
            
        try:
            result = subprocess.run(['mullvad', 'status'], 
                                  capture_output=True, text=True, timeout=10)
            return result.stdout.strip() if result.returncode == 0 else "Status unknown"
        except Exception as e:
            return f"Status check failed: {e}"

def main():
    """Test the Mullvad manager"""
    logging.basicConfig(level=logging.INFO, format='%(message)s')
    
    vpn = MullvadManager(enabled=True)
    
    if vpn.enabled:
        print(f"Current status: {vpn.get_status()}")
        print("Testing server rotation...")
        vpn.rotate_server()
        print(f"New status: {vpn.get_status()}")

if __name__ == "__main__":
    main()