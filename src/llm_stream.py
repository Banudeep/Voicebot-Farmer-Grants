"""
LLM Streaming Module
Streaming text generation using Azure OpenAI Responses API
"""
import asyncio
import json
import random
from pathlib import Path
import config

# Logging
from logging_config import get_logger
logger = get_logger("voicebot.llm")

# Result formatting
from result_formatter import format_tool_result, log_tool_result

# Centralized tool registry
from mcp_tools import get_all_tools, get_all_functions

# HTTP client for Azure OpenAI
try:
    import httpx
    HAS_HTTPX = True
except ImportError:
    HAS_HTTPX = False

# Retry logic for API calls
try:
    from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
    HAS_TENACITY = True
except ImportError:
    HAS_TENACITY = False
    # Fallback: no-op decorator
    def retry(*args, **kwargs):
        def decorator(func):
            return func
        return decorator
    stop_after_attempt = lambda x: None
    wait_exponential = lambda **kwargs: None
    retry_if_exception_type = lambda x: None

class LLMStream:
    """Streaming language model processor"""
    
    def __init__(self):
        # Validate required Azure OpenAI configuration
        if not all([config.AZURE_OPENAI_ENDPOINT, config.AZURE_OPENAI_API_KEY, config.AZURE_OPENAI_DEPLOYMENT]):
            raise ValueError(
                "Azure OpenAI requires AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_API_KEY, "
                "and AZURE_OPENAI_DEPLOYMENT environment variables"
            )
        
        # Store endpoint (clean up trailing slashes)
        self._azure_endpoint = config.AZURE_OPENAI_ENDPOINT.rstrip('/')
        self.model = config.AZURE_OPENAI_DEPLOYMENT
        
        # Responses API: Store reasoning ID for chain-of-thought between turns
        self.reasoning_id = None
        
        if config.DEBUG:
            logger.info("Using Azure OpenAI Responses API")
            logger.info(f"  Deployment: '{config.AZURE_OPENAI_DEPLOYMENT}'")
            logger.info(f"  API Version: {config.AZURE_API_VERSION}")
        
        self.conversation_history = []
        self.system_prompt = config.SYSTEM_PROMPT
        
        # Load tools from centralized registry
        self.all_tools = get_all_tools()
        self.tool_functions = get_all_functions()
        
        if config.DEBUG and self.all_tools:
            logger.info(f"Total tools available: {len(self.all_tools)}")
    
    async def initialize(self):
        """Initialize LLM and tools"""
        if config.DEBUG:
            logger.info("LLM initialized")
            if self.all_tools:
                tool_names = [t.get('function', {}).get('name', t.get('name', 'unknown')) for t in self.all_tools]
                logger.debug(f"Available tools: {', '.join(tool_names)}")
    
    def clear_history(self):
        """Clear the conversation conversation_history"""
        self.conversation_history = []
        # Clear reasoning chain if using Responses API
        self.reasoning_id = None
        if config.DEBUG:
            logger.info("LLM history usage cleared")
    
    async def _get_tools(self):
        """Get available tools in OpenAI format"""
        if not config.ENABLE_TOOLS:
            return []
        return self.all_tools
    
    def _format_tools_for_azure(self, tools):
        """Convert tools format for Azure OpenAI (nested function structure)"""
        if not tools:
            return []
        
        formatted_tools = []
        for tool in tools:
            if "function" in tool:
                formatted_tools.append(tool)
            else:
                formatted_tool = {
                    "type": tool.get("type", "function"),
                    "function": {
                        "name": tool.get("name", ""),
                        "description": tool.get("description", ""),
                        "parameters": tool.get("parameters", {})
                    }
                }
                formatted_tools.append(formatted_tool)
        
        return formatted_tools
    
    def _format_tools_for_responses_api(self, tools):
        """Convert tools to Responses API flat format."""
        if not tools:
            return []
        formatted = []
        for tool in tools:
            if "function" in tool:
                func = tool["function"]
                formatted.append({
                    "type": "function",
                    "name": func.get("name", ""),
                    "description": func.get("description", ""),
                    "parameters": func.get("parameters", {})
                })
            else:
                formatted.append({
                    "type": tool.get("type", "function"),
                    "name": tool.get("name", ""),
                    "description": tool.get("description", ""),
                    "parameters": tool.get("parameters", {})
                })
        return formatted
    
    def _get_filler_phrase(self, tool_name: str) -> str:
        """Get a random filler phrase appropriate for the tool being called.
        Returns varied phrases to sound natural, including simple acknowledgements.
        """
        # Tool-specific filler phrases (randomized)
        tool_fillers = {
            # Price tools
            'get_corn_soybean_prices': [
                "Checking current prices...",
                "Let me look up those prices.",
                "One moment, pulling up prices.",
                "Okay, checking the market data.",
            ],
            'find_state_reports': [
                "Looking up state data...",
                "Let me find that report.",
                "Checking state information.",
            ],
            # Grant/program tools
            'search_agriculture_grants': [
                "Searching available grants...",
                "Let me find some grants for you.",
                "Looking through grant programs.",
            ],
            'search_grants': [
                "Searching grants...",
                "Looking into that for you.",
                "Let me check what's available.",
            ],
            'search_all_programs': [
                "Searching all programs...",
                "Let me look through the programs.",
                "Checking available programs.",
            ],
            'search_farmers_grants': [
                "Looking up farmer programs...",
                "Searching farmer assistance.",
            ],
            'get_grant_details': [
                "Getting those details...",
                "Let me pull up that information.",
                "One moment.",
            ],
            # Stats tools
            'nass_api_get': [
                "Looking up USDA statistics...",
                "Checking the data...",
                "Let me get those numbers.",
            ],
            # Form tools
            'fill_form_field': [
                "Got it.",
                "Okay.",
                "Saving that.",
                "Noted.",
            ],
            'send_form_email': [
                "Sending your form now...",
                "Let me send that off.",
                "Submitting that for you.",
            ],
            'get_form_fields': [
                "Let me get the form ready.",
                "Pulling up the form.",
            ],
            'list_available_forms': [
                "Checking available forms...",
                "Let me see what forms we have.",
            ],
            # Service center / contact tools
            'search_service_center': [
                "Finding your local office...",
                "Looking up service centers.",
                "Let me find that for you.",
            ],
            # News tools
            'search_state_news': [
                "Checking recent news...",
                "Looking up updates.",
            ],
            # Deadline tools
            'get_state_ranking_dates': [
                "Checking deadlines...",
                "Looking up those dates.",
            ],
        }
        
        # Default fillers for unknown tools
        default_fillers = [
            "Let me check on that...",
            "One moment...",
            "Looking into that.",
            "Okay, let me see.",
            "Sure, checking now.",
            "Got it, one second.",
        ]
        
        # Get tool-specific or default fillers
        fillers = tool_fillers.get(tool_name, default_fillers)
        return random.choice(fillers)
    
    async def _execute_tool(self, tool_name: str, arguments: dict) -> str:
        """Execute a tool function directly"""
        if tool_name not in self.tool_functions:
            error_msg = f"Tool '{tool_name}' not found"
            logger.error(error_msg)
            return json.dumps({"error": error_msg})
        
        try:
            tool_func = self.tool_functions[tool_name]
            
            # Validate required arguments by checking function signature
            import inspect
            sig = inspect.signature(tool_func)
            required_params = [p.name for p in sig.parameters.values() 
                             if p.default == inspect.Parameter.empty and p.name != 'self']
            
            missing_params = [p for p in required_params if p not in arguments]
            if missing_params:
                error_msg = f"Tool '{tool_name}' missing required arguments: {', '.join(missing_params)}"
                logger.error(f"{error_msg}. Provided: {list(arguments.keys())}")
                logger.debug(f"Function signature: {sig}")
                return json.dumps({
                    "error": error_msg,
                    "missing_parameters": missing_params,
                    "provided_arguments": list(arguments.keys()),
                    "required_parameters": required_params
                })
            
            # Check if it's an async function
            if asyncio.iscoroutinefunction(tool_func):
                result = await tool_func(**arguments)
            else:
                # Run sync function in executor
                loop = asyncio.get_event_loop()
                result = await loop.run_in_executor(None, lambda: tool_func(**arguments))
            
            # Log tool result using result_formatter
            log_tool_result(tool_name, result)
            
            # Format result for LLM consumption using result_formatter
            return format_tool_result(result)
                
        except TypeError as e:
            error_msg = str(e)
            if "missing" in error_msg.lower() and "required" in error_msg.lower():
                logger.error(f"Tool '{tool_name}' argument error: {error_msg}")
                logger.debug(f"Provided arguments: {arguments}")
                import inspect
                sig = inspect.signature(tool_func)
                return json.dumps({
                    "error": f"Missing required arguments for '{tool_name}': {error_msg}",
                    "provided_arguments": arguments,
                    "function_signature": str(sig)
                })
            else:
                raise
        except Exception as e:
            error_msg = f"Error executing tool '{tool_name}': {str(e)}"
            logger.error(error_msg)
            logger.debug(f"Arguments: {arguments}")
            if config.DEBUG:
                import traceback
                logger.exception("Tool execution traceback")
            return json.dumps({"error": error_msg, "arguments": arguments})
    
    async def _azure_responses_api(self, messages, tools, stream_callback, filler_callback=None):
        """Use Azure OpenAI Responses API (recommended for GPT-5 class models)
        
        Args:
            messages: Conversation messages
            tools: Available tools
            stream_callback: Callback for streaming text (currently unused)
            filler_callback: Async callback to send filler audio before tool execution
        
        Benefits over Chat Completions:
        - Chain-of-thought (CoT) support for better reasoning
        - Reduced reasoning token generation
        - Higher cache hit rates and lower latency
        """
        if not HAS_HTTPX:
            raise RuntimeError("httpx is required for Azure OpenAI. Install with: pip install httpx")
        
        endpoint = config.AZURE_OPENAI_ENDPOINT.rstrip('/')
        # Responses API uses /openai/responses (NOT /openai/deployments/{deployment}/responses)
        url = f"{endpoint}/openai/responses?api-version={config.AZURE_API_VERSION}"
        
        headers = {
            "api-key": config.AZURE_OPENAI_API_KEY,
            "Content-Type": "application/json"
        }
        
        # Convert messages to Responses API input format
        input_items = []
        for msg in messages:
            if msg.get("role") == "system":
                input_items.append({
                    "type": "message",
                    "role": "system",
                    "content": msg.get("content", "")
                })
            elif msg.get("role") == "user":
                input_items.append({
                    "type": "message",
                    "role": "user",
                    "content": msg.get("content", "")
                })
            elif msg.get("role") == "assistant":
                if msg.get("tool_calls"):
                    # Assistant message with tool calls
                    for tc in msg["tool_calls"]:
                        input_items.append({
                            "type": "function_call",
                            "call_id": tc.get("id", ""),
                            "name": tc["function"]["name"],
                            "arguments": tc["function"]["arguments"]
                        })
                elif msg.get("content"):
                    input_items.append({
                        "type": "message",
                        "role": "assistant",
                        "content": msg.get("content", "")
                    })
            elif msg.get("role") == "tool":
                # Tool result
                input_items.append({
                    "type": "function_call_output",
                    "call_id": msg.get("tool_call_id", ""),
                    "output": msg.get("content", "")
                })
        
        payload = {
            "model": config.AZURE_OPENAI_DEPLOYMENT,
            "input": input_items,
            "temperature": config.OPENAI_TEMPERATURE,
            "max_output_tokens": config.OPENAI_MAX_TOKENS
        }
        
        # Add chain-of-thought reasoning if we have a previous reasoning ID
        if self.reasoning_id:
            payload["reasoning"] = {"id": self.reasoning_id}
        
        # Add tools if available
        if tools:
            payload["tools"] = self._format_tools_for_responses_api(tools)
        
        if config.DEBUG:
            logger.debug(f"Responses API URL: {url}")
            logger.debug(f"Model/Deployment: {config.AZURE_OPENAI_DEPLOYMENT}")
            if self.reasoning_id:
                logger.debug(f"Using reasoning chain: {self.reasoning_id[:20]}...")
        
        async with httpx.AsyncClient(timeout=60.0) as client:
            try:
                response = await client.post(url, headers=headers, json=payload)
                response.raise_for_status()
                result = response.json()
                
                # Parse Responses API output format
                response_text = ""
                tool_calls = []
                
                # Store reasoning ID for next turn (chain-of-thought)
                if result.get("reasoning", {}).get("id"):
                    self.reasoning_id = result["reasoning"]["id"]
                    if config.DEBUG:
                        logger.debug("Stored reasoning ID for next turn")
                
                # Process output items
                for item in result.get("output", []):
                    item_type = item.get("type", "")
                    
                    if item_type == "message":
                        # Text response
                        content = item.get("content", [])
                        if isinstance(content, list):
                            for c in content:
                                if c.get("type") == "output_text":
                                    response_text += c.get("text", "")
                        elif isinstance(content, str):
                            response_text += content
                    
                    elif item_type == "function_call":
                        # Tool call
                        tool_calls.append({
                            "id": item.get("call_id", item.get("id", "")),
                            "type": "function",
                            "function": {
                                "name": item.get("name", ""),
                                "arguments": item.get("arguments", "{}")
                            }
                        })
                
                # Handle tool calls
                max_tool_iterations = 10
                iteration = 0
                
                while tool_calls and self.tool_functions and iteration < max_tool_iterations:
                    iteration += 1
                    if config.DEBUG:
                        logger.debug(f"Tool call iteration {iteration}")
                    
                    # Add tool calls to conversation history (in original format for storage)
                    self.conversation_history.append({
                        "role": "assistant",
                        "tool_calls": tool_calls
                    })
                    
                    # Execute each tool and add results
                    new_input_items = list(input_items)  # Start with current input
                    
                    # Add the function calls we just received
                    for tc in tool_calls:
                        new_input_items.append({
                            "type": "function_call",
                            "call_id": tc["id"],
                            "name": tc["function"]["name"],
                            "arguments": tc["function"]["arguments"]
                        })
                    
                    for tc in tool_calls:
                        tool_name = tc["function"]["name"]
                        tool_args = json.loads(tc["function"]["arguments"])
                        
                        # Send filler audio BEFORE tool execution for instant feedback
                        if filler_callback:
                            filler_phrase = self._get_filler_phrase(tool_name)
                            try:
                                await filler_callback(filler_phrase)
                            except Exception as e:
                                logger.warning(f"Filler callback failed: {e}")
                        
                        if config.DEBUG:
                            logger.debug(f"Executing tool: {tool_name} with args: {tool_args}")
                        
                        tool_result = await self._execute_tool(tool_name, tool_args)
                        
                        # Truncate large results
                        MAX_TOOL_CONTENT_SIZE = 8000
                        if isinstance(tool_result, str) and len(tool_result) > MAX_TOOL_CONTENT_SIZE:
                            logger.warning(f"Truncating large tool result ({len(tool_result)} chars)")
                            tool_result = tool_result[:MAX_TOOL_CONTENT_SIZE] + f"\n... [truncated]"
                        
                        # Add to conversation history
                        self.conversation_history.append({
                            "role": "tool",
                            "tool_call_id": tc["id"],
                            "content": tool_result
                        })
                        
                        # Add to input for next API call
                        new_input_items.append({
                            "type": "function_call_output",
                            "call_id": tc["id"],
                            "output": tool_result
                        })
                    
                    # Make next request with tool results
                    next_payload = {
                        "model": config.AZURE_OPENAI_DEPLOYMENT,
                        "input": new_input_items,
                        "temperature": config.OPENAI_TEMPERATURE,
                        "max_output_tokens": config.OPENAI_MAX_TOKENS
                    }
                    
                    if self.reasoning_id:
                        next_payload["reasoning"] = {"id": self.reasoning_id}
                    
                    if tools:
                        next_payload["tools"] = self._format_tools_for_responses_api(tools)
                    
                    next_response = await client.post(url, headers=headers, json=next_payload)
                    next_response.raise_for_status()
                    next_result = next_response.json()
                    
                    # Update reasoning ID
                    if next_result.get("reasoning", {}).get("id"):
                        self.reasoning_id = next_result["reasoning"]["id"]
                    
                    # Parse new response
                    response_text = ""
                    tool_calls = []
                    
                    for item in next_result.get("output", []):
                        item_type = item.get("type", "")
                        
                        if item_type == "message":
                            content = item.get("content", [])
                            if isinstance(content, list):
                                for c in content:
                                    if c.get("type") == "output_text":
                                        response_text += c.get("text", "")
                            elif isinstance(content, str):
                                response_text += content
                        
                        elif item_type == "function_call":
                            tool_calls.append({
                                "id": item.get("call_id", item.get("id", "")),
                                "type": "function",
                                "function": {
                                    "name": item.get("name", ""),
                                    "arguments": item.get("arguments", "{}")
                                }
                            })
                    
                    # Update input_items for potential next iteration
                    input_items = new_input_items
                    
                    if config.DEBUG:
                        if tool_calls:
                            logger.debug(f"LLM wants to make {len(tool_calls)} more tool call(s)")
                        else:
                            logger.debug(f"LLM finished tool calls, response: {response_text[:100] if response_text else '(empty)'}...")
                
                # Ensure we have a response
                if not response_text or not response_text.strip():
                    response_text = "I've retrieved the data but couldn't generate a response. Please try asking again."
                
                # Add final response to history
                self.conversation_history.append({
                    "role": "assistant",
                    "content": response_text
                })
                
                return response_text
                
            except httpx.HTTPStatusError as e:
                error_text = e.response.text if hasattr(e.response, 'text') else str(e)
                logger.error(f"Responses API error: {e.response.status_code}")
                logger.error(f"Error details: {error_text[:500]}")
                logger.debug(f"Request URL: {url}")
                raise
    
    async def generate_response(self, user_message: str, stream_callback=None, filler_callback=None):
        """Generate response with optional streaming and filler audio
        
        Args:
            user_message: The user's message
            stream_callback: Callback for streaming text
            filler_callback: Async callback to send filler audio before tool execution
        """
        # Add user message to history
        self.conversation_history.append({
            "role": "user",
            "content": user_message
        })
        
        # Keep conversation history manageable
        if len(self.conversation_history) > config.MAX_CONVERSATION_HISTORY:
            self.conversation_history = self.conversation_history[-config.MAX_CONVERSATION_HISTORY:]
        
        # Prepare messages
        messages = [
            {"role": "system", "content": self.system_prompt},
            *self.conversation_history
        ]
        
        # Get tools
        tools = await self._get_tools()
        
        try:
            # Use Responses API (httpx required)
            if not HAS_HTTPX:
                raise RuntimeError("httpx is required for Azure OpenAI. Install with: pip install httpx")
            return await self._azure_responses_api(messages, tools, stream_callback, filler_callback)
                
        except Exception as e:
            error_msg = str(e)
            error_details = ""
            status_code = None
            
            # Extract more details from OpenAI library errors
            if hasattr(e, 'status_code'):
                status_code = e.status_code
            elif hasattr(e, 'response') and hasattr(e.response, 'status_code'):
                status_code = e.response.status_code
            
            # Try to extract error body
            if hasattr(e, 'body'):
                try:
                    if isinstance(e.body, dict):
                        error_details = str(e.body)
                    else:
                        error_details = json.loads(e.body) if isinstance(e.body, str) else str(e.body)
                except:
                    error_details = str(e.body)
            elif hasattr(e, 'response') and hasattr(e.response, 'json'):
                try:
                    error_details = e.response.json()
                except:
                    pass
            
            # Format error details
            if error_details:
                if isinstance(error_details, dict):
                    error_details = str(error_details)
                error_details = f"Error code: {status_code} - {error_details}" if status_code else f"Error details: {error_details}"
            elif status_code:
                error_details = f"Error code: {status_code}"
            
            # Print detailed error information
            print(f"❌ LLM error: {error_msg}")
            if error_details:
                print(f"   {error_details}")
            
            return "I encountered an error. Please try asking your question again."
    
    async def generate_response_streaming(self, user_message: str, filler_callback=None, input_mode: str = "voice"):
        """
        Generate response with sentence-level streaming for faster TTS.
        
        Args:
            user_message: The user's message
            filler_callback: Async callback to send filler audio before tool execution.
                           Called with filler phrase text, should synthesize and play audio.
            input_mode: Either 'voice' or 'text' - affects how the LLM responds
        
        Yields:
            tuple: (sentence: str, is_final: bool)
        """
        # Add user message to history
        self.conversation_history.append({
            "role": "user",
            "content": user_message
        })
        
        # Keep conversation history manageable
        if len(self.conversation_history) > config.MAX_CONVERSATION_HISTORY:
            self.conversation_history = self.conversation_history[-config.MAX_CONVERSATION_HISTORY:]
        
        # Add input mode context to system prompt
        mode_hint = ""
        if input_mode == "text":
            mode_hint = "\n\n[USER IS TYPING - Do NOT ask them to spell out names. They are using a keyboard, not voice.]"
        else:
            mode_hint = "\n\n[USER IS SPEAKING - For name fields, ask them to spell out their name letter by letter for accuracy.]"
        
        # Prepare messages with mode-aware system prompt
        messages = [
            {"role": "system", "content": self.system_prompt + mode_hint},
            *self.conversation_history
        ]
        
        # Get tools
        tools = await self._get_tools()
        
        try:
            if not HAS_HTTPX:
                raise RuntimeError("httpx is required for Azure OpenAI")
            
            # Get full response (Azure Responses API doesn't support streaming yet)
            # But we can split it into sentences for incremental TTS
            # Pass filler_callback for instant audio feedback during tool execution
            full_response = await self._azure_responses_api(messages, tools, None, filler_callback)
            
            if not full_response or not isinstance(full_response, str):
                yield ("I'm sorry, I couldn't generate a response.", True)
                return
            
            # Split response into sentences for streaming TTS
            # Use regex to split on sentence boundaries while preserving the punctuation
            import re
            # Pattern matches sentence endings followed by space or end of string
            sentence_pattern = r'(?<=[.!?])\s+'
            sentences = re.split(sentence_pattern, full_response.strip())
            
            # Filter out empty sentences
            sentences = [s.strip() for s in sentences if s.strip()]
            
            if not sentences:
                yield (full_response, True)
                return
            
            # Yield each sentence
            for i, sentence in enumerate(sentences):
                is_final = (i == len(sentences) - 1)
                yield (sentence, is_final)
                
                # Small delay between sentences to allow TTS to catch up
                if not is_final:
                    await asyncio.sleep(0.05)
            
        except Exception as e:
            logger.error(f"LLM streaming error: {e}")
            yield ("I encountered an error. Please try again.", True)
    
    async def cleanup(self):
        """Clean up resources"""
        if config.DEBUG:
            print("🧹 LLM cleaned up")

async def test_llm():
    """Test LLM generation"""
    print("Testing LLM stream...")
    
    llm = LLMStream()
    await llm.initialize()
    
    response = await llm.generate_response("Hello! How are you?")
    print(f"✓ Response: {response}")
    
    await llm.cleanup()
    print("✓ LLM test complete")

if __name__ == "__main__":
    asyncio.run(test_llm())
