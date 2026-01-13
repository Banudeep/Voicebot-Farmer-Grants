"""
Simple USDA API tools for direct use in voice agent
These functions can be called directly without MCP server
"""

import asyncio
import base64
import json
import os
import re
from pathlib import Path
from typing import Any, Optional, Tuple
from datetime import datetime, timedelta

import httpx

# USDA API Configuration
USDA_BASE_URL = "https://marsapi.ams.usda.gov/services/v1.2"
# Sanitize API key to remove potential whitespace or newlines from .env copy-paste
_RAW_KEY = os.getenv("USDA_API_KEY", "")
# Remove quotes and then remove all whitespace
USDA_API_KEY = "".join(_RAW_KEY.strip("'\"").split()) if _RAW_KEY else None

# Cache configuration
# Path: src/mcp_tools/usda_tools.py -> src/mcp_tools -> src -> root
CACHE_DIR = Path(__file__).parent.parent.parent / "cache"
CACHE_DIR.mkdir(exist_ok=True)
REPORTS_CACHE_FILE = CACHE_DIR / "usda_reports_cache.json"
CACHE_EXPIRY_HOURS = 24  # Refresh cache every 24 hours


def get_auth_headers():
    """Get authentication headers if API key is available"""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }
    if USDA_API_KEY:
        credentials = base64.b64encode(f"{USDA_API_KEY}:".encode()).decode()
        headers["Authorization"] = f"Basic {credentials}"
    return headers


async def fetch_api_endpoint(endpoint: str) -> dict:
    """Fetch data from a USDA API endpoint"""
    url = f"{USDA_BASE_URL}/{endpoint}"
    headers = get_auth_headers()
    
    # Print exact HTTP call details
    print("\n" + "=" * 80)
    print("🌐 USDA API HTTP CALL")
    print("=" * 80)
    print(f"Method: GET")
    print(f"URL: {url}")
    if "Authorization" in headers:
        print(f"Headers: Authorization: [REDACTED], User-Agent: {headers.get('User-Agent')}")
    else:
        print(f"Headers: No Authorization (Key missing)")
    print("=" * 80 + "\n")
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.get(url, headers=headers)
            
            # Catch Auth errors immediately
            if response.status_code in (401, 403):
                print(f"❌ API Authentication Failed: HTTP {response.status_code}")
                return {
                    "success": False,
                    "url": url,
                    "error": "Authentication failed (HTTP 401/403). Check USDA_API_KEY.",
                    "code": response.status_code
                }
            
            response.raise_for_status()
            
            try:
                data = response.json()
            except:
                data = {"raw_response": response.text}
            
            return {
                "success": True,
                "url": url,
                "data": data
            }
        except Exception as e:
            return {
                "success": False,
                "url": url,
                "error": str(e)
            }


def format_date_for_api(date_obj: datetime) -> str:
    """Format datetime object to MM/DD/YYYY format for USDA API"""
    return date_obj.strftime("%m/%d/%Y")


def parse_date_string(date_str: str) -> Optional[datetime]:
    """Parse date string in MM/DD/YYYY format to datetime object"""
    try:
        return datetime.strptime(date_str, "%m/%d/%Y")
    except ValueError:
        try:
            # Try other common formats
            return datetime.strptime(date_str, "%Y-%m-%d")
        except ValueError:
            return None


def has_price_values(data: Any) -> bool:
    """
    Check if the data structure actually contains price values.
    Recursively searches through the data structure for numeric price values.
    Returns True if price values are found, False otherwise.
    """
    if data is None:
        return False
    
    # If it's a number, check if it could be a price (positive number, reasonable range)
    if isinstance(data, (int, float)):
        # Prices are typically positive and in reasonable ranges (e.g., $2-$20 per bushel)
        return data > 0 and data < 1000
    
    # If it's a string, check if it contains price-like patterns
    if isinstance(data, str):
        # Look for dollar signs, price patterns like "4.50", "4.50/bu", etc.
        if '$' in data or '/bu' in data.lower() or '/ton' in data.lower():
            # Try to extract a number
            numbers = re.findall(r'\d+\.?\d*', data)
            if numbers:
                try:
                    price = float(numbers[0])
                    return price > 0 and price < 1000
                except:
                    pass
        return False
    
    # If it's a dict, recursively check values
    if isinstance(data, dict):
        # Check common price-related keys
        price_keys = ['price', 'bid', 'cashPrice', 'basis', 'value', 'amount', 'cost']
        for key, value in data.items():
            key_lower = str(key).lower()
            # If key suggests it's a price field, check the value
            if any(pk in key_lower for pk in price_keys):
                if has_price_values(value):
                    return True
            # Also recursively check nested structures
            if has_price_values(value):
                return True
        return False
    
    # If it's a list, check each item
    if isinstance(data, list):
        if len(data) == 0:
            return False
        # Check if any item in the list contains prices
        for item in data:
            if has_price_values(item):
                return True
        return False
    
    return False


