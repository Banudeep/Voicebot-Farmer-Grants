"""
Create comprehensive US county database from FIPS codes API
and prepare for full scraping of USDA service centers.

Fetches all ~3,143 US counties and creates:
1. cache/us_counties.json - Complete county database with URL slugs
2. Updates scraper configuration for full run
"""

import asyncio
import json
import re
from pathlib import Path
from typing import Dict, Any
import httpx

# Paths
BASE_DIR = Path(__file__).parent.parent
CACHE_DIR = BASE_DIR / "cache"
OUTPUT_FILE = CACHE_DIR / "us_counties.json"


def create_url_slug(county_name: str) -> str:
    """
    Convert county name to URL slug for farmers.gov dashboard.
    Examples:
        "Autauga County" -> "autauga"
        "St. Louis County" -> "st-louis"
        "Fairfax City" -> "fairfax-city"
    """
    # Remove common suffixes
    slug = county_name.lower()
    slug = re.sub(r'\s+(county|parish|borough|census area|municipality|city and borough)$', '', slug, flags=re.I)
    
    # Replace periods and special chars
    slug = slug.replace(".", "")
    slug = slug.replace("'", "")
    slug = slug.replace("  ", " ")
    
    # Replace spaces with hyphens
    slug = slug.replace(" ", "-")
    
    # Remove double hyphens
    while "--" in slug:
        slug = slug.replace("--", "-")
    
    return slug.strip("-")


async def fetch_fips_data() -> Dict[str, Any]:
    """Fetch the complete FIPS county database"""
    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.get("https://api.fips.codes/index")
        response.raise_for_status()
        return response.json()


def process_fips_data(fips_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Process FIPS data into a format suitable for scraping.
    Returns database with state info and county list with URL slugs.
    """
    result = {
        "metadata": {
            "source": "https://api.fips.codes/index",
            "total_counties": 0,
            "total_states": 0
        },
        "states": {},
        "counties_by_state": {}
    }
    
    # State slugs for URL
    state_slugs = {
        "AL": "alabama", "AK": "alaska", "AZ": "arizona", "AR": "arkansas",
        "CA": "california", "CO": "colorado", "CT": "connecticut", "DE": "delaware",
        "FL": "florida", "GA": "georgia", "HI": "hawaii", "ID": "idaho",
        "IL": "illinois", "IN": "indiana", "IA": "iowa", "KS": "kansas",
        "KY": "kentucky", "LA": "louisiana", "ME": "maine", "MD": "maryland",
        "MA": "massachusetts", "MI": "michigan", "MN": "minnesota", "MS": "mississippi",
        "MO": "missouri", "MT": "montana", "NE": "nebraska", "NV": "nevada",
        "NH": "new-hampshire", "NJ": "new-jersey", "NM": "new-mexico", "NY": "new-york",
        "NC": "north-carolina", "ND": "north-dakota", "OH": "ohio", "OK": "oklahoma",
        "OR": "oregon", "PA": "pennsylvania", "RI": "rhode-island", "SC": "south-carolina",
        "SD": "south-dakota", "TN": "tennessee", "TX": "texas", "UT": "utah",
        "VT": "vermont", "VA": "virginia", "WA": "washington", "WV": "west-virginia",
        "WI": "wisconsin", "WY": "wyoming", "DC": "district-of-columbia",
        "PR": "puerto-rico", "VI": "virgin-islands", "GU": "guam", "AS": "american-samoa",
        "MP": "northern-mariana-islands"
    }
    
    total_counties = 0
    
    for state_code, state_data in fips_data.items():
        if not isinstance(state_data, dict):
            continue
        
        state_name = state_data.get("_name", state_code)
        state_fips = state_data.get("_fips", "")
        state_slug = state_slugs.get(state_code, state_code.lower())
        
        # Store state info
        result["states"][state_code] = {
            "name": state_name,
            "fips": state_fips,
            "slug": state_slug
        }
        
        # Process counties
        counties = []
        for key, value in state_data.items():
            if key.startswith("_"):
                continue  # Skip metadata fields
            
            county_name = key
            fips_code = value
            county_slug = create_url_slug(county_name)
            
            counties.append({
                "name": county_name,
                "slug": county_slug,
                "fips": fips_code,
                "url": f"https://www.farmers.gov/dashboard/{state_slug}/{county_slug}"
            })
            total_counties += 1
        
        # Sort counties alphabetically
        counties.sort(key=lambda x: x["name"])
        result["counties_by_state"][state_code] = counties
    
    result["metadata"]["total_counties"] = total_counties
    result["metadata"]["total_states"] = len(result["states"])
    
    return result


async def main():
    """Main function"""
    print("=" * 60)
    print("US County Database Builder")
    print("=" * 60)
    
    CACHE_DIR.mkdir(exist_ok=True)
    
    # Fetch FIPS data
    print("\nFetching FIPS county data...")
    fips_data = await fetch_fips_data()
    print(f"  Retrieved data for {len(fips_data)} states/territories")
    
    # Process data
    print("\nProcessing county data...")
    county_db = process_fips_data(fips_data)
    print(f"  Processed {county_db['metadata']['total_counties']} counties")
    print(f"  Across {county_db['metadata']['total_states']} states/territories")
    
    # Save to file
    with OUTPUT_FILE.open("w", encoding="utf-8") as f:
        json.dump(county_db, f, indent=2)
    print(f"\nSaved to {OUTPUT_FILE}")
    
    # Print sample
    print("\nSample data:")
    for state in ["IA", "TX", "CA"]:
        if state in county_db["counties_by_state"]:
            counties = county_db["counties_by_state"][state]
            print(f"\n  {state} ({len(counties)} counties):")
            for county in counties[:3]:
                print(f"    - {county['name']} -> {county['slug']}")
    
    print("\n" + "=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
