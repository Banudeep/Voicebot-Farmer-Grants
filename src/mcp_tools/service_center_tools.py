"""
Service Center Search Tool for USDA Voicebot

Provides FAST direct lookup over scraped service center data.
Data source: cache/service_centers_complete.json

Supports queries like:
- "Find the FSA office in Polk County, Iowa"
- "Who is the NRCS contact in Harris County, Texas?"
- "USDA service center in Franklin County"
"""

from pathlib import Path
from typing import Dict, Any, Optional, List

from mcp_tools.utils import (
    CACHE_DIR,
    AGENCY_NAMES,
    SERVICE_CENTER_LOCATOR_URL,
    load_county_db,
    load_json_cache,
    normalize_state,
)

# Paths
SERVICE_CENTERS_PATH = CACHE_DIR / "service_centers_complete.json"

# Cached data (loaded once at import time for speed)
_SERVICE_CENTERS_CACHE: Optional[Dict] = None


def _load_service_centers() -> Dict[str, Any]:
    """Load and cache service center data"""
    global _SERVICE_CENTERS_CACHE
    if _SERVICE_CENTERS_CACHE is None:
        _SERVICE_CENTERS_CACHE = load_json_cache(
            SERVICE_CENTERS_PATH, fallback={"counties": {}}
        )
    return _SERVICE_CENTERS_CACHE


def _normalize_county_slug(county: str) -> str:
    """Convert county name to slug format used in keys"""
    slug = county.lower().strip()
    # Remove common suffixes
    for suffix in [" county", " parish", " borough", " census area", " municipality"]:
        slug = slug.replace(suffix, "")
    # Convert to slug format
    slug = slug.replace(" ", "-").replace(".", "").replace("'", "").strip("-")
    # Handle special cases (st. -> st, etc.)
    slug = slug.replace("st-", "st").replace("ste-", "ste")
    return slug


def _build_key(state_code: str, county: str) -> str:
    """Build lookup key from state code and county name"""
    slug = _normalize_county_slug(county)
    return f"{state_code}_{slug}"


async def search_service_center(
    query: str,
    state: Optional[str] = None,
    county: Optional[str] = None,
    agency: Optional[str] = None
) -> Dict[str, Any]:
    """
    Search for USDA service center contacts by county.
    
    Args:
        query: Natural language search query (for context/logging)
        state: State name or code (e.g., "Iowa", "IA") - REQUIRED for lookup
        county: County name (e.g., "Polk", "Polk County") - REQUIRED for lookup
        agency: Optional agency filter ("FSA", "NRCS", "RD")
    
    Returns:
        Dictionary with service center contacts including emails, phones, addresses
    """
    try:
        data = _load_service_centers()
        county_db = load_county_db()
        
        # Validate state
        if not state:
            return {
                "success": False,
                "error": "State is required. Please specify a state (e.g., 'Iowa' or 'IA').",
                "locator_url": SERVICE_CENTER_LOCATOR_URL
            }
        
        state_code = normalize_state(state, county_db)
        if not state_code:
            return {
                "success": False,
                "error": f"State '{state}' not recognized. Use a state name or two-letter code.",
                "locator_url": SERVICE_CENTER_LOCATOR_URL
            }
        
        # Validate county
        if not county:
            return {
                "success": False,
                "error": "County is required. Please specify a county name.",
                "locator_url": SERVICE_CENTER_LOCATOR_URL
            }
        
        # Try 1: Direct lookup
        key = _build_key(state_code, county)
        county_data = data.get("counties", {}).get(key)
        
        # Try 2: Alternative slug (handle spaces, special chars differently)
        if not county_data:
            alt_slug = county.lower().replace(" ", "").replace("county", "").replace("parish", "").replace("city", "")
            alt_key = f"{state_code}_{alt_slug}"
            county_data = data.get("counties", {}).get(alt_key)
            
        # Try 3: Suffix variations (common for VA cities)
        if not county_data:
            slug = _normalize_county_slug(county)
            variations = [
                f"{state_code}_{slug}-city",
                f"{state_code}_{slug}city",
                f"{state_code}_{slug}-county",
                f"{state_code}_{slug}county"
            ]
            for var_key in variations:
                if var_key in data.get("counties", {}):
                    county_data = data.get("counties", {}).get(var_key)
                    break
                    
        # Try 4: Fuzzy Match - Iterate all keys for that state
        if not county_data:
            normalized_q = _normalize_county_slug(county).replace("-", "").replace("_", "")
            for k, v in data.get("counties", {}).items():
                if not k.startswith(f"{state_code}_"):
                    continue
                
                # Check if query is contained in key or vice versa
                k_clean = k.replace(f"{state_code}_", "").replace("-", "").replace("_", "")
                if normalized_q in k_clean or k_clean in normalized_q:
                     county_data = v
                     break
        
        if not county_data:
            state_name = county_db.get("states", {}).get(state_code, {}).get("name", state_code)
            return {
                "success": True, # Still success technically, just no data found
                "results": None,
                "message": f"No service center data found for {county}, {state_name}.",
                "dashboard_url": f"https://www.farmers.gov/dashboard/{state_name.lower().replace(' ', '-')}/{_normalize_county_slug(county)}",
                "locator_url": SERVICE_CENTER_LOCATOR_URL
            }
        
        # Filter by agency if specified
        service_centers = county_data.get("service_centers", {})
        if agency and agency.upper().strip() not in ("ALL", ""):
            agency_upper = agency.upper().strip()
            if agency_upper in service_centers:
                service_centers = {agency_upper: service_centers[agency_upper]}
            else:
                available = list(service_centers.keys())
                return {
                    "success": True,
                    "results": None,
                    "message": f"No {agency_upper} office found in {county_data['county']}, {state_code}. Available agencies: {', '.join(available)}",
                    "available_agencies": available
                }
        
        # Format response
        formatted_agencies = []
        for agency_code, info in service_centers.items():
            formatted = {
                "agency": agency_code,
                "agency_name": AGENCY_NAMES.get(agency_code, agency_code),
                "service_center": info.get("service_center", ""),
                "contact_name": info.get("contact_name", ""),
                "email": info.get("email", ""),
                "phone": info.get("phone", ""),
                "physical_address": info.get("address", ""),
                "mailing_address": info.get("mailing_address", "")
            }
            formatted_agencies.append(formatted)
        
        return {
            "success": True,
            "state": state_code,
            "county": county_data.get("county", county),
            "dashboard_url": county_data.get("url", ""),
            "agencies": formatted_agencies,
            "message": f"Found {len(formatted_agencies)} USDA office(s) in {county_data.get('county', county)}, {state_code}."
        }
    
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "locator_url": SERVICE_CENTER_LOCATOR_URL
        }


