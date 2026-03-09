"""
Unified USDA Programs Search Tool

Searches all 139 USDA programs from FSA, RD, and Program Deadlines with a single tool call.
Data sources:
  - cache/fsa_programs_comprehensive.json (46 programs)
  - cache/rd_programs_comprehensive.json (77 programs)  
  - cache/program_deadlines_comprehensive.json (16 programs)
"""

from typing import Dict, Any, List, Optional

from mcp_tools.utils import (
    CACHE_DIR,
    SERVICE_CENTER_LOCATOR_URL,
    get_tool_logger,
    load_json_cache,
    truncate_summary,
)

logger = get_tool_logger("voicebot.tools.programs")

# Data paths
FSA_DATA_PATH = CACHE_DIR / "fsa_programs_comprehensive.json"
RD_DATA_PATH = CACHE_DIR / "rd_programs_comprehensive.json"
DEADLINES_DATA_PATH = CACHE_DIR / "program_deadlines_comprehensive.json"

# Source configurations: (path, source_code, source_full, field_map)
# field_map keys: name, url, description, summary_field, deadline
_SOURCES = [
    {
        "path": FSA_DATA_PATH,
        "source": "FSA",
        "source_full": "Farm Service Agency",
        "name_keys": ["title", "detail_title"],
        "url_key": "url",
        "desc_key": "full_description",
        "summary_key": "full_description",
        "deadline_key": "important_dates",
    },
    {
        "path": RD_DATA_PATH,
        "source": "RD",
        "source_full": "Rural Development",
        "name_keys": ["title", "detail_title"],
        "url_key": "url",
        "desc_key": "full_description",
        "summary_key": "full_description",
        "deadline_key": None,
    },
    {
        "path": DEADLINES_DATA_PATH,
        "source": "Deadline",
        "source_full": "Active Program Deadline",
        "name_keys": ["program_name", "name"],
        "url_key": "url",
        "url_fallback": "detail_url",
        "desc_key": "detailed_description",
        "desc_fallback": "description",
        "summary_key": "description",
        "deadline_key": "deadline",
        "deadline_fallback": "application_deadline",
    },
]

# Cache for loaded data
_all_programs: List[Dict] = []
_programs_by_name: Dict[str, Dict] = {}


def _load_all_programs() -> List[Dict]:
    """Load and merge all program data from FSA, RD, and Deadlines sources."""
    global _all_programs, _programs_by_name
    
    if _all_programs:
        return _all_programs
    
    programs = []
    
    for src_cfg in _SOURCES:
        raw_data = load_json_cache(src_cfg["path"], fallback=[])
        # Handle wrapper object structure {"programs": [...]}
        if isinstance(raw_data, dict) and "programs" in raw_data:
            raw_data = raw_data["programs"]
        if not isinstance(raw_data, list):
            continue

        try:
            for program in raw_data:
                # Resolve name from prioritized keys
                name = ""
                for k in src_cfg["name_keys"]:
                    name = program.get(k, "")
                    if name:
                        break

                desc = program.get(src_cfg["desc_key"], "")
                if not desc and "desc_fallback" in src_cfg:
                    desc = program.get(src_cfg["desc_fallback"], "")

                url = program.get(src_cfg["url_key"], "")
                if not url and "url_fallback" in src_cfg:
                    url = program.get(src_cfg["url_fallback"], "")

                summary_text = program.get(src_cfg["summary_key"], "")

                deadline = None
                if src_cfg.get("deadline_key"):
                    deadline = program.get(src_cfg["deadline_key"])
                    if not deadline and "deadline_fallback" in src_cfg:
                        deadline = program.get(src_cfg["deadline_fallback"])

                programs.append({
                    "name": name,
                    "source": src_cfg["source"],
                    "source_full": src_cfg["source_full"],
                    "url": url,
                    "description": desc,
                    "summary": truncate_summary(summary_text),
                    "deadline": deadline,
                    "raw_data": program,
                })
        except Exception as e:
            logger.warning(f"Could not load {src_cfg['source']} programs: {e}")
    
    _all_programs = programs
    
    # Build name lookup
    for p in programs:
        name_key = p["name"].lower().strip()
        _programs_by_name[name_key] = p
    
    logger.info(f"Loaded {len(programs)} unified programs (FSA + RD + Deadlines)")
    return programs


def _score_match(program: Dict, query_terms: List[str]) -> float:
    """Score how well a program matches the query terms."""
    score = 0.0
    name = program.get("name", "").lower()
    description = program.get("description", "").lower()
    source = program.get("source", "").lower()
    
    for term in query_terms:
        term = term.lower()
        
        # Exact match in name (highest weight)
        if term in name:
            score += 10.0
            if name.startswith(term):
                score += 5.0
        
        # Match in description
        if term in description:
            # Count occurrences
            count = description.count(term)
            score += min(count * 1.0, 5.0)  # Cap at 5 points
        
        # Source match (if user mentions FSA, RD, etc.)
        if term in source or term in program.get("source_full", "").lower():
            score += 3.0
    
    # Bonus for programs with active deadlines
    if program.get("deadline"):
        score += 2.0
    
    return score


