"""
Scraper for USDA Service Center Locator (offices.sc.egov.usda.gov)
Rewritten to use Playwright and Form Navigation.

Output:
- cache/service_centers_complete.json
"""

import asyncio
import json
import re
from pathlib import Path
from typing import Dict, Any, List
from datetime import datetime

from playwright.async_api import async_playwright, Page, BrowserContext

# Base paths
BASE_DIR = Path(__file__).parent.parent.parent
CACHE_DIR = BASE_DIR / "cache"

# Output file
SERVICE_CENTERS_PATH = CACHE_DIR / "service_centers_complete.json"

# State codes
STATE_CODES = {
    "AL": ("01", "alabama"), "AK": ("02", "alaska"), "AZ": ("04", "arizona"), 
    "AR": ("05", "arkansas"), "CA": ("06", "california"), "CO": ("08", "colorado"),
    "CT": ("09", "connecticut"), "DE": ("10", "delaware"), "FL": ("12", "florida"),
    "GA": ("13", "georgia"), "HI": ("15", "hawaii"), "ID": ("16", "idaho"),
    "IL": ("17", "illinois"), "IN": ("18", "indiana"), "IA": ("19", "iowa"),
    "KS": ("20", "kansas"), "KY": ("21", "kentucky"), "LA": ("22", "louisiana"),
    "ME": ("23", "maine"), "MD": ("24", "maryland"), "MA": ("25", "massachusetts"),
    "MI": ("26", "michigan"), "MN": ("27", "minnesota"), "MS": ("28", "mississippi"),
    "MO": ("29", "missouri"), "MT": ("30", "montana"), "NE": ("31", "nebraska"),
    "NV": ("32", "nevada"), "NH": ("33", "new-hampshire"), "NJ": ("34", "new-jersey"),
    "NM": ("35", "new-mexico"), "NY": ("36", "new-york"), "NC": ("37", "north-carolina"),
    "ND": ("38", "north-dakota"), "OH": ("39", "ohio"), "OK": ("40", "oklahoma"),
    "OR": ("41", "oregon"), "PA": ("42", "pennsylvania"), "RI": ("44", "rhode-island"),
    "SC": ("45", "south-carolina"), "SD": ("46", "south-dakota"), "TN": ("47", "tennessee"),
    "TX": ("48", "texas"), "UT": ("49", "utah"), "VT": ("50", "vermont"),
    "VA": ("51", "virginia"), "WA": ("53", "washington"), "WV": ("54", "west-virginia"),
    "WI": ("55", "wisconsin"), "WY": ("56", "wyoming")
}

