# MN Public Notice Scraper

A professional Python scraper for extracting foreclosure and bankruptcy notices from the Minnesota Public Notice website for lead generation in financial assistance services.

## Quick Start

**Windows:** Double-click `run_scraper.bat`  
**Mac/Linux:** Double-click `run_scraper.sh`

The launcher will automatically:
- Install Python 3.11+ if needed
- Install all required packages
- Set up API keys (first time only)
- Run the scraper

When the Python script starts you'll be prompted to pick which source(s) to scrape:
1. **MN Public Notice** (`mnpublicnotice.com`)
2. **Star Tribune Foreclosures** (`classifieds.startribune.com`)
3. **Both** (runs sequentially)

## What It Does

- Searches for foreclosure and bankruptcy notices from **yesterday's date**
- Supports statewide results from both MN Public Notice and Star Tribune classifieds
- Automatically solves reCAPTCHA challenges using 2captcha service
- Extracts contact information using AI-powered text parsing
- Processes multiple pages of results (typically 200-300+ notices per day)
- Saves results to organized CSV files
- Uses VPN rotation to prevent IP blocking

## Output Data

Each record contains:
- **Contact Info**: First Name, Last Name, Street Address, City, State, ZIP
- **Legal Details**: Date Filed, Plaintiff/Creditor Name
- **Reference**: Link to original notice, Internal notice ID

## Requirements

### Software (Auto-installed by launcher)
- Python 3.7+ (auto-installed if missing)
- Playwright browser automation
- Required Python packages (auto-installed)

### Services (You need accounts)
- **Mullvad VPN** ($5/month) - Prevents IP blocking
- **2captcha** (~$2-5/month) - Solves captchas automatically  
- **OpenAI API** (~$3-10/month) - AI text parsing

### Total Monthly Cost: ~$10-20

## Supported Sources

- **MN Public Notice** – foreclosure & bankruptcy listings across Minnesota
- **Star Tribune Foreclosures** – statewide foreclosure notices from the Star Tribune marketplace

You can run either site independently or back-to-back from the CLI prompt.

## Setup Instructions

**Follow the guides in order:**

1. **SETUP_GUIDE.txt** - Complete setup walkthrough
2. **DAILY_USE.txt** - How to run daily
3. **AUTOMATION_GUIDE.txt** - Set up automatic daily runs
4. **TROUBLESHOOTING.txt** - Fix common problems

## Key Features

✅ **Fully Automated** - One-click operation after setup  
✅ **Enterprise Reliability** - Handles all website quirks and errors  
✅ **AI-Powered Parsing** - Superior data extraction accuracy  
✅ **Multi-page Processing** - Gets all available notices, not just first 50  
✅ **IP Blocking Prevention** - VPN rotation and smart rate limiting  
✅ **Professional Output** - Clean, organized CSV files  
✅ **Self-Updating** - Handles Python and package updates automatically  

## File Structure

```
MN_Notice_Scraper/
├── run_scraper.bat          # Windows launcher
├── run_scraper.sh           # Mac/Linux launcher  
├── SETUP_GUIDE.txt          # Complete setup instructions
├── DAILY_USE.txt            # Daily operation guide
├── AUTOMATION_GUIDE.txt     # Scheduling setup
├── TROUBLESHOOTING.txt      # Problem solving
├── mn_scraper.py            # Main scraper
├── gpt_parser.py            # AI text parsing
├── mullvad_manager.py       # VPN management
├── requirements.txt         # Python dependencies
└── csvs/                    # Output folder (auto-created)
```

## Performance

- **Runtime**: 1 hour+ for typical daily batch (200-300 notices)
- **Success Rate**: 95%+ captcha solving, 90%+ data extraction
- **Data Quality**: AI parsing eliminates formatting artifacts
- **Reliability**: Enterprise-grade error handling with automatic recovery

## Daily Workflow

1. **Automatic** (recommended): Set up daily scheduling - see AUTOMATION_GUIDE.txt
2. **Manual**: Double-click launcher file, press Enter when prompted

Results are saved as `mn_notices_YYYY-MM-DD.csv` with yesterday's date.

## Important Notes

⚠️ **VPN Required**: Running without VPN will result in 2+ day IP bans  
📅 **Daily Data**: Automatically searches for yesterday's notices  
💾 **File Preservation**: Each day creates a new CSV - old files are kept  
🔐 **API Keys**: Stored securely in .env file (created automatically)  

## Support

Check the documentation files for detailed help:
- Setup issues → SETUP_GUIDE.txt
- Daily operation → DAILY_USE.txt  
- Common problems → TROUBLESHOOTING.txt
- Automation → AUTOMATION_GUIDE.txt

This scraper is designed for legitimate business use in financial assistance services. Always respect website terms of use and rate limits.
