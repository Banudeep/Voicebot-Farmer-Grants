"""
Deep State News Scraper

Scrapes all state news by:
1. Navigating to each state's dashboard
2. Clicking "View More News" 
3. Extracting all news items
4. Clicking into each article to get full content

Output: cache/state_news_deep.json
"""

import asyncio
import json
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List
import argparse

try:
    from playwright.async_api import async_playwright, Page, Browser
    HAS_PLAYWRIGHT = True
except ImportError:
    HAS_PLAYWRIGHT = False
    print("⚠️ Playwright required: pip install playwright && playwright install chromium")

BASE_DIR = Path(__file__).parent.parent.parent
CACHE_DIR = BASE_DIR / "cache"
OUTPUT_PATH = CACHE_DIR / "state_news_deep.json"
COUNTY_DB_PATH = CACHE_DIR / "us_counties.json"

# US States list
STATES = {
    "AL": "alabama", "AK": "alaska", "AZ": "arizona", "AR": "arkansas", "CA": "california",
    "CO": "colorado", "CT": "connecticut", "DE": "delaware", "FL": "florida", "GA": "georgia",
    "HI": "hawaii", "ID": "idaho", "IL": "illinois", "IN": "indiana", "IA": "iowa",
    "KS": "kansas", "KY": "kentucky", "LA": "louisiana", "ME": "maine", "MD": "maryland",
    "MA": "massachusetts", "MI": "michigan", "MN": "minnesota", "MS": "mississippi", "MO": "missouri",
    "MT": "montana", "NE": "nebraska", "NV": "nevada", "NH": "new-hampshire", "NJ": "new-jersey",
    "NM": "new-mexico", "NY": "new-york", "NC": "north-carolina", "ND": "north-dakota", "OH": "ohio",
    "OK": "oklahoma", "OR": "oregon", "PA": "pennsylvania", "RI": "rhode-island", "SC": "south-carolina",
    "SD": "south-dakota", "TN": "tennessee", "TX": "texas", "UT": "utah", "VT": "vermont",
    "VA": "virginia", "WA": "washington", "WV": "west-virginia", "WI": "wisconsin", "WY": "wyoming"
}


async def extract_article_content(page: Page, url: str) -> Dict[str, Any]:
    """Navigate to article and extract full content"""
    try:
        await page.goto(url, wait_until="networkidle", timeout=30000)
        await asyncio.sleep(1.5)
        
        content = {}
        
        # Try multiple selectors for title (different USDA sites have different structures)
        title_selectors = ['h1.margin-0.grid-col-12', 'h1.usa-page-title', 'article h1', 'main h1', '.node__title', 'h1']
        for sel in title_selectors:
            elem = await page.query_selector(sel)
            if elem:
                text = await elem.inner_text()
                # Skip generic site titles
                if text and len(text) > 10 and "USDA" not in text[:10]:
                    content["title"] = text.strip()
                    break
        
        # Date - look for time element with datetime
        time_elem = await page.query_selector('time[datetime]')
        if time_elem:
            content["date"] = await time_elem.inner_text()
            content["datetime"] = await time_elem.get_attribute("datetime")
        else:
            # Fallback - look for date patterns in meta or headers
            date_elem = await page.query_selector('.field--name-field-date, .date, .posted-date')
            if date_elem:
                content["date"] = await date_elem.inner_text()
        
        # Article content - try specific field selectors first (Drupal-based USDA sites)
        content_selectors = [
            '.field--name-field-text-long',  # NRCS article body
            '.field--name-body',              # Generic Drupal body
            '.node__content .field__item',    # FSA/other USDA sites
            'article .usa-prose',             # USA Design System
            'article .content',               # Generic
            '.press-release-content',         # Press releases
            'main .field__item',              # Main content area
        ]
        
        full_text = ""
        for sel in content_selectors:
            elems = await page.query_selector_all(sel)
            if elems:
                texts = []
                for elem in elems:
                    text = await elem.inner_text()
                    if text and len(text) > 50:
                        texts.append(text.strip())
                if texts:
                    full_text = '\n\n'.join(texts)
                    break
        
        # Fallback to article tag
        if not full_text or len(full_text) < 100:
            article = await page.query_selector('article')
            if article:
                full_text = await article.inner_text()
        
        if full_text:
            # Clean up - remove nav, footer, sidebar content
            lines = [line.strip() for line in full_text.split('\n') if line.strip()]
            # Filter out likely nav/footer items
            lines = [l for l in lines if len(l) > 20 or l.endswith('.') or l.endswith(':')]
            content["full_text"] = '\n'.join(lines)
            content["summary"] = content["full_text"][:800] + "..." if len(content["full_text"]) > 800 else content["full_text"]
        
        return content
        
    except Exception as e:
        return {"error": str(e)}


