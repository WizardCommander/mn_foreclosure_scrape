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
    def __init__(self, enabled=True):
        self.enabled = enabled
        self.used_servers = []  # Track used servers to avoid repetition
        self.current_server = None
        
        if self.enabled:
            self.setup()
    
    def setup(self):
        """Initialize Mullvad connection"""
        try:
            logger.info("🌐 Setting up Mullvad VPN connection...")
            
            # Check if Mullvad is installed
            result = subprocess.run(['mullvad', '--help'], 
                                  capture_output=True, text=True, timeout=10)
            if result.returncode != 0:
                logger.error("❌ Mullvad CLI not found. Please install Mullvad VPN.")
                self.enabled = False
                return False
            
            # Connect to a random server
            if self.rotate_server():
                return True
            else:
                logger.error("❌ Failed to establish VPN connection")
                self.enabled = False
                return False
                
        except subprocess.TimeoutExpired:
            logger.error("❌ Mullvad CLI timeout - please check installation")
            self.enabled = False
            return False
        except Exception as e:
            logger.error(f"❌ VPN setup failed: {e}")
            self.enabled = False
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
    
    def rotate_server(self):
        """Connect to a new VPN server"""
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
            
            # Disconnect first
            disconnect_result = subprocess.run(['mullvad', 'disconnect'], 
                                             capture_output=True, text=True, timeout=10)
            time.sleep(2)
            
            # Set relay to specific server
            set_result = subprocess.run(['mullvad', 'relay', 'set', 'hostname', selected_server],
                                      capture_output=True, text=True, timeout=10)
            
            if set_result.returncode != 0:
                logger.error(f"❌ Failed to set relay to {selected_server}: {set_result.stderr}")
                return False
            
            # Connect
            connect_result = subprocess.run(['mullvad', 'connect'], 
                                          capture_output=True, text=True, timeout=15)
            
            if connect_result.returncode != 0:
                logger.error(f"❌ Failed to connect to VPN: {connect_result.stderr}")
                return False
            
            # Wait for connection to establish
            time.sleep(5)
            
            # Verify connection
            if self.verify_connection():
                self.current_server = selected_server
                logger.info(f"✅ Successfully connected to {selected_server}")
                return True
            else:
                logger.error(f"❌ VPN connection verification failed for {selected_server}")
                return False
                
        except subprocess.TimeoutExpired:
            logger.error("❌ VPN connection timeout")
            return False
        except Exception as e:
            logger.error(f"❌ VPN rotation failed: {e}")
            return False
    
    def verify_connection(self):
        """Verify VPN is connected and working"""
        if not self.enabled:
            return True
            
        try:
            # Check Mullvad status
            result = subprocess.run(['mullvad', 'status'], 
                                  capture_output=True, text=True, timeout=10)
            
            if result.returncode == 0 and 'Connected' in result.stdout:
                status_info = result.stdout.strip()
                logger.info(f"🔗 VPN Status: {status_info}")
                return True
            else:
                logger.error(f"❌ VPN not connected: {result.stdout}")
                return False
                
        except Exception as e:
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