async def check_date_for_data(endpoint: str, headers: dict, date_str: str, commodity: str) -> Tuple[bool, Optional[dict], Optional[str]]:
    """
    Check if data is available for a specific date.
    Returns: (has_data, data_dict, error_message)
    """
    query_parts = [f"report_begin_date={date_str}"]
    if commodity:
        query_parts.append(f"commodity={commodity}")
    
    url = f"{endpoint}?q={';'.join(query_parts)}"
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.get(url, headers=headers)
            
            if response.status_code == 200:
                try:
                    data = response.json()
                    
                    # First check if data structure exists
                    has_structure = False
                    if isinstance(data, dict):
                        has_structure = bool(
                            data.get("data") or 
                            data.get("results") or 
                            data.get("report") or
                            len(data) > 0
                        )
                    elif isinstance(data, list):
                        has_structure = len(data) > 0
                    else:
                        has_structure = bool(data)
                    
                    # If structure exists, check if it actually contains price values
                    if has_structure:
                        if has_price_values(data):
                            return (True, {"url": url, "data": data}, None)
                        else:
                            # Structure exists but no price values found
                            return (False, None, f"No price values found in data for {date_str}")
                    else:
                        return (False, None, f"No data available for {date_str}")
                        
                except (json.JSONDecodeError, ValueError):
                    return (False, None, f"Invalid response format for {date_str}")
            else:
                return (False, None, f"HTTP {response.status_code} for {date_str}")
                
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 400:
                return (False, None, f"Bad request for {date_str} (data likely not available)")
            elif e.response.status_code in (401, 403):
                return (False, None, f"AUTH_ERROR_HTTP_{e.response.status_code}")
            else:
                return (False, None, f"HTTP {e.response.status_code} for {date_str}")
        except Exception as e:
            return (False, None, f"Error for {date_str}: {str(e)}")


async def check_date_range_concurrently(endpoint: str, headers: dict, slug_id: int, start_date: datetime, num_days: int, commodity: str, phase_name: str, date_requested: str) -> Optional[dict]:
    """
    Check a range of dates concurrently and return the first successful result (most recent date).
    Returns the result dict if found, None otherwise.
    """
    # Create list of dates to check
    dates_to_check = []
    for days_back in range(num_days):
        current_date = start_date - timedelta(days=days_back)
        date_str = format_date_for_api(current_date)
        dates_to_check.append((days_back, date_str))
    
    # Check all dates concurrently
    tasks = [check_date_for_data(endpoint, headers, date_str, commodity) for _, date_str in dates_to_check]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    # Find the first successful result (most recent date)
    for idx, (days_back, date_str) in enumerate(dates_to_check):
        result = results[idx]
        
        # Handle exceptions
        if isinstance(result, Exception):
            continue
        
        has_data, data_dict, error = result
        
        if has_data and data_dict:
            return {
                "success": True,
                "slug_id": slug_id,
                "date_used": date_str,
                "date_requested": date_requested,
                "days_back": days_back,
                "search_phase": phase_name,
                "url": data_dict["url"],
                "data": data_dict["data"],
                "note": f"Data found for {date_str}" + (f" (requested {date_requested}, but data not available)" if days_back > 0 else "")
            }
    
    return None


