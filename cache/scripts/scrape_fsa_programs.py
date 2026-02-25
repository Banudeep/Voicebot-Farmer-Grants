"""
Scrape FSA Programs Directory

Scrapes all programs from FSA Resources page with pagination,
visiting each detail page for comprehensive info.

Output: cache/fsa_programs_comprehensive.json
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
OUTPUT_PATH = CACHE_DIR / "fsa_programs_comprehensive.json"

# URLs
BASE_URL = "https://www.fsa.usda.gov/resources/programs"


async def extract_program_detail(page: Page, url: str) -> Dict[str, Any]:
    """Extract full content from a program detail page"""
    try:
        await page.goto(url, wait_until="networkidle", timeout=30000)
        await asyncio.sleep(1)
        
        content = {}
        
        # Title
        title_elem = await page.query_selector("h1")
        if title_elem:
            content["detail_title"] = (await title_elem.inner_text()).strip()
        
        # Main content - try multiple selectors
        selectors = [
            ".grid-col-fill",  # FSA common layout
            ".usa-prose",
            "article",
            ".node__content",
            "#main-content"
        ]
        
        full_text = ""
        for sel in selectors:
            elem = await page.query_selector(sel)
            if elem:
                full_text = await elem.inner_text()
                if len(full_text) > 200:  # Valid content
                    break
        
        if full_text:
            # Clean text
            lines = [l.strip() for l in full_text.split("\n") if l.strip()]
            # Filter out very short lines and navigation noise
            lines = [l for l in lines if len(l) > 15 or l.endswith(".") or l.endswith(":")]
            content["full_description"] = "\n".join(lines)
        
        # Try to find "Important Dates" section
        dates_section = await page.query_selector("h2:has-text('Important Dates'), h3:has-text('Important Dates')")
        if dates_section:
            # Get next siblings until next header
            parent = await dates_section.evaluate_handle("el => el.parentElement")
            dates_text = await parent.evaluate('''el => {
                let text = "";
                let node = el.querySelector("h2, h3").nextElementSibling;
                while (node && !["H1", "H2", "H3"].includes(node.tagName)) {
                    text += node.innerText + "\\n";
                    node = node.nextElementSibling;
                }
                return text;
            }''')
            if dates_text:
                content["important_dates"] = dates_text.strip()
        
        return content
        
    except Exception as e:
        print(f"  ⚠️ Error scraping {url}: {e}")
        return {"error": str(e)}


async def scrape_fsa_programs(context: BrowserContext) -> Dict[str, Any]:
    """Main scraping logic"""
    page = await context.new_page()
    
    all_programs = []
    
    # Pagination loop (estimated 3 pages for 46 programs at 18/page)
    for page_num in range(5):  # Safety margin
        url = f"{BASE_URL}?title=&items_per_page=18&page={page_num}"
        print(f"\n📖 Page {page_num + 1}: {url}")
        
        try:
            await page.goto(url, wait_until="networkidle", timeout=30000)
            await asyncio.sleep(2)
        except Exception as e:
            print(f"  ⚠️ Failed to load page {page_num}: {e}")
            break
        
        # Get all program cards
        cards = await page.query_selector_all(".usa-card .card-link, a.card-link")
        
        if not cards:
            print(f"  No more programs found. Stopping.")
            break
        
        print(f"  Found {len(cards)} programs on this page.")
        
        for card in cards:
            program = {}
            
            # Title & URL
            title = await card.get_attribute("title")
            if not title:
                title = await card.inner_text()
            program["title"] = title.strip() if title else ""
            
            href = await card.get_attribute("href")
            if href:
                if href.startswith("/"):
                    href = "https://www.fsa.usda.gov" + href
                program["url"] = href
            
            if program.get("title") and program.get("url"):
                all_programs.append(program)
    
    print(f"\n✅ Collected {len(all_programs)} program links. Now scraping details...")
    
    # Visit each detail page
    for idx, prog in enumerate(all_programs):
        print(f"  [{idx+1}/{len(all_programs)}] {prog['title'][:50]}...")
        details = await extract_program_detail(page, prog["url"])
        prog.update(details)
        
        # Be nice to the server
        await asyncio.sleep(1)
    
    return {
        "programs": all_programs,
        "scraped_at": datetime.now().isoformat(),
        "total_count": len(all_programs)
    }


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        )
        
        data = await scrape_fsa_programs(context)
        
        # Save
        with OUTPUT_PATH.open("w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        
        print(f"\n✅ Saved {data['total_count']} FSA programs to {OUTPUT_PATH}")
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
