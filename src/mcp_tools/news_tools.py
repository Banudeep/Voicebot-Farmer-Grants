"""
State News Search Tool for USDA Voicebot

Provides HYBRID search over state news articles:
1. Fast filtering by state/agency (direct lookup)
2. Optional RAG semantic search for content matching

Data source: cache/state_news_deep.json + cache/state_news_index.json (if RAG enabled)
"""

import json
from pathlib import Path
from typing import Dict, Any, Optional, List
import re

# Logging
try:
    from logging_config import get_logger
    logger = get_logger("voicebot.tools.news")
except ImportError:
    import logging
    logger = logging.getLogger("voicebot.tools.news")

# Optional dependencies for RAG search
HAS_OPENAI = False
HAS_NUMPY = False

try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    np = None

try:
    from openai import OpenAI
    HAS_OPENAI = True
except ImportError:
    OpenAI = None

# Paths
# Path: src/mcp_tools/news_tools.py -> src/mcp_tools -> src -> root
BASE_DIR = Path(__file__).parent.parent.parent
CACHE_DIR = BASE_DIR / "cache"
NEWS_DATA_PATH = CACHE_DIR / "state_news_deep.json"
NEWS_INDEX_PATH = CACHE_DIR / "state_news_index.json"
COUNTY_DB_PATH = CACHE_DIR / "us_counties.json"

# Embedding model
EMBED_MODEL = "text-embedding-3-small"

# Cached data
_NEWS_CACHE: Optional[Dict] = None
_NEWS_INDEX_CACHE: Optional[Dict] = None
_COUNTY_DB_CACHE: Optional[Dict] = None


def _load_news_data() -> Dict[str, Any]:
    """Load and cache news data"""
    global _NEWS_CACHE
    if _NEWS_CACHE is None:
        if NEWS_DATA_PATH.exists():
            with NEWS_DATA_PATH.open("r", encoding="utf-8") as f:
                _NEWS_CACHE = json.load(f)
        else:
            _NEWS_CACHE = {"states": {}}
    return _NEWS_CACHE


def _load_news_index() -> Dict[str, Any]:
    """Load RAG index if available"""
    global _NEWS_INDEX_CACHE
    if _NEWS_INDEX_CACHE is None:
        if NEWS_INDEX_PATH.exists():
            with NEWS_INDEX_PATH.open("r", encoding="utf-8") as f:
                _NEWS_INDEX_CACHE = json.load(f)
        else:
            _NEWS_INDEX_CACHE = {"chunks": []}
    return _NEWS_INDEX_CACHE


def _load_county_db() -> Dict[str, Any]:
    """Load county database for state name lookups"""
    global _COUNTY_DB_CACHE
    if _COUNTY_DB_CACHE is None:
        if COUNTY_DB_PATH.exists():
            with COUNTY_DB_PATH.open("r", encoding="utf-8") as f:
                _COUNTY_DB_CACHE = json.load(f)
        else:
            _COUNTY_DB_CACHE = {"states": {}}
    return _COUNTY_DB_CACHE


def _normalize_state(state_input: str, county_db: Dict) -> Optional[str]:
    """Convert state name to 2-letter code"""
    state_upper = state_input.upper().strip()
    if state_upper in county_db.get('states', {}):
        return state_upper
    
    state_lower = state_input.lower().strip()
    for code, info in county_db.get('states', {}).items():
        if info.get('name', '').lower() == state_lower:
            return code
    return None


def _cosine_similarity(a: List[float], b: List[float]) -> float:
    """Calculate cosine similarity"""
    if not HAS_NUMPY:
        # Simple fallback without numpy
        dot_product = sum(x * y for x, y in zip(a, b))
        norm_a = sum(x * x for x in a) ** 0.5
        norm_b = sum(x * x for x in b) ** 0.5
        return dot_product / (norm_a * norm_b + 1e-9)
    
    a_arr = np.array(a)
    b_arr = np.array(b)
    return float(np.dot(a_arr, b_arr) / (np.linalg.norm(a_arr) * np.linalg.norm(b_arr) + 1e-9))


def _keyword_search(news_items: List[Dict], query: str) -> List[Dict]:
    """Simple keyword-based search with scoring"""
    query_terms = set(query.lower().split())
    scored = []
    
    for item in news_items:
        # Build searchable text
        text = " ".join([
            item.get("headline", ""),
            item.get("summary", ""),
            item.get("full_text", "")[:1000]  # Limit full text for speed
        ]).lower()
        
        # Count matching terms
        score = sum(1 for term in query_terms if term in text and len(term) > 2)
        if score > 0:
            scored.append((score, item))
    
    # Sort by score descending
    scored.sort(key=lambda x: x[0], reverse=True)
    return [item for score, item in scored]


def _rag_search(query: str, state_filter: Optional[str] = None, top_k: int = 5) -> List[Dict]:
    """Semantic search using RAG embeddings"""
    if not HAS_OPENAI:
        return []
    
    import os
    api_key = os.getenv("AZURE_OPENAI_API_KEY")
    endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
    
    if not api_key or not endpoint:
        return []
    
    index = _load_news_index()
    chunks = index.get("chunks", [])
    if not chunks or not chunks[0].get("embedding"):
        return []
    
    # Use Azure OpenAI for embeddings
    try:
        from openai import AzureOpenAI
        
        # Get API version from environment or use default
        api_version = os.getenv("AZURE_API_VERSION", "2025-04-01-preview")
        
        # Use text-embedding-ada-002 for Azure (common deployment name)
        embed_deployment = os.getenv("AZURE_EMBEDDING_DEPLOYMENT", "text-embedding-ada-002")
        
        client = AzureOpenAI(
            api_key=api_key,
            api_version=api_version,
            azure_endpoint=endpoint
        )
        response = client.embeddings.create(model=embed_deployment, input=[query])
        query_embedding = response.data[0].embedding
    except Exception as e:
        # Log RAG fallback for debugging
        logger.warning(f"Azure embedding failed, falling back to keyword search: {e}")
        return []
    
    # Calculate similarities
    similarities = []
    for chunk in chunks:
        if state_filter and chunk.get("state_code") != state_filter:
            continue
        
        if chunk.get("embedding"):
            sim = _cosine_similarity(query_embedding, chunk["embedding"])
            similarities.append((sim, chunk))
    
    similarities.sort(key=lambda x: x[0], reverse=True)
    return [chunk for sim, chunk in similarities[:top_k]]