# Tool definition for LLM integration
SEARCH_SERVICE_CENTER_TOOL = {
    "type": "function",
    "function": {
        "name": "search_service_center",
        "description": "Search for USDA service center contacts (FSA, NRCS, Rural Development) by county. Returns staff emails, phone numbers, physical and mailing addresses. Use when user asks about local USDA offices or service centers.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query context (e.g., 'FSA office', 'NRCS contact')"
                },
                "state": {
                    "type": "string",
                    "description": "State name (e.g., 'Iowa') or two-letter code (e.g., 'IA'). REQUIRED."
                },
                "county": {
                    "type": "string",
                    "description": "County name (e.g., 'Polk', 'Polk County'). REQUIRED."
                },
                "agency": {
                    "type": "string",
                    "description": "Filter by SPECIFIC agency. OMIT this parameter to get ALL agencies (FSA, NRCS, RD) in a SINGLE call - this is faster. Only use if user specifically asks for one agency.",
                    "enum": ["FSA", "NRCS", "RD", "ALL"]
                }
            },
            "required": ["query", "state", "county"]
        }
    }
}

# Export for integration
SERVICE_CENTER_TOOLS = [SEARCH_SERVICE_CENTER_TOOL]
SERVICE_CENTER_TOOL_FUNCTIONS = {"search_service_center": search_service_center}


# Test
if __name__ == "__main__":
    import asyncio
    
    async def test():
        print("=" * 60)
        print("Testing search_service_center (Direct Lookup)")
        print("=" * 60)
        
        # Test 1: Full lookup
        print("\n1. Iowa/Polk County - All agencies:")
        result = await search_service_center("FSA office", state="Iowa", county="Polk")
        if result.get("success") and result.get("agencies"):
            for a in result["agencies"]:
                print(f"   {a['agency']}: {a['contact_name']} - {a['email']}")
                print(f"      Physical: {a['physical_address']}")
                print(f"      Mailing:  {a['mailing_address']}")
        else:
            print(f"   {result.get('message') or result.get('error')}")
        
        # Test 2: Specific agency
        print("\n2. Oklahoma/McClain County - FSA only:")
        result = await search_service_center("contact info", state="OK", county="McClain", agency="FSA")
        if result.get("success") and result.get("agencies"):
            a = result["agencies"][0]
            print(f"   {a['contact_name']} - {a['email']}")
        else:
            print(f"   {result.get('message') or result.get('error')}")
        
        # Test 3: State name instead of code
        print("\n3. Alabama/Autauga County:")
        result = await search_service_center("NRCS", state="Alabama", county="Autauga")
        if result.get("success"):
            print(f"   Found {len(result.get('agencies', []))} agencies")
            print(f"   Dashboard: {result.get('dashboard_url')}")
        
        print("\n" + "=" * 60)
        print("Tests complete!")
    
    asyncio.run(test())