async def search_all_programs(
    query: str,
    limit: int = 10,
    source_filter: Optional[str] = None
) -> Dict[str, Any]:
    """
    Search all USDA programs (FSA, RD, and active deadlines) with a single query.
    
    Args:
        query: Natural language search query (e.g., "milk contamination", "emergency farm loan", "rural business grants")
        limit: Maximum number of results to return (default: 10)
        source_filter: Optional filter by source ("FSA", "RD", or "Deadline")
    
    Returns:
        Dictionary with matching programs from all sources, sorted by relevance.
    """
    programs = _load_all_programs()
    
    if not programs:
        return {
            "success": False,
            "error": "No program data available. Please check cache files.",
            "results": []
        }
    
    # Parse query into terms
    query_terms = [term.strip() for term in query.lower().split() if len(term.strip()) > 2]
    
    # Also add original query as a phrase
    query_terms.append(query.lower())
    
    # Score all programs
    scored_programs = []
    for program in programs:
        # Apply source filter if specified
        if source_filter:
            if program["source"].lower() != source_filter.lower():
                continue
        
        score = _score_match(program, query_terms)
        if score > 0:
            scored_programs.append((score, program))
    
    # Sort by score descending
    scored_programs.sort(key=lambda x: x[0], reverse=True)
    
    # Take top results
    top_results = scored_programs[:limit]
    
    # Format results
    results = []
    for score, program in top_results:
        result = {
            "name": program["name"],
            "source": program["source"],
            "source_full": program["source_full"],
            "url": program["url"],
            "summary": program["summary"],
            "relevance_score": round(score, 2)
        }
        if program.get("deadline"):
            result["deadline"] = program["deadline"]
        results.append(result)
    
    # Group by source for summary
    sources_found = {}
    for _, p in scored_programs:
        src = p["source"]
        sources_found[src] = sources_found.get(src, 0) + 1
    
    return {
        "success": True,
        "query": query,
        "total_matches": len(scored_programs),
        "showing": len(results),
        "sources_searched": {
            "FSA": len([p for p in programs if p["source"] == "FSA"]),
            "RD": len([p for p in programs if p["source"] == "RD"]),
            "Deadline": len([p for p in programs if p["source"] == "Deadline"])
        },
        "matches_by_source": sources_found,
        "results": results,
        "service_center_locator": SERVICE_CENTER_LOCATOR_URL
    }


async def get_program_details(
    program_name: str
) -> Dict[str, Any]:
    """
    Get full details for a specific USDA program.
    
    Args:
        program_name: Name of the program (e.g., "Emergency Farm Loans", "Value-Added Producer Grants")
    
    Returns:
        Dictionary with complete program details including eligibility, funding, and application info.
    """
    programs = _load_all_programs()
    
    # Normalize search
    search_name = program_name.lower().strip()
    
    # Try exact match first
    if search_name in _programs_by_name:
        program = _programs_by_name[search_name]
        return {
            "success": True,
            "program": {
                "name": program["name"],
                "source": program["source"],
                "source_full": program["source_full"],
                "url": program["url"],
                "full_description": program["description"],
                "deadline": program.get("deadline"),
                "raw_data": program.get("raw_data", {})
            },
            "service_center_locator": SERVICE_CENTER_LOCATOR_URL
        }
    
    # Try partial match
    best_match = None
    best_score = 0
    for name_key, program in _programs_by_name.items():
        if search_name in name_key or name_key in search_name:
            score = len(set(search_name.split()) & set(name_key.split()))
            if score > best_score:
                best_score = score
                best_match = program
    
    if best_match:
        return {
            "success": True,
            "program": {
                "name": best_match["name"],
                "source": best_match["source"],
                "source_full": best_match["source_full"],
                "url": best_match["url"],
                "full_description": best_match["description"],
                "deadline": best_match.get("deadline"),
                "raw_data": best_match.get("raw_data", {})
            },
            "note": f"Partial match for '{program_name}'",
            "service_center_locator": SERVICE_CENTER_LOCATOR_URL
        }
    
    return {
        "success": False,
        "error": f"Program '{program_name}' not found.",
        "suggestion": "Try using search_all_programs to find the correct program name.",
        "service_center_locator": SERVICE_CENTER_LOCATOR_URL
    }


# Tool definitions for OpenAI function calling
UNIFIED_PROGRAMS_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_all_programs",
            "description": "Search all 139 USDA programs from FSA (loans, disaster, conservation), Rural Development (business, housing, infrastructure), and active program deadlines. Use this for ANY program-related question. Returns ranked results from all sources.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Natural language search query (e.g., 'milk contamination', 'emergency farm loan', 'rural business grants', 'conservation programs')"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of results to return (default: 10)",
                        "default": 10
                    },
                    "source_filter": {
                        "type": "string",
                        "enum": ["FSA", "RD", "Deadline"],
                        "description": "Optional: filter results to a specific source"
                    }
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_program_details",
            "description": "Get complete details for a specific USDA program including eligibility, funding amounts, and application process. Use after search_all_programs to get full information.",
            "parameters": {
                "type": "object",
                "properties": {
                    "program_name": {
                        "type": "string",
                        "description": "Exact or partial name of the program (e.g., 'Emergency Farm Loans', 'Value-Added Producer Grants')"
                    }
                },
                "required": ["program_name"]
            }
        }
    }
]

UNIFIED_PROGRAMS_TOOL_FUNCTIONS = {
    "search_all_programs": search_all_programs,
    "get_program_details": get_program_details
}