async def get_corn_soybean_prices(slug_id: int = 3167, date: Optional[str] = None, commodity: str = "Corn,Soybeans") -> dict:
    """
    Get corn and/or soybean price data from USDA reports.
    If the requested date isn't available, automatically tries:
    1. Previous days up to 1 week (checked concurrently)
    2. If that fails, previous days up to 1 month (checked concurrently)
    3. If that still fails, searches year by year going backwards to find the latest available data
    """
    endpoint = f"{USDA_BASE_URL}/reports/{slug_id}/Report%20Detail"
    headers = get_auth_headers()
    
    # Determine starting date
    if date:
        start_date = parse_date_string(date)
        if not start_date:
            return {
                "success": False,
                "slug_id": slug_id,
                "error": f"Invalid date format: {date}. Please use MM/DD/YYYY format."
            }
    else:
        # If no date provided, start with today
        start_date = datetime.now()
    
    last_error = None
    
    # Phase 1: Try last 7 days (1 week) - check all concurrently
    print(f"🔍 Phase 1: Checking last 7 days concurrently starting from {format_date_for_api(start_date)}")
    date_requested_str = date if date else "today"
    result = await check_date_range_concurrently(endpoint, headers, slug_id, start_date, 8, commodity, "week", date_requested_str)
    
    # Check for Auth Error in result logic (Wait, check_date_range_concurrently returns found result OR None)
    # We need to peek at 'check_date_for_data' results, but check_date_range_concurrently hides them if None.
    # But wait! If result is found, we return it. If NOT found, we continue.
    # If Auth failed for ALL dates, we iterate to Phase 2. This is bad.
    
    # To fix this properly without refactoring everything: 
    # check_date_range_concurrently ONLY returns success.
    # Let's do a quick single-day check first to validate Auth!
    
    # Quick Auth Check with today's date (or start_date)
    print("🔑 Verifying API Authentication...")
    auth_check_date = format_date_for_api(start_date)
    has_access, _, auth_err = await check_date_for_data(endpoint, headers, auth_check_date, commodity)
    if not has_access and auth_err and "AUTH_ERROR" in auth_err:
        return {
            "success": False,
            "slug_id": slug_id,
            "error": f"USDA API Authentication Failed: {auth_err}. Please check your USDA_API_KEY in .env.",
            "note": "Stopping search immediately due to invalid credentials."
        }

    if result:
        return result
    
    # Phase 2: Search the entire current year day by day (concurrently in batches)
    print(f"🔍 Phase 2: Searching entire current year ({start_date.year}) day by day")
    current_year = start_date.year
    year_start = datetime(current_year, 1, 1)
    
    # Calculate how many days to check (from 8 days back to the start of the year)
    days_since_year_start = (start_date - year_start).days
    days_to_check_total = days_since_year_start - 7  # Exclude the 7 days already checked
    
    if days_to_check_total > 0:
        # Check in batches to avoid too many concurrent requests
        batch_size = 50  # Check 50 dates at a time concurrently
        dates_to_check = []
        
        for days_back in range(8, days_since_year_start + 1):
            check_date = start_date - timedelta(days=days_back)
            if check_date.year != current_year:
                break
            date_str = format_date_for_api(check_date)
            dates_to_check.append((days_back, date_str))
        
        # Process in batches
        for batch_start in range(0, len(dates_to_check), batch_size):
            batch = dates_to_check[batch_start:batch_start + batch_size]
            print(f"  Checking batch: {len(batch)} dates (days {batch[0][0]} to {batch[-1][0]})")
            
            tasks = [check_date_for_data(endpoint, headers, date_str, commodity) for _, date_str in batch]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Find the first successful result (most recent date)
            for idx, (days_back, date_str) in enumerate(batch):
                result_data = results[idx]
                if isinstance(result_data, Exception):
                    continue
                
                has_data, data_dict, error = result_data
                if has_data and data_dict:
                    return {
                        "success": True,
                        "slug_id": slug_id,
                        "date_used": date_str,
                        "date_requested": date_requested_str,
                        "days_back": days_back,
                        "search_phase": f"year_{current_year}",
                        "url": data_dict["url"],
                        "data": data_dict["data"],
                        "note": f"Data found for {date_str} (searched back {days_back} days in {current_year})"
                    }
    
    # Phase 3: Search previous years going backwards
    print(f"🔍 Phase 3: Searching previous years going backwards")
    max_years_back = 10  # Limit to 10 years to avoid infinite loops
    
    for year_offset in range(1, max_years_back + 1):  # Start from 1 since we already checked current year
        check_year = current_year - year_offset
        year_start = datetime(check_year, 1, 1)
        year_end = datetime(check_year, 12, 31)
        
        print(f"  Searching year {check_year} day by day...")
        
        # Search the entire year day by day in batches
        total_days_in_year = (year_end - year_start).days + 1
        batch_size = 50  # Check 50 dates at a time concurrently
        
        dates_to_check = []
        for day_offset in range(total_days_in_year):
            check_date = year_end - timedelta(days=day_offset)
            if check_date.year != check_year:
                break
            date_str = format_date_for_api(check_date)
            dates_to_check.append((check_date, date_str))
        
        # Process in batches
        for batch_start in range(0, len(dates_to_check), batch_size):
            batch = dates_to_check[batch_start:batch_start + batch_size]
            if batch_start == 0:
                print(f"    Checking {len(batch)} dates from end of year...")
            
            tasks = [check_date_for_data(endpoint, headers, date_str, commodity) for _, date_str in batch]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Find the first successful result (most recent date in this year)
            for idx, (check_date, date_str) in enumerate(batch):
                result_data = results[idx]
                if isinstance(result_data, Exception):
                    continue
                
                has_data, data_dict, error = result_data
                if has_data and data_dict:
                    return {
                        "success": True,
                        "slug_id": slug_id,
                        "date_used": date_str,
                        "date_requested": date_requested_str,
                        "days_back": (start_date - check_date).days,
                        "search_phase": f"year_{check_year}",
                        "url": data_dict["url"],
                        "data": data_dict["data"],
                        "note": f"Data found for {date_str} (searched back to year {check_year})"
                    }
        
        # If no data in this year, continue to previous year
        last_error = f"No data found in year {check_year}"
    
    # No data found after all searches
    return {
        "success": False,
        "slug_id": slug_id,
        "date_requested": date_requested_str,
        "error": f"No data available after searching: 7 days, entire current year, and {max_years_back} previous years (day by day). Last error: {last_error}",
        "note": "Exhausted all search phases but found no available data."
    }


