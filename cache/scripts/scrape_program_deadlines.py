"""
Scrape Farmers.gov Program Deadlines

Scrapes the "Program Deadlines" page and visits each program's detail page
to gather comprehensive info about USDA grants and programs.

Output: cache/program_deadlines_comprehensive.json
"""

import asyncio
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional

from playwright.async_api import async_playwright, Page, BrowserContext

# Paths
BASE_DIR = Path(__file__).parent.parent.parent
CACHE_DIR = BASE_DIR / "cache"
OUTPUT_PATH = CACHE_DIR / "program_deadlines_comprehensive.json"

# URLs
DEADLINES_URL = "https://www.farmers.gov/working-with-us/program-deadlines"


async def extract_page_content(page: Page, url: str) -> Dict[str, Any]:
    """Extract content from a detail page"""
    try:
        await page.goto(url, wait_until="networkidle", timeout=30000)
        await asyncio.sleep(1)
        
        content = {}
        
        # Title
        title_elem = await page.query_selector("h1")
        if title_elem:
            content["detail_title"] = (await title_elem.inner_text()).strip()
        
        # Main content area
        # Try multiple selectors common on USDA sites
        selectors = [
            ".node__content", 
            "article", 
            ".usa-prose", 
            ".layout-content",
            "#main-content"
        ]
        
        full_text = ""
        for sel in selectors:
            elem = await page.query_selector(sel)
            if elem:
                full_text = await elem.inner_text()
                break
        
        if full_text:
            # Clean text
            lines = [l.strip() for l in full_text.split("\n") if l.strip()]
            # Filter nav/footer noise
            lines = [l for l in lines if len(l) > 20 or l.endswith(".") or l.endswith(":")]
            content["full_description"] = "\n".join(lines)
        
        return content
        
    except Exception as e:
        print(f"  ⚠️ Error scraping detail {url}: {e}")
        return {"error": str(e)}


async def scrape_deadlines(context: BrowserContext) -> Dict[str, Any]:
    """main scraping logic"""
    page = await context.new_page()
    
    print(f"📖 Navigating to {DEADLINES_URL}...")
    await page.goto(DEADLINES_URL, wait_until="networkidle")
    await asyncio.sleep(2)
    
    programs = []
    
    # Each program is in a row
    rows = await page.query_selector_all(".views-row")
    print(f"Found {len(rows)} program items.")
    
    for row in rows:
        item = {}
        
        # Title
        title_elem = await row.query_selector(".views-field-title h3, .views-field-title")
        if title_elem:
            item["program_name"] = (await title_elem.inner_text()).strip()
        
        # Deadline
        date_elem = await row.query_selector(".date-display-single, time, .views-field-field-deadline .field-content")
        if date_elem:
            item["deadline"] = (await date_elem.inner_text()).strip()
        
        # Agency (sometimes labelled)
        agency_elem = await row.query_selector(".views-field-field-agency .field-content")
        if agency_elem:
            item["agency"] = (await agency_elem.inner_text()).strip()
        
        # Summary
        desc_elem = await row.query_selector(".views-field-field-program-description .field-content p")
        if desc_elem:
            item["summary"] = (await desc_elem.inner_text()).strip()
            
        # Link
        link_elem = await row.query_selector("a")
        if link_elem:
            href = await link_elem.get_attribute("href")
            if href:
                if href.startswith("/"):
                    href = "https://www.farmers.gov" + href
                item["url"] = href
        
        if item.get("program_name"):
            programs.append(item)
            
    print(f"✅ Extracted {len(programs)} basic items. Now scraping details...")
    
    # Visit detail pages
    for i, prog in enumerate(programs):
        if prog.get("url"):
            print(f"  [{i+1}/{len(programs)}] {prog['program_name'][:40]}...")
            details = await extract_page_content(page, prog["url"])
            prog.update(details)
            
            # Be nice to the server
            await asyncio.sleep(1)
            
    return {"programs": programs, "scraped_at": datetime.now().isoformat()}


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        )
        
        data = await scrape_deadlines(context)
        
        # Save
        with OUTPUT_PATH.open("w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
            
        print(f"\n✅ Saved {len(data['programs'])} detailed programs to {OUTPUT_PATH}")
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