async def scrape_state_news(page: Page, state_code: str, state_slug: str) -> Dict[str, Any]:
    """Scrape all news for a state with full article content"""
    result = {
        "state_code": state_code,
        "state_name": state_slug.replace("-", " ").title(),
        "scraped_at": datetime.now().isoformat(),
        "news_items": []
    }
    
    try:
        # Get first county for this state to access news
        county_db_path = CACHE_DIR / "us_counties.json"
        if county_db_path.exists():
            with county_db_path.open() as f:
                county_db = json.load(f)
            counties = county_db.get("counties_by_state", {}).get(state_code, [])
            if counties:
                first_county = counties[0]["slug"]
            else:
                first_county = "county"
        else:
            first_county = "county"
        
        # Navigate to news listing page directly
        news_url = f"https://www.farmers.gov/dashboard/{state_slug}/{first_county}/news"
        await page.goto(news_url, wait_until="networkidle", timeout=30000)
        await asyncio.sleep(2)
        
        # FIRST: Collect all news items from the listing (URLs and metadata)
        news_items = []
        feed_items = await page.query_selector_all('.feed-item')
        print(f"  Found {len(feed_items)} news items for {state_code}")
        
        for item in feed_items:
            try:
                news_data = {}
                
                # Headline and link
                headline_elem = await item.query_selector('.item-headline a')
                if headline_elem:
                    news_data["headline"] = (await headline_elem.inner_text()).strip()
                    news_data["url"] = await headline_elem.get_attribute("href")
                
                # Date from listing
                date_elem = await item.query_selector('.item-date')
                if date_elem:
                    news_data["listing_date"] = (await date_elem.inner_text()).strip()
                
                # Category
                category_elem = await item.query_selector('.item-category')
                if category_elem:
                    news_data["category"] = (await category_elem.inner_text()).strip()
                
                if news_data.get("url"):
                    news_items.append(news_data)
                    
            except Exception:
                continue
        
        # SECOND: Visit each article URL to get full content
        for idx, news_data in enumerate(news_items):
            try:
                print(f"    [{idx+1}/{len(news_items)}] Fetching: {news_data['headline'][:50]}...")
                article_content = await extract_article_content(page, news_data["url"])
                news_data.update(article_content)
            except Exception as e:
                news_data["error"] = str(e)
        
        result["news_items"] = news_items
        result["total_items"] = len(news_items)
        
    except Exception as e:
        result["error"] = str(e)
    
    return result


async def run_deep_news_scrape(states_to_scrape: List[str] = None):
    """Scrape news for all states with full article content"""
    if not HAS_PLAYWRIGHT:
        print("❌ Playwright not installed!")
        return
    
    states = states_to_scrape or list(STATES.keys())
    
    print("=" * 60)
    print("Deep State News Scraper")
    print("=" * 60)
    print(f"States to scrape: {len(states)}")
    print("=" * 60)
    
    results = {
        "metadata": {
            "scraped_at": datetime.now().isoformat(),
            "total_states": len(states)
        },
        "states": {}
    }
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        page.set_default_timeout(30000)
        
        for idx, state_code in enumerate(states):
            state_slug = STATES.get(state_code, state_code.lower())
            print(f"\n[{idx+1}/{len(states)}] Scraping {state_code} ({state_slug})...")
            
            state_news = await scrape_state_news(page, state_code, state_slug)
            results["states"][state_code] = state_news
            
            # Save after each state
            with OUTPUT_PATH.open("w", encoding="utf-8") as f:
                json.dump(results, f, indent=2)
            
            print(f"  ✓ {state_code}: {len(state_news.get('news_items', []))} articles with full content")
        
        await browser.close()
    
    print("\n" + "=" * 60)
    print("COMPLETE")
    print("=" * 60)
    print(f"Output: {OUTPUT_PATH}")
    total_articles = sum(len(s.get("news_items", [])) for s in results["states"].values())
    print(f"Total articles: {total_articles}")


def main():
    parser = argparse.ArgumentParser(description="Deep scrape state news with full article content")
    parser.add_argument("--states", nargs="+", help="Specific states to scrape (e.g., IA TX CA)")
    parser.add_argument("--test", action="store_true", help="Test mode (Iowa only)")
    args = parser.parse_args()
    
    states = args.states
    if args.test:
        states = ["IA"]
    
    asyncio.run(run_deep_news_scrape(states_to_scrape=states))


if __name__ == "__main__":
    main()