def load_reports_cache() -> Optional[list]:
    """Load reports cache from file if it exists and is not expired"""
    if not REPORTS_CACHE_FILE.exists():
        return None
    
    try:
        with open(REPORTS_CACHE_FILE, 'r', encoding='utf-8') as f:
            cache_data = json.load(f)
        
        # Check if cache is expired
        cache_time_str = cache_data.get("cached_at", "2000-01-01")
        try:
            cache_time = datetime.fromisoformat(cache_time_str)
        except ValueError:
            # Handle different date formats
            try:
                cache_time = datetime.strptime(cache_time_str, "%Y-%m-%dT%H:%M:%S.%f")
            except ValueError:
                print(f"⚠️ Invalid cache timestamp format: {cache_time_str}")
                return None
        
        time_diff = datetime.now() - cache_time
        if time_diff > timedelta(hours=CACHE_EXPIRY_HOURS):
            print(f"⚠️ Cache expired ({time_diff.total_seconds() / 3600:.1f} hours old)")
            return None
        
        reports = cache_data.get("reports", [])
        if not reports:
            print("⚠️ Cache file exists but contains no reports")
            return None
        
        return reports
    except Exception as e:
        print(f"⚠️ Error loading cache: {e}")
        import traceback
        traceback.print_exc()
        return None


