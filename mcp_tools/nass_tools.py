"""
NASS Quick Stats API tools for the STS voice agent.

These tools wrap the Quick Stats API:
  - https://quickstats.nass.usda.gov/api/api_GET
  - https://quickstats.nass.usda.gov/api/get_param_values
  - https://quickstats.nass.usda.gov/api/get_counts

They are designed to:
  - Let the model discover valid parameter values (via get_param_values)
  - Check how many rows a query would return (get_counts)
  - Fetch the actual data (api_GET) in JSON format
"""

import asyncio
import json
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

import httpx

# Logging
try:
    from logging_config import get_logger
    logger = get_logger("voicebot.tools.nass")
except ImportError:
    import logging
    logger = logging.getLogger("voicebot.tools.nass")

# Caching
try:
    from cache_manager import cached
    HAS_CACHE = True
except ImportError:
    HAS_CACHE = False
    # Fallback no-op decorator
    def cached(name, ttl=None):
        def decorator(func):
            return func
        return decorator

NASS_BASE_URL = "https://quickstats.nass.usda.gov/api"
NASS_API_KEY = (
    os.getenv("NASS_API_KEY")
    or os.getenv("USDA_NASS_API_KEY")
    or os.getenv("API_KEY")
)


def _ensure_key() -> str:
    if not NASS_API_KEY:
        raise RuntimeError(
            "NASS_API_KEY (or USDA_NASS_API_KEY / API_KEY) is not set. "
            "Get a Quick Stats API key from https://quickstats.nass.usda.gov/api "
            "and set it in your environment."
        )
    return NASS_API_KEY


