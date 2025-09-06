@echo off
setlocal enabledelayedexpansion

echo ===============================================
echo    MN PUBLIC NOTICE SCRAPER - STARTUP
echo ===============================================
echo.

REM Change to the directory where this batch file is located
cd /d "%~dp0"

REM Check if Python is installed and version is adequate
echo [1/6] Checking Python installation...
python --version >nul 2>&1
if errorlevel 1 (
    echo Python not found. Installing Python automatically...
    goto :install_python
) else (
    REM Extract Python version and check if it's 3.7 or higher
    for /f "tokens=2 delims= " %%i in ('python --version 2^>^&1') do (
        set python_version=%%i
        echo Python %%i found
    )
    
    REM Parse major and minor version numbers
    for /f "tokens=1,2 delims=." %%a in ("!python_version!") do (
        set major=%%a
        set minor=%%b
    )
    
    REM Check if version is less than 3.7
    if !major! lss 3 (
        echo Python version !python_version! is too old. Need Python 3.7+
        goto :install_python
    )
    if !major! equ 3 if !minor! lss 7 (
        echo Python version !python_version! is too old. Need Python 3.7+
        goto :install_python
    )
    
    echo Python version !python_version! is compatible
)
echo.

REM Check if pip is available
echo [2/6] Checking pip...
pip --version >nul 2>&1
if errorlevel 1 (
    echo pip not found. Please reinstall Python with pip included.
    pause
    exit /b 1
)
echo pip is available
echo.

REM Install/update Python packages
echo [3/6] Installing/updating Python packages...
pip install -r requirements.txt
if errorlevel 1 (
    echo Failed to install Python packages. Check your internet connection.
    pause
    exit /b 1
)
echo.

REM Install Playwright browsers
echo [4/6] Installing Playwright browsers...
python -c "import playwright" >nul 2>&1
if not errorlevel 1 (
    playwright install chromium --with-deps
    if errorlevel 1 (
        echo Warning: Playwright browser installation failed. Continuing anyway...
    ) else (
        echo Playwright browsers installed successfully
    )
) else (
    echo Playwright not found in packages. This should not happen.
)
echo.

REM Check for .env file and API keys
echo [5/6] Checking API configuration...
if not exist ".env" (
    echo .env file not found. Setting up API keys...
    echo.
    echo You need two API keys to run this scraper:
    echo 1. 2captcha API key (for solving captchas)
    echo 2. OpenAI API key (for text processing)
    echo.
    echo See SETUP_GUIDE.txt for instructions on getting these keys.
    echo.
    
    set /p captcha_key=Enter your 2captcha API key: 
    set /p openai_key=Enter your OpenAI API key: 
    
    echo TWO_CAPTCHA_API_KEY=!captcha_key!> .env
    echo OPENAI_API_KEY=!openai_key!>> .env
    
    echo API keys saved to .env file
) else (
    echo .env file found
)
echo.

REM Test API keys
echo Testing API connections...
python -c "
import os
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
"
echo.

REM Check Mullvad VPN
echo [6/6] Checking Mullvad VPN...
mullvad --help >nul 2>&1
if errorlevel 1 (
    echo Warning: Mullvad CLI not found
    echo The scraper will work without VPN but may be slower
    echo See SETUP_GUIDE.txt for Mullvad installation instructions
) else (
    echo Mullvad CLI found
    mullvad status 2>nul | find "Connected" >nul
    if not errorlevel 1 (
        echo VPN Status: Connected
    ) else (
        echo VPN Status: Disconnected (will auto-connect when scraping starts)
    )
)
echo.

echo ===============================================
echo    READY TO SCRAPE
echo ===============================================
echo.
echo The scraper will search for notices from yesterday's date.
echo Results will be saved to the 'csvs' folder.
echo This typically takes 15-25 minutes to complete.
echo.
pause

REM Run the scraper
echo Starting scraper...
echo.
python mn_scraper.py

echo.
echo ===============================================
echo    SCRAPING COMPLETE
echo ===============================================
echo.
echo Results have been saved to the csvs folder.
echo Check the CSV file with yesterday's date for your data.
echo.
pause
goto :eof

:install_python
echo.
echo Installing Python 3.11 automatically...
echo This will download and install Python with all required settings.
echo.

REM Download Python installer
echo Downloading Python installer...
powershell -Command "& {Invoke-WebRequest -Uri 'https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe' -OutFile 'python_installer.exe'}"

if not exist "python_installer.exe" (
    echo Failed to download Python installer.
    echo Please manually install Python from https://www.python.org/downloads/
    echo Make sure to check "Add Python to PATH" during installation.
    pause
    exit /b 1
)

echo Installing Python... This may take a few minutes.
echo Please wait and do not close this window.

REM Install Python silently with all required options
python_installer.exe /quiet InstallAllUsers=0 PrependPath=1 Include_test=0 Include_pip=1 Include_tcltk=0 Include_launcher=1

if errorlevel 1 (
    echo Python installation failed. Please install manually.
    echo Go to https://www.python.org/downloads/ and install Python 3.7+
    echo Make sure to check "Add Python to PATH" during installation.
    del python_installer.exe
    pause
    exit /b 1
)

echo Python installation completed successfully!
del python_installer.exe

REM Refresh environment variables
echo Refreshing environment variables...
for /f "tokens=2*" %%i in ('reg query "HKCU\Environment" /v PATH 2^>nul') do set "user_path=%%j"
for /f "tokens=2*" %%i in ('reg query "HKLM\SYSTEM\CurrentControlSet\Control\Session Manager\Environment" /v PATH 2^>nul') do set "system_path=%%j"
set "PATH=%system_path%;%user_path%"

echo Testing Python installation...
python --version >nul 2>&1
if errorlevel 1 (
    echo Python installation completed but python command not found.
    echo Please restart this script to try again.
    pause
    exit /b 1
) else (
    for /f "tokens=2" %%i in ('python --version 2^>^&1') do echo Python %%i is now installed and ready!
    echo.
    echo Continuing with scraper setup...
    echo.
    goto :continue_setup
)

:continue_setup