async def search_state_news(
    query: str,
    state: Optional[str] = None,
    agency: Optional[str] = None,
    use_rag: bool = True,
    limit: int = 5
) -> Dict[str, Any]:
    """
    Search USDA state news articles.
    
    Args:
        query: Search query (e.g., "conservation funding", "EQIP deadline")
        state: Optional state name or code to filter by
        agency: Optional agency filter ("FSA", "NRCS", "RD")
        use_rag: Whether to use semantic search (slower but more accurate)
        limit: Maximum results to return
    
    Returns:
        Dictionary with matching news articles
    """
    try:
        news_data = _load_news_data()
        county_db = _load_county_db()
        
        # Normalize state if provided
        state_code = None
        if state:
            state_code = _normalize_state(state, county_db)
            if not state_code:
                return {
                    "success": False,
                    "error": f"State '{state}' not recognized."
                }
        
        # Collect articles to search
        all_articles = []
        states_to_search = [state_code] if state_code else list(news_data.get("states", {}).keys())
        
        for sc in states_to_search:
            state_data = news_data.get("states", {}).get(sc, {})
            for item in state_data.get("news_items", []):
                # Apply agency filter
                if agency:
                    item_category = item.get("category", "").upper()
                    if agency.upper() not in item_category:
                        continue
                
                # Add state code to item for context
                item_copy = item.copy()
                item_copy["state_code"] = sc
                item_copy["state_name"] = state_data.get("state_name", sc)
                all_articles.append(item_copy)
        
        if not all_articles:
            return {
                "success": True,
                "results": [],
                "message": f"No news articles found" + (f" for {state}" if state else "") + (f" from {agency}" if agency else "")
            }
        
        # Search strategy: try RAG first, fall back to keyword
        results = []
        if use_rag and HAS_OPENAI:
            rag_results = _rag_search(query, state_filter=state_code, top_k=limit)
            if rag_results:
                # Match RAG chunks back to full articles
                for chunk in rag_results:
                    matching = [a for a in all_articles if a.get("url") == chunk.get("url")]
                    if matching:
                        results.append(matching[0])
        
        # Fall back to keyword search if RAG returned nothing
        if not results:
            results = _keyword_search(all_articles, query)[:limit]
        
        # Format results
        formatted = []
        for r in results[:limit]:
            formatted.append({
                "headline": r.get("headline", r.get("title", "")),
                "date": r.get("date", r.get("listing_date", "")),
                "state": r.get("state_name", r.get("state_code", "")),
                "agency": r.get("category", ""),
                "summary": r.get("summary", "")[:500],
                "url": r.get("url", "")
            })
        
        return {
            "success": True,
            "results": formatted,
            "total_found": len(results),
            "query": query,
            "filters": {"state": state_code, "agency": agency},
            "message": f"Found {len(formatted)} news article(s)."
        }
    
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }


# Tool definition for LLM integration
SEARCH_STATE_NEWS_TOOL = {
    "type": "function",
    "function": {
        "name": "search_state_news",
        "description": "Search USDA state news for recent announcements, deadlines, programs, and success stories. Good for questions about current events, program updates, conservation news, and state-specific USDA activities.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query (e.g., 'conservation funding', 'EQIP deadline', 'farm bill news')"
                },
                "state": {
                    "type": "string",
                    "description": "Optional: State name or code to filter news (e.g., 'Iowa', 'TX')"
                },
                "agency": {
                    "type": "string",
                    "description": "Optional: Filter by agency",
                    "enum": ["FSA", "NRCS", "RD"]
                }
            },
            "required": ["query"]
        }
    }
}

# Export for integration
NEWS_TOOLS = [SEARCH_STATE_NEWS_TOOL]
NEWS_TOOL_FUNCTIONS = {"search_state_news": search_state_news}


# Test
if __name__ == "__main__":
    import asyncio
    
    async def test():
        print("=" * 60)
        print("Testing search_state_news (Hybrid Search)")
        print("=" * 60)
        
        # Test 1: State-filtered search
        print("\n1. Iowa conservation news:")
        result = await search_state_news("conservation funding", state="Iowa")
        if result.get("success") and result.get("results"):
            for r in result["results"][:3]:
                print(f"   • {r['headline'][:60]}...")
                print(f"     {r['date']} | {r['agency']}")
        else:
            print(f"   {result.get('message') or result.get('error')}")
        
        # Test 2: Agency-filtered search
        print("\n2. NRCS news nationwide:")
        result = await search_state_news("EQIP program", agency="NRCS")
        print(f"   Found: {result.get('total_found', 0)} articles")
        
        # Test 3: General search
        print("\n3. Regenerative farming news:")
        result = await search_state_news("regenerative farming")
        if result.get("results"):
            r = result["results"][0]
            print(f"   Top result: {r['headline'][:50]}...")
            print(f"   Summary: {r['summary'][:150]}...")
        
        print("\n" + "=" * 60)
        print("✅ Tests complete!")
    
    asyncio.run(test())
