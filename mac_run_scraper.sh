#!/bin/bash

echo "==============================================="
echo "    MN PUBLIC NOTICE SCRAPER - STARTUP"
echo "==============================================="
echo

# Change to the directory where this script is located
cd "$(dirname "$0")"

# Function to check if command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Function to check Python version
check_python_version() {
    local python_cmd=$1
    local version_output=$($python_cmd --version 2>&1)
    local version=$(echo $version_output | grep -oE '[0-9]+\.[0-9]+\.[0-9]+')
    local major=$(echo $version | cut -d. -f1)
    local minor=$(echo $version | cut -d. -f2)
    
    if [ "$major" -gt 3 ] || ([ "$major" -eq 3 ] && [ "$minor" -ge 7 ]); then
        echo "$python_cmd found: $version_output (compatible)"
        PYTHON_CMD=$python_cmd
        return 0
    else
        echo "$python_cmd found: $version_output (too old, need 3.7+)"
        return 1
    fi
}

# Function to install Python
install_python() {
    echo
    echo "Installing Python 3.11 automatically..."
    echo
    
    # Detect OS
    if [[ "$OSTYPE" == "darwin"* ]]; then
        # macOS
        if command_exists brew; then
            echo "Installing Python via Homebrew..."
            brew install python@3.11
            if [ $? -eq 0 ]; then
                echo "Python installed successfully!"
                # Update PATH for this session
                export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"
                if command_exists python3.11; then
                    PYTHON_CMD="python3.11"
                elif command_exists python3; then
                    PYTHON_CMD="python3"
                fi
                echo "Continuing with scraper setup..."
                return 0
            fi
        else
            echo "Homebrew not found. Installing Homebrew first..."
            /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
            if [ $? -eq 0 ]; then
                export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"
                brew install python@3.11
                if [ $? -eq 0 ]; then
                    echo "Python installed successfully!"
                    PYTHON_CMD="python3"
                    return 0
                fi
            fi
        fi
    else
        # Linux
        if command_exists apt; then
            echo "Installing Python via apt..."
            sudo apt update
            sudo apt install -y python3.11 python3.11-pip
        elif command_exists yum; then
            echo "Installing Python via yum..."
            sudo yum install -y python3.11 python3.11-pip
        elif command_exists dnf; then
            echo "Installing Python via dnf..."
            sudo dnf install -y python3.11 python3.11-pip
        fi
        
        if command_exists python3.11; then
            PYTHON_CMD="python3.11"
            echo "Python installed successfully!"
            return 0
        fi
    fi
    
    # If automatic installation failed
    echo "Automatic Python installation failed."
    echo "Please manually install Python 3.7+ from:"
    echo "  macOS: https://www.python.org/downloads/ or 'brew install python3'"
    echo "  Linux: Use your package manager (apt, yum, dnf, etc.)"
    read -p "Press Enter to exit..."
    exit 1
}

# Check if Python is installed and version is adequate
echo "[1/6] Checking Python installation..."

# Check available Python versions
PYTHON_CMD=""
if command_exists python3; then
    if check_python_version python3; then
        : # Version is good
    else
        echo "Python3 version is too old, installing newer version..."
        install_python
    fi
elif command_exists python; then
    if check_python_version python; then
        : # Version is good  
    else
        echo "Python version is too old, installing newer version..."
        install_python
    fi
else
    echo "Python not found. Installing Python automatically..."
    install_python
fi
echo

# Check if pip is available
echo "[2/6] Checking pip..."
if command_exists pip3; then
    PIP_CMD="pip3"
elif command_exists pip; then
    PIP_CMD="pip"
else
    echo "pip not found. Please reinstall Python with pip included."
    read -p "Press Enter to exit..."
    exit 1
fi
echo "pip is available"
echo

# Install/update Python packages
echo "[3/6] Installing/updating Python packages..."
$PIP_CMD install -r requirements.txt
if [ $? -ne 0 ]; then
    echo "Failed to install Python packages. Check your internet connection."
    read -p "Press Enter to exit..."
    exit 1
fi
echo

# Install Playwright browsers
echo "[4/6] Installing Playwright browsers..."
if $PYTHON_CMD -c "import playwright" 2>/dev/null; then
    $PYTHON_CMD -m playwright install chromium --with-deps
    if [ $? -ne 0 ]; then
        echo "Warning: Playwright browser installation failed. Continuing anyway..."
    else
        echo "Playwright browsers installed successfully"
    fi
else
    echo "Playwright not found in packages. This should not happen."
fi
echo

# Check for .env file and API keys
echo "[5/6] Checking API configuration..."
if [ ! -f ".env" ]; then
    echo ".env file not found. Setting up API keys..."
    echo
    echo "You need two API keys to run this scraper:"
    echo "1. 2captcha API key (for solving captchas)"
    echo "2. OpenAI API key (for text processing)"
    echo
    echo "See SETUP_GUIDE.txt for instructions on getting these keys."
    echo
    
    read -p "Enter your 2captcha API key: " captcha_key
    read -p "Enter your OpenAI API key: " openai_key
    
    echo "TWO_CAPTCHA_API_KEY=$captcha_key" > .env
    echo "OPENAI_API_KEY=$openai_key" >> .env
    
    echo "API keys saved to .env file"
else
    echo ".env file found"
fi
echo

# Test API keys
echo "Testing API connections..."
$PYTHON_CMD -c "
import os
try:
    from dotenv import load_dotenv
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
except ImportError:
    print('python-dotenv not installed, but continuing...')
"
echo

# Check Mullvad VPN
echo "[6/6] Checking Mullvad VPN..."
if command_exists mullvad; then
    echo "Mullvad CLI found"
    if mullvad status 2>/dev/null | grep -q "Connected"; then
        echo "VPN Status: Connected"
    else
        echo "VPN Status: Disconnected (will auto-connect when scraping starts)"
    fi
else
    echo "Warning: Mullvad CLI not found"
    echo "The scraper will work without VPN but may be slower"
    echo "See SETUP_GUIDE.txt for Mullvad installation instructions"
fi
echo

echo "==============================================="
echo "    READY TO SCRAPE"
echo "==============================================="
echo
echo "The scraper will search for notices from yesterday's date."
echo "Results will be saved to the 'csvs' folder."
echo "This typically takes 15-25 minutes to complete."
echo
read -p "Press Enter to start scraping..."

# Run the scraper
echo "Starting scraper..."
echo
$PYTHON_CMD mn_scraper.py

echo
echo "==============================================="
echo "    SCRAPING COMPLETE"
echo "==============================================="
echo
echo "Results have been saved to the csvs folder."
echo "Check the CSV file with yesterday's date for your data."
echo
read -p "Press Enter to exit..."