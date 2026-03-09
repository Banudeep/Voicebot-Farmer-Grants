"""
MCP Tools Registry - Centralized Tool Registration

Provides a single import point for all tools in the voicebot.
Handles graceful fallback when tool modules are unavailable.
"""

from typing import Dict, Any, List, Callable
import importlib

# Try to import logging (might not be available during initial setup)
try:
    from logging_config import get_logger
    logger = get_logger("voicebot.tools")
except ImportError:
    import logging
    logger = logging.getLogger("voicebot.tools")

# Tool registry
_TOOL_DEFINITIONS: List[Dict[str, Any]] = []
_TOOL_FUNCTIONS: Dict[str, Callable] = {}


def _load_tool_module(module_name: str, tools_var: str, funcs_var: str) -> tuple:
    """Load a tool module and extract tools and functions"""
    try:
        module = importlib.import_module(f"mcp_tools.{module_name}")
        tools = getattr(module, tools_var, [])
        functions = getattr(module, funcs_var, {})
        return tools, functions, True
    except ImportError as e:
        logger.debug(f"Tool module {module_name} not available: {e}")
        return [], {}, False
    except Exception as e:
        logger.warning(f"Error loading {module_name}: {e}")
        return [], {}, False


# Tool module configurations
TOOL_MODULES = [
    ("usda_tools", "USDA_TOOLS", "TOOL_FUNCTIONS", "ENABLE_USDA_TOOLS"),
    ("nass_tools", "NASS_TOOLS", "TOOL_FUNCTIONS", "ENABLE_NASS_TOOLS"),
    ("farmers_grants_tools", "FARMERS_GRANTS_TOOLS", "TOOL_FUNCTIONS", "ENABLE_FARMERS_GRANTS_TOOLS"),
    ("service_center_tools", "SERVICE_CENTER_TOOLS", "SERVICE_CENTER_TOOL_FUNCTIONS", None),
    ("news_tools", "NEWS_TOOLS", "NEWS_TOOL_FUNCTIONS", None),
    ("unified_programs_tools", "UNIFIED_PROGRAMS_TOOLS", "UNIFIED_PROGRAMS_TOOL_FUNCTIONS", None),
    ("form_tools", "FORM_TOOLS", "FORM_TOOL_FUNCTIONS", None),
]


def _is_tool_enabled(env_var: str) -> bool:
    """Check if a tool is enabled via environment variable"""
    if env_var is None:
        return True
    import os
    return os.getenv(env_var, "true").lower() == "true"


def load_all_tools() -> tuple:
    """
    Load all available tools from registered modules.
    
    Returns:
        Tuple of (all_tool_definitions, all_tool_functions)
    """
    global _TOOL_DEFINITIONS, _TOOL_FUNCTIONS
    
    all_tools = []
    all_functions = {}
    
    for module_name, tools_var, funcs_var, enable_var in TOOL_MODULES:
        if not _is_tool_enabled(enable_var):
            logger.debug(f"Tool {module_name} disabled via {enable_var}")
            continue
        
        tools, functions, loaded = _load_tool_module(module_name, tools_var, funcs_var)
        
        if loaded:
            all_tools.extend(tools)
            all_functions.update(functions)
            tool_count = len(tools)
            logger.debug(f"Loaded {tool_count} tools from {module_name}")
    
    _TOOL_DEFINITIONS = all_tools
    _TOOL_FUNCTIONS = all_functions
    
    logger.info(f"Loaded {len(all_tools)} total tools from {len(all_functions)} functions")
    
    return all_tools, all_functions


def get_all_tools() -> List[Dict[str, Any]]:
    """Get all loaded tool definitions"""
    if not _TOOL_DEFINITIONS:
        load_all_tools()
    return _TOOL_DEFINITIONS


def get_all_functions() -> Dict[str, Callable]:
    """Get all loaded tool functions"""
    if not _TOOL_FUNCTIONS:
        load_all_tools()
    return _TOOL_FUNCTIONS


def get_tool_function(name: str) -> Callable:
    """Get a specific tool function by name"""
    functions = get_all_functions()
    return functions.get(name)


def register_tool(tool_def: Dict[str, Any], func: Callable):
    """
    Register a custom tool at runtime.
    
    Args:
        tool_def: OpenAI function tool definition
        func: The callable function
    """
    global _TOOL_DEFINITIONS, _TOOL_FUNCTIONS
    
    # Extract function name
    if "function" in tool_def:
        name = tool_def["function"]["name"]
    else:
        name = tool_def.get("name", func.__name__)
    
    _TOOL_DEFINITIONS.append(tool_def)
    _TOOL_FUNCTIONS[name] = func
    logger.info(f"Registered custom tool: {name}")


def list_tools() -> List[str]:
    """List all available tool names"""
    tools = get_all_tools()
    names = []
    for tool in tools:
        if "function" in tool:
            names.append(tool["function"]["name"])
        else:
            names.append(tool.get("name", "unknown"))
    return names


# Auto-load tools on import
try:
    load_all_tools()
except Exception as e:
    logger.warning(f"Failed to auto-load tools: {e}")


if __name__ == "__main__":
    print(f"Loaded tools: {list_tools()}")
    print(f"Total: {len(get_all_tools())} tools")
