# MN Public Notice Scraper - Development Summary

## Project Overview
Built a web scraper for MN Public Notice website to extract foreclosure and bankruptcy notices for lead generation in financial assistance services.

**Target Site**: https://www.mnpublicnotice.com/Search.aspx
**Goal**: Extract contact information from daily foreclosure/bankruptcy filings

## Required Data Fields
- A: First Name
- B: Last Name  
- C: Street Address
- D: City
- E: State (MN)
- F: Zip Code
- G: Date Filed
- H: Plaintiff/Creditor
- Link to original notice

## Technology Stack
- **Python + Selenium WebDriver** (Chrome)
- **BeautifulSoup** for HTML parsing
- **CSV output** to organized folder structure
- **Regex patterns** for data extraction

## Key Implementation Details

### 1. Search Form Automation
**Correct sequence is critical:**
1. Enter keywords: "foreclosure bankruptcy"
2. Click "Any Words" radio button: `#ctl00_ContentPlaceHolder1_as1_rdoType_1`
3. Open date range selector: `#ctl00_ContentPlaceHolder1_as1_divDateRange`
4. Click range radio button: `#ctl00_ContentPlaceHolder1_as1_rbRange`
5. Set from/to dates (same day for daily runs)
6. Click Go button: `#ctl00_ContentPlaceHolder1_as1_btnGo`

### 2. Critical Timing Issues
- **Wait 3 seconds** after clicking "Any Words" radio (triggers page reload)
- **Wait 3 seconds** after opening date range selector (loading spinner)
- **Use JavaScript clicks** for radio buttons (more reliable than regular clicks)

### 3. Notice Processing Flow
1. Find all view buttons: `class="viewButton"`
2. For each notice:
   - Click view button to get detail page
   - Check for captcha (skip if present)
   - Extract data using regex patterns
   - Navigate back to results
   - Re-find view buttons (avoid stale element errors)

### 4. Captcha Detection
Detects reCAPTCHA by checking for:
- Text: "You must complete the reCAPTCHA in order to continue"
- Elements with `id*='recaptcha'`
- Scripts containing `grecaptcha.render`

### 5. Data Extraction Patterns
Uses flexible regex patterns for:
- **Names**: `MORTGAGOR|DEBTOR|DEFENDANT` patterns
- **Addresses**: Minnesota-specific address formats
- **Dates**: Multiple date formats (MM/DD/YYYY, Month DD, YYYY)
- **Plaintiffs**: Financial institution name patterns

### 6. File Management
- Saves to `csvs/` folder
- Removes old CSV files (keeps only latest)
- Timestamps filenames: `mn_notices_YYYYMMDD_HHMMSS.csv`

## Current Status ✅

### Working Features
- ✅ **Search form automation** with correct sequence
- ✅ **Date range filtering** (same-day search for daily runs)
- ✅ **View button processing** with stale element handling
- ✅ **Captcha detection and skipping**
- ✅ **Data extraction** with flexible regex patterns
- ✅ **CSV output** with proper file management
- ✅ **Error handling** and logging

### Test Results
- Successfully finds 15 search results for "foreclosure bankruptcy"
- Properly handles ASP.NET postbacks and loading delays
- Correctly skips captcha-protected notices
- Saves extracted data to organized CSV structure

## Remaining Tasks 🚧

### 1. Pagination Support
- **Need to implement**: Navigation through multiple pages of results
- **Look for**: Next/Previous buttons, page numbers
- **Challenge**: Maintain session state across page navigation

### 2. Captcha Solving
- **Current**: Detects and skips captcha pages (~70% of notices)
- **Options**: 
  - Browser extensions (NopeCHA, Buster - free)
  - Manual intervention workflow
  - Paid services (2captcha, Anti-Captcha)
- **Recommendation**: Start with free browser extensions

## File Structure
```
marc/
├── mn_scraper_selenium.py      # Main working scraper
├── mn_scraper.py              # Original requests-based version (deprecated)
├── csvs/                      # Output folder (auto-managed)
├── overview.txt               # Original project requirements
├── todo.md                    # Task tracking
└── DEVELOPMENT_SUMMARY.md     # This file
```

## Key Learnings

### Why Selenium Over Requests
- **ASP.NET complexity**: ViewState, postbacks, JavaScript dependencies
- **Dynamic loading**: Elements load/reload after interactions
- **Form interactions**: Radio buttons, dropdowns require real browser events

### Critical Success Factors
1. **Correct interaction sequence** (Any Words before Go button)
2. **Proper waits** after each page interaction
3. **JavaScript clicks** for radio buttons
4. **Stale element handling** during navigation
5. **Captcha detection** to avoid failures

## Future Enhancement Ideas
- **Scheduling**: Daily automated runs
- **Notification**: Email/Slack alerts when new notices found
- **Data validation**: AI-powered field verification
- **Database storage**: Replace CSV with structured database
- **Multi-county support**: Expand beyond MN statewide

## Production Deployment Notes
- Requires Chrome browser and ChromeDriver
- Recommended: Run in non-headless mode initially for debugging
- Consider VPN/proxy rotation for large-scale scraping
- Implement rate limiting to be respectful to target site
- Monitor for site structure changes (selectors may break)

---

*Last updated: August 20, 2025*
*Status: Core functionality complete, ready for pagination and captcha solving*