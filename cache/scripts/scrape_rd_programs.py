"""
Scrape USDA Rural Development Programs

Scrapes all programs from rd.usda.gov/programs-services/all-programs
with pagination, visiting each detail page for comprehensive info.

Output: cache/rd_programs_comprehensive.json
"""

import asyncio
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List

from playwright.async_api import async_playwright, Page, BrowserContext

# Paths
BASE_DIR = Path(__file__).parent.parent.parent
CACHE_DIR = BASE_DIR / "cache"
OUTPUT_PATH = CACHE_DIR / "rd_programs_comprehensive.json"

# ... (omitted)

async def main():
    async with async_playwright() as p:
        # Launch with visible browser for debugging
        browser = await p.chromium.launch(
            headless=True,  # Run in background
            args=['--disable-http2']
        )
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        
        data = await scrape_rd_programs(context)
        
        # Save
        with OUTPUT_PATH.open("w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        
        print(f"\n✅ Saved {data['total_count']} Rural Development programs to {OUTPUT_PATH}")
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
