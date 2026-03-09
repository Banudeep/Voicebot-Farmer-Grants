"""
Shared utilities for MCP tool modules.

Centralises helpers that were duplicated across service_center_tools,
news_tools, and unified_programs_tools.
"""

import json
from pathlib import Path
from typing import Any, Dict, Optional


# ── Paths ────────────────────────────────────────────────────────────────────
# Every tool module used the same three-level parent traversal to find root.
BASE_DIR = Path(__file__).parent.parent.parent
CACHE_DIR = BASE_DIR / "cache"

# ── Shared constants ────────────────────────────────────────────────────────
SERVICE_CENTER_LOCATOR_URL = (
    "https://www.farmers.gov/working-with-us/service-center-locator"
)

AGENCY_NAMES: Dict[str, str] = {
    "FSA": "Farm Service Agency",
    "NRCS": "Natural Resources Conservation Service",
    "RD": "Rural Development",
}

SUMMARY_MAX_LENGTH = 300


# ── Logging helper ───────────────────────────────────────────────────────────
def get_tool_logger(name: str):
    """Return a logger using the project's logging_config.get_tool_logger.

    Falls back to stdlib logging when logging_config is unavailable (e.g.
    during standalone script execution).
    """
    try:
        from logging_config import get_tool_logger as _get_tool_logger
        return _get_tool_logger(name)
    except ImportError:
        import logging
        return logging.getLogger(name)


# ── Generic JSON cache loader ───────────────────────────────────────────────
def load_json_cache(
    path: Path,
    fallback: Optional[Any] = None,
) -> Any:
    """Load a JSON file with a single-line fallback on missing / corrupt data.

    Parameters
    ----------
    path : Path
        Absolute or relative path to the JSON file.
    fallback : Any, optional
        Value returned when the file does not exist or cannot be parsed.
        Defaults to an empty dict ``{}``.
    """
    if fallback is None:
        fallback = {}
    if path.exists():
        try:
            with path.open("r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return fallback
    return fallback


# ── County DB (shared between service_center_tools & news_tools) ────────────
COUNTY_DB_PATH = CACHE_DIR / "us_counties.json"
_COUNTY_DB_CACHE: Optional[Dict] = None


def load_county_db() -> Dict[str, Any]:
    """Load and cache the county database (``us_counties.json``)."""
    global _COUNTY_DB_CACHE
    if _COUNTY_DB_CACHE is None:
        _COUNTY_DB_CACHE = load_json_cache(
            COUNTY_DB_PATH,
            fallback={"states": {}, "counties_by_state": {}},
        )
    return _COUNTY_DB_CACHE


def normalize_state(state_input: str, county_db: Optional[Dict] = None) -> Optional[str]:
    """Convert a state name or abbreviation to its standard 2-letter code.

    If *county_db* is ``None`` the shared county DB is loaded automatically.
    """
    if county_db is None:
        county_db = load_county_db()

    state_upper = state_input.upper().strip()
    if state_upper in county_db.get("states", {}):
        return state_upper

    state_lower = state_input.lower().strip()
    for code, info in county_db.get("states", {}).items():
        if info.get("name", "").lower() == state_lower:
            return code

    return None


# ── Text helpers ─────────────────────────────────────────────────────────────
def truncate_summary(text: str, max_length: int = SUMMARY_MAX_LENGTH) -> str:
    """Return *text* truncated to *max_length* with an ellipsis when needed."""
    if not text:
        return ""
    if len(text) <= max_length:
        return text
    return text[:max_length] + "..."