def save_reports_cache(reports: list):
    """Save reports to cache file"""
    try:
        cache_data = {
            "cached_at": datetime.now().isoformat(),
            "reports": reports
        }
        with open(REPORTS_CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump(cache_data, f, indent=2, ensure_ascii=False)
        print(f"✓ Cached {len(reports)} reports to {REPORTS_CACHE_FILE}")
    except Exception as e:
        print(f"⚠️ Error saving cache: {e}")


async def fetch_all_reports() -> list:
    """Fetch all reports from USDA API and cache them"""
    result = await fetch_api_endpoint("reports")
    
    if result.get("success") and result.get("data"):
        data = result["data"]
        # Handle different response formats
        if isinstance(data, list):
            reports = data
        elif isinstance(data, dict):
            reports = data.get("results", data.get("data", []))
        else:
            reports = []
        
        # Save to cache
        if reports:
            save_reports_cache(reports)
        
        return reports
    
    return []


async def find_state_reports(state: Optional[str] = None) -> dict:
    """Find slug_ids for state-specific grain reports. Checks cache first, then API if needed."""
    
    # Try to load from cache first
    cached_reports = load_reports_cache()
    cache_was_used = bool(cached_reports)
    
    if cache_was_used:
        print(f"✓ Using cache with {len(cached_reports)} reports")
    else:
        print("📥 Cache miss or expired - fetching from API...")
        cached_reports = await fetch_all_reports()
    
    # If still no reports, fall back to marketTypes endpoint
    if not cached_reports:
        print("📥 Falling back to marketTypes endpoint...")
        result = await fetch_api_endpoint("marketTypes/Point%20of%20Sale%20-%20Grain")
        if result.get("success") and result.get("data"):
            data = result["data"]
            if isinstance(data, list):
                cached_reports = data
            elif isinstance(data, dict):
                cached_reports = data.get("results", data.get("data", []))
    
    # If no state specified, return all reports
    if not state:
        return {
            "success": True,
            "data": cached_reports,
            "total_reports": len(cached_reports),
            "source": "cache" if cache_was_used else "api"
        }
    
    # Filter by state - prioritize reports with "Grain - [State]" pattern in markets
    state_lower = state.lower().strip()
    filtered_reports = []
    
    for report in cached_reports:
        # Get markets array (can be list or single string)
        markets = report.get("markets", [])
        if not isinstance(markets, list):
            # Handle case where market is a single string
            markets = [report.get("market", "")] if report.get("market") else []
        
        # Get market_types to ensure it's grain-related
        market_types = report.get("market_types", [])
        if not isinstance(market_types, list):
            market_types = [market_types] if market_types else []
        
        # Check if this is a grain report
        is_grain_report = False
        for mt in market_types:
            if isinstance(mt, str) and "grain" in mt.lower():
                is_grain_report = True
                break
        
        # Priority 1: Check for "Grain - [State Name]" pattern in markets
        state_found = False
        matching_market = None
        
        for market in markets:
            if not isinstance(market, str):
                continue
            market_lower = market.lower()
            
            # Check for "Grain - [State]" pattern (e.g., "Grain - North Carolina")
            if "grain" in market_lower and state_lower in market_lower:
                # Verify it's the pattern we want (Grain - State)
                if f"grain" in market_lower and state_lower in market_lower:
                    state_found = True
                    matching_market = market
                    break
        
        # Priority 2: If not found in markets, check other fields
        if not state_found:
            report_title = str(report.get("reportTitle") or report.get("report_title", "")).lower()
            slug_name = str(report.get("slugName") or report.get("slug_name", "")).lower()
            offices = report.get("offices", [])
            
            # Check if state appears in title or slug
            state_found = (
                state_lower in report_title or 
                state_lower in slug_name
            )
            
            # Also check offices array
            if not state_found and isinstance(offices, list):
                for office in offices:
                    if isinstance(office, str) and state_lower in office.lower():
                        state_found = True
                        break
        
        # Only include if state found AND it's a grain report (or if markets match the pattern)
        if state_found and (is_grain_report or matching_market):
            filtered_reports.append({
                "slugId": report.get("slugId") or report.get("slug_id"),
                "slugName": report.get("slugName") or report.get("slug_name"),
                "market": matching_market or (markets[0] if markets else report.get("market", "")),
                "markets": markets,
                "reportTitle": report.get("reportTitle") or report.get("report_title"),
                "offices": report.get("offices", [])
            })
    
    # If no matches found in cache, try API search as fallback
    if not filtered_reports:
        print(f"🔍 No matches in cache for '{state}', searching API...")
        result = await fetch_api_endpoint("marketTypes/Point%20of%20Sale%20-%20Grain")
        
        if result.get("success") and result.get("data"):
            data = result["data"]
            reports_list = data if isinstance(data, list) else data.get("results", data.get("data", []))
            
            for report in reports_list:
                # Get markets array
                markets = report.get("markets", [])
                if not isinstance(markets, list):
                    markets = [report.get("market", "")] if report.get("market") else []
                
                # Check for "Grain - [State]" pattern in markets
                state_found = False
                matching_market = None
                
                for market in markets:
                    if not isinstance(market, str):
                        continue
                    market_lower = market.lower()
                    if "grain" in market_lower and state_lower in market_lower:
                        state_found = True
                        matching_market = market
                        break
                
                if state_found:
                    filtered_reports.append({
                        "slugId": report.get("slugId"),
                        "slugName": report.get("slugName"),
                        "market": matching_market or (markets[0] if markets else report.get("market", "")),
                        "markets": markets,
                        "reportTitle": report.get("reportTitle")
                    })
    
    # Determine source - if we used cache initially, mark as cache even if we did API fallback
    # Only mark as API if we never had cache data
    source = "cache" if cache_was_used else "api"
    
    return {
        "success": True,
        "data": filtered_reports,
        "state_searched": state,
        "matches_found": len(filtered_reports),
        "source": source
    }


async def list_offices() -> dict:
    """List all USDA offices"""
    return await fetch_api_endpoint("offices")


async def get_office_reports(office_name: str) -> dict:
    """Get all reports from a specific USDA office"""
    office_encoded = office_name.replace(" ", "%20")
    return await fetch_api_endpoint(f"offices/{office_encoded}")


async def get_corn_soybean_prices_by_date_range(slug_id: int, start_date: str, end_date: str, commodity: str = "Corn,Soybeans") -> dict:
    """
    Get corn and/or soybean price data for a date range using USDA API's range filter.
    Uses the syntax: report_begin_date=start_date:end_date
    
    Args:
        slug_id: Report ID
        start_date: Start date in MM/DD/YYYY format
        end_date: End date in MM/DD/YYYY format
        commodity: "Corn", "Soybeans", or "Corn,Soybeans"
    
    Returns:
        dict with success status and data for the date range
    """
    endpoint = f"{USDA_BASE_URL}/reports/{slug_id}/Report%20Detail"
    headers = get_auth_headers()
    
    # Validate date formats
    start_dt = parse_date_string(start_date)
    end_dt = parse_date_string(end_date)
    
    if not start_dt:
        return {
            "success": False,
            "slug_id": slug_id,
            "error": f"Invalid start date format: {start_date}. Please use MM/DD/YYYY format."
        }
    
    if not end_dt:
        return {
            "success": False,
            "slug_id": slug_id,
            "error": f"Invalid end date format: {end_date}. Please use MM/DD/YYYY format."
        }
    
    if start_dt > end_dt:
        return {
            "success": False,
            "slug_id": slug_id,
            "error": f"Start date ({start_date}) must be before or equal to end date ({end_date})"
        }
    
    # Build query with date range using : separator
    query_parts = [f"report_begin_date={start_date}:{end_date}"]
    if commodity:
        query_parts.append(f"commodity={commodity}")
    
    url = f"{endpoint}?q={';'.join(query_parts)}"
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            
            try:
                data = response.json()
            except:
                data = {"raw_response": response.text}
            
            # Check if data contains price values
            if has_price_values(data):
                return {
                    "success": True,
                    "slug_id": slug_id,
                    "start_date": start_date,
                    "end_date": end_date,
                    "url": url,
                    "data": data,
                    "note": f"Data retrieved for date range {start_date} to {end_date}"
                }
            else:
                return {
                    "success": False,
                    "slug_id": slug_id,
                    "start_date": start_date,
                    "end_date": end_date,
                    "error": f"No price values found in data for date range {start_date} to {end_date}",
                    "url": url
                }
        except Exception as e:
            return {
                "success": False,
                "slug_id": slug_id,
                "start_date": start_date,
                "end_date": end_date,
                "url": url,
                "error": str(e)
            }


# Tools for GPT-4o Realtime API
USDA_TOOLS = [
    {
        "type": "function",
        "name": "get_corn_soybean_prices",
        "description": "Get corn and/or soybean price data from USDA reports. Returns JSON data with price information that you must parse and summarize. IMPORTANT: If the user mentions a specific state or location, you MUST first call find_state_reports to get the correct slug_id for that state. Do NOT use the default slug_id (3167) for state-specific queries. Only use 3167 for general/national prices when no state is mentioned. CRITICAL DATE HANDLING: DO NOT pass a date parameter unless the user specifically requests a particular date (e.g., 'What was the price on December 5th?' or 'Show me prices from last Tuesday'). If no date is provided, the tool automatically finds the most recent date with available data by searching backwards from today. AUTOMATIC RETRY: The tool automatically searches concurrently: (1) Previous 7 days, (2) If that fails, searches the ENTIRE current year day by day in batches, (3) If that still fails, searches previous years day by day going backwards up to 10 years to find the latest available data. The result will include 'date_used', 'days_back', and 'search_phase' fields. Always mention the date in your response (e.g., 'As of [date_used], prices are...').",
        "parameters": {
            "type": "object",
            "properties": {
                "slug_id": {
                    "type": "integer",
                    "description": "Report ID. For state-specific queries, use find_state_reports first to get the correct slug_id. For general prices with no state mentioned, you can use 3167 (Grain Market News).",
                },
                "date": {
                    "type": "string",
                    "description": "Date in MM/DD/YYYY format (e.g., '12/05/2025'). ONLY use this if the user specifically requests a particular date. If not provided, the tool automatically finds the most recent date with available data by searching backwards from today up to 1 week, then 1 month, then year by year.",
                },
                "commodity": {
                    "type": "string",
                    "description": "Commodity: 'Corn', 'Soybeans', or 'Corn,Soybeans' for both",
                    "enum": ["Corn", "Soybeans", "Corn,Soybeans"],
                    "default": "Corn,Soybeans"
                }
            },
            "required": []
        }
    },
    {
        "type": "function",
        "name": "find_state_reports",
        "description": "Find slug_ids for state-specific grain reports (e.g., 'Virginia', 'Illinois', 'Iowa'). Returns all Point of Sale - Grain reports with their slugId, market, and reportTitle. Use this to find the slug_id for a specific state's daily grain bids before calling get_corn_soybean_prices.",
        "parameters": {
            "type": "object",
            "properties": {
                "state": {
                    "type": "string",
                    "description": "State name to search for (e.g., 'Virginia', 'Illinois', 'Iowa'). Leave empty to get all states.",
                }
            },
            "required": []
        }
    },
    {
        "type": "function",
        "name": "list_offices",
        "description": "List all USDA offices. Use this to find office names, then use get_office_reports to get reports for a specific office.",
        "parameters": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "type": "function",
        "name": "get_office_reports",
        "description": "Get all reports from a specific USDA office (e.g., 'Richmond', 'St Joseph', 'Des Moines', 'Louisville'). Returns reports with slugId and titles. Use this to find daily grain bid reports for a specific location.",
        "parameters": {
            "type": "object",
            "properties": {
                "office_name": {
                    "type": "string",
                    "description": "Office name (e.g., 'Richmond', 'St Joseph', 'Des Moines'). Use list_offices to see available offices.",
                }
            },
            "required": ["office_name"]
        }
    },
    {
        "type": "function",
        "name": "get_corn_soybean_prices_by_date_range",
        "description": "Get corn and/or soybean price data for a date range using USDA API's range filter syntax (report_begin_date=start_date:end_date). Use this when the user asks for prices 'between two dates', 'from X to Y', 'over the past week/month', or wants to see trends over a time period. IMPORTANT: If the user mentions a specific state, you MUST first call find_state_reports to get the correct slug_id. Returns data for all dates within the specified range.",
        "parameters": {
            "type": "object",
            "properties": {
                "slug_id": {
                    "type": "integer",
                    "description": "Report ID. For state-specific queries, use find_state_reports first to get the correct slug_id. For general prices, use 3167 (Grain Market News).",
                },
                "start_date": {
                    "type": "string",
                    "description": "Start date in MM/DD/YYYY format (e.g., '06/06/2017')",
                },
                "end_date": {
                    "type": "string",
                    "description": "End date in MM/DD/YYYY format (e.g., '07/01/2017')",
                },
                "commodity": {
                    "type": "string",
                    "description": "Commodity: 'Corn', 'Soybeans', or 'Corn,Soybeans' for both",
                    "enum": ["Corn", "Soybeans", "Corn,Soybeans"],
                    "default": "Corn,Soybeans"
                }
            },
            "required": ["slug_id", "start_date", "end_date"]
        }
    }
]

TOOL_FUNCTIONS = {
    "get_corn_soybean_prices": get_corn_soybean_prices,
    "get_corn_soybean_prices_by_date_range": get_corn_soybean_prices_by_date_range,
    "find_state_reports": find_state_reports,
    "list_offices": list_offices,
    "get_office_reports": get_office_reports
}

