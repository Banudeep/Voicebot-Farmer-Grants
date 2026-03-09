"""
Result Formatter for USDA Voicebot

Handles formatting and truncation of tool results for LLM consumption.
Extracted from llm_stream.py for better modularity.
"""

import json
from typing import Any, Dict, List, Union

from logging_config import get_logger

logger = get_logger("voicebot.formatter")

# Configuration
MAX_TOOL_RESULT_SIZE = 10000  # Max characters for tool result in conversation
MAX_LIST_SAMPLE_SIZE = 3      # Number of list items to include in summary
MAX_DICT_KEYS_PREVIEW = 20    # Max dict keys to show in summary
MAX_VALUE_PREVIEW_LEN = 200   # Max length for individual value previews


def truncate_string(s: str, max_length: int = MAX_TOOL_RESULT_SIZE) -> str:
    """Truncate a string with informative suffix"""
    if len(s) <= max_length:
        return s
    return s[:max_length] + f"\n... [truncated, original length: {len(s)} chars]"


def summarize_dict(data: Dict[str, Any]) -> Dict[str, Any]:
    """Create a summary of a large dictionary"""
    summary = {
        "success": data.get("success", True),
        "summary": "Result too large to include fully. Key information:",
    }
    
    # Preserve error info
    if "error" in data:
        summary["error"] = data["error"]
    if "error_code" in data:
        summary["error_code"] = data["error_code"]
    if "suggestion" in data:
        summary["suggestion"] = data["suggestion"]
    
    # Summarize data field
    if "data" in data:
        nested_data = data["data"]
        if isinstance(nested_data, list):
            summary["data_summary"] = {
                "type": "list",
                "count": len(nested_data),
            }
            if nested_data:
                if isinstance(nested_data[0], dict):
                    sample_size = min(MAX_LIST_SAMPLE_SIZE, len(nested_data))
                    summary["data_sample"] = nested_data[:sample_size]
                else:
                    summary["data_sample"] = str(nested_data[0])[:500]
        elif isinstance(nested_data, dict):
            summary["data_summary"] = {
                "type": "dict",
                "keys": list(nested_data.keys())[:MAX_DICT_KEYS_PREVIEW],
                "sample_values": {
                    k: str(v)[:MAX_VALUE_PREVIEW_LEN] 
                    for k, v in list(nested_data.items())[:5]
                }
            }
        else:
            summary["data_summary"] = {
                "type": type(nested_data).__name__,
                "preview": str(nested_data)[:500]
            }
    
    # Preserve important metadata fields
    for key in ["endpoint", "params", "total_reports", "matches_found", 
                "total_matches", "showing", "query"]:
        if key in data:
            summary[key] = data[key]
    
    return summary


def summarize_list(data: List[Any]) -> Dict[str, Any]:
    """Create a summary of a large list"""
    return {
        "summary": f"List with {len(data)} items",
        "count": len(data),
        "sample": data[0] if data else None,
        "first_items": data[:10] if len(data) > 10 else data
    }


def format_tool_result(result: Any) -> str:
    """
    Format a tool result for inclusion in LLM conversation.
    
    Handles:
    - Dict results (with potential summarization)
    - List results (with sampling)
    - String results (with truncation)
    - Other types (JSON serialization)
    
    Args:
        result: The raw tool result
    
    Returns:
        JSON string suitable for LLM consumption
    """
    try:
        if isinstance(result, dict):
            result_json = json.dumps(result, default=str)
            
            if len(result_json) > MAX_TOOL_RESULT_SIZE:
                logger.debug(f"Tool result large ({len(result_json)} chars), summarizing...")
                summary = summarize_dict(result)
                result_json = json.dumps(summary, default=str)
                logger.debug(f"Created summary ({len(result_json)} chars)")
            
            return result_json
        
        elif isinstance(result, list):
            result_json = json.dumps(result, default=str)
            
            if len(result_json) > MAX_TOOL_RESULT_SIZE:
                logger.debug(f"List result large ({len(result_json)} chars), summarizing...")
                summary = summarize_list(result)
                result_json = json.dumps(summary, default=str)
                logger.debug(f"Created summary ({len(result_json)} chars)")
            
            return result_json
        
        elif isinstance(result, str):
            if len(result) > MAX_TOOL_RESULT_SIZE:
                logger.debug(f"String result large ({len(result)} chars), truncating...")
                return truncate_string(result)
            return result
        
        else:
            return json.dumps({"result": str(result)}, default=str)
    
    except Exception as e:
        logger.error(f"Error formatting result: {e}")
        return json.dumps({"error": f"Failed to format result: {str(e)}"})


def format_for_debug(result: Any, max_length: int = 4000) -> str:
    """
    Format a tool result for debug logging.
    
    Args:
        result: The raw tool result
        max_length: Maximum length for the formatted output
    
    Returns:
        Human-readable string for logging
    """
    try:
        if isinstance(result, (dict, list)):
            formatted = json.dumps(result, indent=2, default=str)
        else:
            formatted = str(result)
        
        if len(formatted) > max_length:
            return formatted[:max_length] + f"...\n[{len(formatted) - max_length} more chars]"
        return formatted
    
    except Exception as e:
        return f"[Error formatting: {e}]"


def log_tool_result(tool_name: str, result: Any):
    """Log tool result with appropriate formatting"""
    logger.info(f"{'=' * 60}")
    logger.info(f"TOOL RESULT: {tool_name}")
    logger.info(f"{'=' * 60}")
    
    if isinstance(result, dict):
        if result.get("success"):
            logger.info("Tool execution successful")
        else:
            logger.warning(f"Tool failed: {result.get('error', 'Unknown error')}")
    
    logger.debug(f"Full result:\n{format_for_debug(result)}")
    logger.info(f"{'=' * 60}")


if __name__ == "__main__":
    # Test formatting
    test_data = {
        "success": True,
        "data": [{"id": i, "name": f"Item {i}"} for i in range(100)],
        "total_matches": 100,
        "query": "test query"
    }
    
    result = format_tool_result(test_data)
    print(f"Formatted result length: {len(result)}")
    print(f"Result preview: {result[:500]}...")
    print("Result formatter test complete")