async def _nass_get(endpoint: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Helper for GET requests to the Quick Stats API.
    Always expects JSON responses (the QuickStats endpoints used here are JSON by default).
    """
    key = _ensure_key()
    url = f"{NASS_BASE_URL}{endpoint}"

    query: Dict[str, Any] = {"key": key}
    if params:
        query.update(params)

    # Log HTTP call details (without API key)
    logger.info("NASS API HTTP CALL")
    logger.debug(f"Method: GET, URL: {url}")

    # Redact key from displayed query
    query_display = {k: "[REDACTED]" if k == "key" else v for k, v in query.items()}
    logger.debug(f"Query Parameters: {json.dumps(query_display, indent=2)}")

    # Also log a safe full URL with key redacted
    import urllib.parse

    safe_query = dict(query)
    safe_query["key"] = "REDACTED"
    safe_full_url = f"{url}?{urllib.parse.urlencode(safe_query)}"
    logger.debug(f"Full URL (redacted): {safe_full_url}")

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.get(url, params=query)
        resp.raise_for_status()
        data = resp.json()

        # Check for 50,000 row limit error (either in returned JSON or error text)
        if isinstance(data, dict):
            error_msg = data.get("error", "")
            if (
                "50,000" in error_msg
                or "50000" in error_msg
                or "limit" in error_msg.lower()
            ):
                return {
                    "success": False,
                    "endpoint": endpoint,
                    "params": query,
                    "error": "Row limit exceeded (50,000 rows). Add more filters to narrow the query.",
                    "error_code": "ROW_LIMIT_EXCEEDED",
                    "suggestion": (
                        "Add additional filters such as state_alpha, county_name, "
                        "year, or other parameters to narrow the results."
                    ),
                }

        return {
            "success": True,
            "endpoint": endpoint,
            "params": query,
            "data": data,
        }
    except httpx.HTTPStatusError as e:
        error_text = e.response.text
        # Check for 50,000 row limit in error response
        if (
            "50,000" in error_text
            or "50000" in error_text
            or "limit" in error_text.lower()
        ):
            return {
                "success": False,
                "endpoint": endpoint,
                "params": query,
                "error": "Row limit exceeded (50,000 rows). Add more filters to narrow the query.",
                "error_code": "ROW_LIMIT_EXCEEDED",
                "suggestion": (
                    "Add additional filters such as state_alpha, county_name, year "
                    "(specific year instead of a range), or statisticcat_desc."
                ),
            }
        return {
            "success": False,
            "endpoint": endpoint,
            "params": query,
            "error": f"HTTP {e.response.status_code}: {error_text}",
        }
    except Exception as e:
        return {
            "success": False,
            "endpoint": endpoint,
            "params": query,
            "error": str(e),
        }


# =========================
# Tool functions
# =========================


async def nass_get_param_values(param: str) -> Dict[str, Any]:
    """
    Get all possible values for a Quick Stats parameter.

    Example: param='sector_desc' or param='commodity_desc'

    The QuickStats API returns values as:
      {"param_name": ["VAL1", "VAL2", ...]}
    """
    return await _nass_get("/get_param_values/", params={"param": param})


async def nass_get_counts(filters: Dict[str, str]) -> Dict[str, Any]:
    """
    Get the number of rows that would be returned by a Quick Stats query.

    QuickStats API uses WHAT/WHERE/WHEN parameters:
    - WHAT: commodity_desc, sector_desc, statisticcat_desc, etc.
    - WHERE: state_alpha, county_name, region_desc, etc.
    - WHEN: year, year__GE (greater than or equal), freq_desc, etc.

    Args:
        filters: REQUIRED - Dictionary of Quick Stats query parameters as strings, e.g.:
            {
              "commodity_desc": "CORN",      # WHAT
              "year__GE": "2010",            # WHEN (year >= 2010)
              "state_alpha": "VA"            # WHERE
            }
            Must contain at least one parameter.
            If result exceeds 50,000 rows, add more filters (e.g., state, county, year).

    Returns:
        Dict with success flag and either data or an error message.
    """
    if not filters or not isinstance(filters, dict) or len(filters) == 0:
        return {
            "success": False,
            "error": (
                "filters parameter is required and must contain at least one query parameter. "
                "Example: {'commodity_desc': 'CORN', 'year': '2021'}"
            ),
            "example_filters": {
                "commodity_desc": "CORN",
                "year": "2021",
                "state_alpha": "VA",
            },
        }

    result = await _nass_get("/get_counts/", params=filters)

    # If limit exceeded, suggest adding more filters
    if not result.get("success") and result.get("error_code") == "ROW_LIMIT_EXCEEDED":
        result["suggestion"] = (
            "Add more filters to narrow the query. Suggested filters: "
            "state_alpha (e.g., 'VA'), county_name, year (specific year instead of range), "
            "or statisticcat_desc to narrow results."
        )

    return result


async def _split_query_by_states(filters: Dict[str, str], format: str) -> Dict[str, Any]:
    """
    Split a query by states if it would exceed the 50,000 row limit.
    Uses get_param_values('state_alpha') to discover valid state codes.
    """
    states_result = await nass_get_param_values("state_alpha")
    if not states_result.get("success") or "data" not in states_result:
        return {
            "success": False,
            "error": "Could not retrieve state list for query splitting",
        }

    states_data = states_result["data"]
    states: List[str] = []

    # QuickStats get_param_values returns: {"state_alpha": ["AL", "AK", ...]}
    if isinstance(states_data, dict) and "state_alpha" in states_data:
        raw_states = states_data.get("state_alpha") or []
        if isinstance(raw_states, list):
            states = [s for s in raw_states if s]
    elif isinstance(states_data, list):
        # Fallback if the API ever changes shape
        for item in states_data:
            if isinstance(item, dict) and "state_alpha" in item:
                state_code = item["state_alpha"]
                if state_code and state_code not in states:
                    states.append(state_code)
            elif isinstance(item, str) and item not in states:
                states.append(item)

    if not states:
        return {
            "success": False,
            "error": "Could not extract state codes from API response",
        }

    logger.info(f"Splitting query by {len(states)} states to avoid 50,000 row limit...")

    all_results: List[Any] = []
    failed_states: List[str] = []

    # Process in batches to avoid overwhelming the API
    batch_size = 10
    for i in range(0, len(states), batch_size):
        batch = states[i : i + batch_size]
        tasks = []
        for state in batch:
            state_filters = dict(filters)
            state_filters["state_alpha"] = state
            params = dict(state_filters)
            params["format"] = format
            tasks.append(_nass_get("/api_GET/", params=params))

        batch_results = await asyncio.gather(*tasks, return_exceptions=True)

        for state, result in zip(batch, batch_results):
            if isinstance(result, Exception):
                logger.warning(f"Error querying state {state}: {result}")
                failed_states.append(state)
            elif result.get("success") and "data" in result:
                data = result["data"]
                # api_GET returns {"data":[...]} shape
                if isinstance(data, dict) and "data" in data and isinstance(
                    data["data"], list
                ):
                    all_results.extend(data["data"])
                elif isinstance(data, list):
                    all_results.extend(data)

    return {
        "success": True,
        "data": all_results,
        "total_rows": len(all_results),
        "states_queried": len(states),
        "failed_states": failed_states,
        "split_method": "by_state",
        "note": f"Query was automatically split by {len(states)} states to avoid 50,000 row limit",
    }


async def _split_query_by_years(
    filters: Dict[str, str], format: str, start_year: int, end_year: int
) -> Dict[str, Any]:
    """
    Split a query by individual years within a range if it would exceed the limit.

    We break the [start_year, end_year] interval into 5-year blocks for logging only,
    but we actually query year-by-year inside each block (safer vs the 50k row cap).
    """
    year_ranges: List[tuple[int, int]] = []
    current_start = start_year
    while current_start <= end_year:
        current_end = min(current_start + 4, end_year)
        year_ranges.append((current_start, current_end))
        current_start = current_end + 1

    logger.info(
        f"Splitting query by year ranges ({start_year}-{end_year}) "
        f"to avoid 50,000 row limit..."
    )

    all_results: List[Any] = []
    failed_years: List[str] = []

    for year_start, year_end in year_ranges:
        year_filters = dict(filters)
        # Remove year__GE and year__LE, add specific years
        year_filters.pop("year__GE", None)
        year_filters.pop("year__LE", None)
        year_filters.pop("year", None)

        for year in range(year_start, year_end + 1):
            year_filters["year"] = str(year)
            params = dict(year_filters)
            params["format"] = format

            result = await _nass_get("/api_GET/", params=params)
            if result.get("success") and "data" in result:
                data = result["data"]
                if isinstance(data, dict) and "data" in data and isinstance(
                    data["data"], list
                ):
                    all_results.extend(data["data"])
                elif isinstance(data, list):
                    all_results.extend(data)
            else:
                failed_years.append(str(year))

    return {
        "success": True,
        "data": all_results,
        "total_rows": len(all_results),
        "year_range": f"{start_year}-{end_year}",
        "failed_years": failed_years,
        "split_method": "by_year",
        "note": (
            "Query was automatically split by individual years within ranges "
            "to avoid the 50,000 row limit"
        ),
    }


async def nass_api_get(filters: Dict[str, str], format: str = "json") -> Dict[str, Any]:
    """
    Fetch Quick Stats data matching the given filters using the api_GET endpoint.

    QuickStats API uses WHAT/WHERE/WHEN parameters:
    - WHAT: commodity_desc, sector_desc, statisticcat_desc, etc.
    - WHERE: state_alpha, county_name, region_desc, etc.
    - WHEN: year, year__GE (greater than or equal), freq_desc, etc.

    The QuickStats API returns at most 50,000 rows per request.
    If the limit is exceeded, this function automatically splits the query
    by state and/or year.

    NOTE: For STS Voice, this wrapper only supports JSON output.
    'format' must be 'json'.

    Args:
        filters: REQUIRED - Dictionary of Quick Stats query parameters as strings.
                 Must contain at least one parameter.
                 Example: {'commodity_desc': 'CORN', 'year__GE': '2012', 'state_alpha': 'VA'}
        format:  Output format: 'json'. CSV/XML are not supported in this wrapper.

    Returns:
        Dict with 'success', 'data', and optionally 'error' and 'error_code'.
        If query was split, includes 'split_method' and 'note' fields.
    """
    if not filters or not isinstance(filters, dict) or len(filters) == 0:
        return {
            "success": False,
            "error": (
                "filters parameter is required and must contain at least one query parameter. "
                "Example: {'commodity_desc': 'CORN', 'year': '2021'}"
            ),
            "example_filters": {
                "commodity_desc": "CORN",
                "year": "2021",
                "state_alpha": "VA",
            },
        }

    fmt = format.lower()
    if fmt != "json":
        return {
            "success": False,
            "error": "Only 'json' format is supported by this wrapper.",
        }

    # First, check the count to see if we need to split
    count_result = await nass_get_counts(filters)

    needs_splitting = False
    if not count_result.get("success") or count_result.get("error_code") == "ROW_LIMIT_EXCEEDED":
        needs_splitting = True
        logger.warning("Query might exceed 50,000 row limit, attempting to split if needed...")
    elif count_result.get("success") and "data" in count_result:
        count_data = count_result["data"]
        if isinstance(count_data, dict) and "count" in count_data:
            count_value = count_data["count"]
            if isinstance(count_value, (int, str)) and int(count_value) > 45000:
                needs_splitting = True
                logger.warning(
                    f"Query would return ~{count_value} rows, splitting to avoid limit..."
                )

    # Try the query once directly
    params = dict(filters)
    params["format"] = fmt
    result = await _nass_get("/api_GET/", params=params)

    # If limit exceeded, mark for splitting
    if not result.get("success") and result.get("error_code") == "ROW_LIMIT_EXCEEDED":
        needs_splitting = True

    if needs_splitting:
        has_state = "state_alpha" in filters
        has_year_range = "year__GE" in filters or "year__LE" in filters

        # Strategy 1: Split by state if no state filter provided
        if not has_state:
            logger.info("Splitting query by states (no state filter provided)...")
            return await _split_query_by_states(filters, fmt)

        # Strategy 2: Split by year if we have a year range
        elif has_year_range:
            year_ge = int(filters.get("year__GE", "2000"))
            year_le = int(filters.get("year__LE", str(datetime.now().year)))
            if year_le - year_ge > 5:
                logger.info(f"Splitting query by year ranges ({year_ge}-{year_le})...")
                return await _split_query_by_years(filters, fmt, year_ge, year_le)

        # Strategy 3: We have state but still hitting limit; ask caller to refine
        result["suggestion"] = (
            "Query may exceed the 50,000 row limit. Try adding more specific filters: "
            "statisticcat_desc (e.g., 'AREA PLANTED'), "
            "agg_level_desc (e.g., 'STATE' instead of 'COUNTY'), "
            "or a specific year instead of a range."
        )
        result["auto_split_attempted"] = True

    return result


# =========================
# OpenAI Realtime tool spec
# =========================

NASS_TOOLS: List[Dict[str, Any]] = [
    {
        "type": "function",
        "name": "nass_get_param_values",
        "description": (
            "Get all possible values for a NASS Quick Stats parameter (e.g., sector_desc, "
            "commodity_desc, statisticcat_desc, state_alpha). Use this to explore valid options "
            "before forming a detailed query."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "param": {
                    "type": "string",
                    "description": (
                        "Quick Stats parameter name (e.g., 'sector_desc', 'commodity_desc', "
                        "'state_alpha', 'statisticcat_desc')."
                    ),
                }
            },
            "required": ["param"],
        },
    },
    {
        "type": "function",
        "name": "nass_get_counts",
        "description": (
            "Get the number of rows that would be returned by a NASS Quick Stats query for a given "
            "set of filters, without downloading the full data. Use this to check that the result "
            "will not exceed the 50,000 row limit. "
            "REQUIRED: You MUST provide a 'filters' object with at least one parameter. "
            "QuickStats API uses WHAT/WHERE/WHEN parameters: "
            "WHAT: commodity_desc (e.g., 'CORN'), sector_desc, statisticcat_desc; "
            "WHERE: state_alpha (e.g., 'VA'), county_name, region_desc; "
            "WHEN: year (e.g., '2021'), year__GE (year >= value), freq_desc. "
            "Example filters: {'commodity_desc': 'CORN', 'year__GE': '2012', 'state_alpha': 'VA'}. "
            "If the count exceeds 50,000, add more filters (e.g., specific state, county, or year) and try again."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "filters": {
                    "type": "object",
                    "description": (
                        "REQUIRED: Dictionary of Quick Stats query parameters using WHAT/WHERE/WHEN concept. "
                        "Must contain at least one parameter. "
                        "WHAT parameters: commodity_desc (e.g., 'CORN', 'SOYBEANS'), sector_desc (e.g., 'CROPS'), "
                        "statisticcat_desc (e.g., 'AREA PLANTED', 'PRODUCTION'), group_desc, class_desc. "
                        "WHERE parameters: state_alpha (e.g., 'VA', 'CA'), county_name, region_desc, "
                        "agg_level_desc (e.g., 'STATE', 'COUNTY', 'NATIONAL'). "
                        "WHEN parameters: year (e.g., '2021'), year__GE (year >= value, e.g., '2012'), "
                        "year__LE (year <= value), freq_desc (e.g., 'ANNUAL', 'MONTHLY'). "
                        "Examples: "
                        "{'commodity_desc': 'CORN', 'year__GE': '2012', 'state_alpha': 'VA'}, "
                        "{'commodity_desc': 'CORN', 'year': '2021', 'state_alpha': 'VA'}, "
                        "{'sector_desc': 'CROPS', 'commodity_desc': 'CORN', 'year': '2020'}. "
                        "Values must be strings. Use commas to separate multiple values when needed."
                    ),
                    "additionalProperties": {"type": "string"},
                }
            },
            "required": ["filters"],
        },
    },
    {
        "type": "function",
        "name": "nass_api_get",
        "description": (
            "Fetch NASS Quick Stats data using the api_GET endpoint, returning JSON output only. "
            "REQUIRED: You MUST provide a 'filters' object with at least one parameter. "
            "QuickStats API uses WHAT/WHERE/WHEN parameters: "
            "WHAT: commodity_desc (e.g., 'CORN'), sector_desc, statisticcat_desc; "
            "WHERE: state_alpha (e.g., 'VA'), county_name, region_desc; "
            "WHEN: year (e.g., '2021'), year__GE (year >= value), freq_desc. "
            "Example filters: {'commodity_desc': 'CORN', 'year__GE': '2012', 'state_alpha': 'VA'}. "
            "The API returns at most 50,000 rows. If you get a 'ROW_LIMIT_EXCEEDED' error, "
            "this wrapper may automatically split the query by state or year, or you can add more "
            "filters (e.g., specific state, county, or year) and retry the query."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "filters": {
                    "type": "object",
                    "description": (
                        "REQUIRED: Dictionary of Quick Stats query parameters using WHAT/WHERE/WHEN concept. "
                        "Must contain at least one parameter. "
                        "WHAT parameters: commodity_desc (e.g., 'CORN', 'SOYBEANS'), sector_desc (e.g., 'CROPS'), "
                        "statisticcat_desc (e.g., 'AREA PLANTED', 'PRODUCTION'), group_desc, class_desc. "
                        "WHERE parameters: state_alpha (e.g., 'VA', 'CA'), county_name, region_desc, "
                        "agg_level_desc (e.g., 'STATE', 'COUNTY', 'NATIONAL'). "
                        "WHEN parameters: year (e.g., '2021'), year__GE (year >= value, e.g., '2012'), "
                        "year__LE (year <= value), freq_desc (e.g., 'ANNUAL', 'MONTHLY'). "
                        "Examples: "
                        "{'commodity_desc': 'CORN', 'year__GE': '2012', 'state_alpha': 'VA'}, "
                        "{'commodity_desc': 'CORN', 'year': '2021', 'state_alpha': 'VA'}, "
                        "{'sector_desc': 'CROPS', 'commodity_desc': 'CORN', 'year': '2020'}. "
                        "Values must be strings. Use commas to separate multiple values when needed. "
                        "If you get a 50,000 row limit error, add more filters (e.g., state_alpha, county_name, specific year)."
                    ),
                    "additionalProperties": {"type": "string"},
                },
                "format": {
                    "type": "string",
                    "description": (
                        "Output format. Only 'json' is supported by this wrapper for STS Voice."
                    ),
                    "default": "json",
                },
            },
            "required": ["filters"],
        },
    },
]


TOOL_FUNCTIONS: Dict[str, Any] = {
    "nass_get_param_values": nass_get_param_values,
    "nass_get_counts": nass_get_counts,
    "nass_api_get": nass_api_get,
}