class USDAServiceCenterScraper:
    """Playwright Scraper for USDA Service Center Locator"""
    
    BASE_URL = "https://offices.sc.egov.usda.gov/locator/app"
    STATE_LIST_URL = "https://offices.sc.egov.usda.gov/locator/app?service=action/1/StateMap/1/NavBar.StateLink"
    
    def __init__(self):
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None
    
    async def _navigate(self, url: str):
        """Navigate to URL and handle interstitial warning page if it appears"""
        try:
            await self.page.goto(url, wait_until="domcontentloaded")
            
            # Check for interstitial
            content = await self.page.content()
            if "Click here" in content and "Official United States Government System" in content:
                print("  Handling interstitial/warning page...")
                link = self.page.locator("a[href*='service=restart']").first
                if await link.count() > 0:
                    await link.click()
                    await self.page.wait_for_load_state("domcontentloaded")
                    
                    # After handling, we might need to go to original URL 
                    # But usually we just restart session. 
                    # The caller should handle navigation flow.
        except Exception as e:
            print(f"  Navigation error: {e}")

    async def start_session(self) -> bool:
        """Launch browser and start session"""
        try:
            self.playwright = await async_playwright().start()
            self.browser = await self.playwright.chromium.launch(headless=True)
            self.context = await self.browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
            self.page = await self.context.new_page()
            
            # Init session
            await self._navigate(f"{self.BASE_URL}?service=restart")
            return True
        except Exception as e:
            print(f"Error starting session: {e}")
            return False
    
    async def close(self):
        """Close browser"""
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()
            
    async def _select_state(self, state_code: str) -> bool:
        """Navigate to State List and select state"""
        try:
            # Go to State List
            await self._navigate(self.STATE_LIST_URL)
            
            # Determine state name for matching
            _, slug = STATE_CODES.get(state_code, (None, None))
            if not slug:
                return False
            
            state_name = slug.replace("-", " ").title()
            if state_code == "DC": state_name = "District of Columbia"
            
            # Find matching option
            state_options = await self.page.locator("select[name='state'] option").all()
            target_value = None
            
            for opt in state_options:
                text = await opt.text_content()
                if state_name in text:
                    target_value = await opt.get_attribute("value")
                    break
            
            if target_value:
                await self.page.select_option("select[name='state']", value=target_value)
                await self.page.click("input[value='Go to this State']")
                await self.page.wait_for_load_state("domcontentloaded")
                return True
            else:
                print(f"  State option not found for {state_code} ({state_name})")
                return False
                
        except Exception as e:
            print(f"  Error selecting state {state_code}: {e}")
            return False

    async def get_counties_for_state(self, state_code: str) -> List[Dict[str, str]]:
        """Get list of counties for a state"""
        if not await self._select_state(state_code):
            return []
        
        try:
            counties = []
            options = await self.page.locator("select[name='county'] option").all()
            
            for option in options:
                value = await option.get_attribute("value")
                name = (await option.text_content()).strip()
                # Assuming value '0' works as a code? Some values were 1, 2...
                if name and "Select" not in name:
                    counties.append({
                        "code": value,
                        "name": name
                    })
            return counties
        except Exception as e:
            print(f"Error getting counties for {state_code}: {e}")
            return []
    
    async def get_service_center_for_county(self, state_code: str, county_code: str, county_name: str) -> Dict[str, Any]:
        """Get service center details for a county"""
        
        # We must navigate from scratch to be safe
        if not await self._select_state(state_code):
            return {}
        
        try:
            # Select County
            # county_code here is the VALUE from the option
            await self.page.select_option("select[name='county']", value=county_code)
            await self.page.click("input[value='Go to this County']")
            await self.page.wait_for_load_state("domcontentloaded")
            
            result = {
                "state_code": state_code,
                "county_code": county_code,
                "county_name": county_name,
                "offices": [],
                "scraped_at": datetime.now().isoformat()
            }
            
            # Extract info
            text = await self.page.inner_text("body")
            
            # Addresses
            address_pattern = re.compile(
                r'(\d+\s+[A-Z][A-Za-z\s]+(?:ST|AVE|BLVD|RD|DR|LN|WAY)\.?\s*[A-Z][A-Za-z\s]+,\s*[A-Z]{2}\s*\d{5}(?:-\d{4})?)',
                re.I
            )
            # Phones
            phone_pattern = re.compile(r'\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}')
            
            addresses = address_pattern.findall(text)
            phones = phone_pattern.findall(text)
            
            if addresses:
                result["raw_addresses"] = addresses[:3]
            if phones:
                result["raw_phones"] = phones[:3]
                
            # Emails? Need to find agency links
            # Usually checking agency tabs or scrolling
            # Links might be: <a href="?service=page/AgencyHome...">
            # This scraper is basic, extracting just raw addresses/phones is a good start.
            
            return result
        except Exception as e:
            print(f"Error getting info for {state_code}/{county_name}: {e}")
            return {"error": str(e)}

async def scrape_service_centers(states: List[str] = None, max_counties_per_state: int = 1000) -> Dict[str, Any]:
    """Scrape service centers"""
    if states is None:
        states = list(STATE_CODES.keys())
        
    print(f"\n📍 Scraping service centers for {len(states)} states (PW+Form)...")
    
    results = {
        "metadata": {"scraped_at": datetime.now().isoformat()},
        "service_centers": {}
    }
    
    scraper = USDAServiceCenterScraper()
    if not await scraper.start_session():
        return results
        
    try:
        for state_idx, state_code in enumerate(states):
            print(f"\n[{state_idx + 1}/{len(states)}] Processing {state_code}...")
            counties = await scraper.get_counties_for_state(state_code)
            print(f"  Found {len(counties)} counties")
            
            for county_idx, county in enumerate(counties[:max_counties_per_state]):
                county_name = county["name"]
                print(f"  [{county_idx+1}/{len(counties)}] {county_name}...")
                
                info = await scraper.get_service_center_for_county(
                    state_code, county["code"], county_name
                )
                
                key = f"{state_code}_{county_name.lower().replace(' ', '_')}"
                results["service_centers"][key] = info
                
            # Save after each state
            with SERVICE_CENTERS_PATH.open("w", encoding="utf-8") as f:
                json.dump(results, f, indent=2)
            print(f"  ✓ Saved {len(results['service_centers'])} centers to file")
                
    finally:
        await scraper.close()
        
    return results

async def main():
    print("USDA Service Center Locator Scraper (Playwright Form)")
    CACHE_DIR.mkdir(exist_ok=True)
    
    # Run full scrape
    results = await scrape_service_centers(states=None, max_counties_per_state=1000)
    
    with SERVICE_CENTERS_PATH.open("w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
        
    print(f"\n✅ Saved {len(results['service_centers'])} to {SERVICE_CENTERS_PATH}")

if __name__ == "__main__":
    asyncio.run(main())
