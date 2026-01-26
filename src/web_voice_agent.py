"""
Web-Based Voice Agent
Uses browser for audio capture (more reliable than PyAudio)
"""
import asyncio
import json
import base64
import wave
import struct
import uuid
from datetime import datetime
from pathlib import Path
from aiohttp import web
from websockets.server import serve
from websockets.exceptions import ConnectionClosed

from llm_stream import LLMStream
from stt_stream import STTStream
from tts_stream import TTSStream
from blob_storage import get_blob_logger
from mcp_tools.form_tools import get_active_form_state, cleanup_session_files
import config

class WebVoiceAgent:
    """Voice agent with web-based audio capture"""
    
    def __init__(self):
        self.llm = LLMStream()
        self.stt = STTStream()
        self.tts = TTSStream()
        self.active_connections = set()
        self.greeted_connections = set()
        self.last_transcript = None
        self.last_processed_time = 0  # Track when we last PROCESSED a message
        self.current_speech = ""
        self.last_transcript_time = None
        self.is_processing = False
        self.current_processing_task = None
        self.asked_to_repeat = False  # Track if we've already asked to repeat
        self.processed_texts = []  # Track ALL processed texts to strip from cumulative transcripts
        # Audio recording storage: map websocket to list of audio chunks
        self.audio_recordings = {}
        # Session tracking for blob logging: {websocket: {session_id, started_at, messages}}
        self.session_data = {}
        # Track users who opted out of recording
        self.recording_opt_out = set()
        # Blob storage logger (singleton)
        self.blob_logger = get_blob_logger()
    
    def _is_late_transcript(self, current_time: float) -> bool:
        """Check if a transcript arrived too late (after we already started processing)"""
        # If we processed something within the last 3 seconds, ignore new transcripts
        # This prevents late-arriving refined transcripts from causing duplicate responses
        time_since_processed = current_time - self.last_processed_time
        return self.last_processed_time > 0 and time_since_processed < 3.0
    
    def _strip_processed_text(self, transcript: str) -> str:
        """Strip all previously processed text from a cumulative transcript"""
        if not self.processed_texts:
            return transcript
        
        result = transcript.lower()
        
        # Try to find and remove all previously processed texts
        for processed in self.processed_texts:
            processed_lower = processed.lower()
            if processed_lower in result:
                # Find the position and remove it
                idx = result.find(processed_lower)
                if idx != -1:
                    result = result[:idx] + result[idx + len(processed_lower):]
        
        # Clean up the result
        result = result.strip()
        
        # If nothing left or just punctuation/filler words, return empty
        if not result or len(result) < 3:
            return ""
        
        # Try to find the actual case-preserved version in original
        # by matching position in the original transcript
        original_lower = transcript.lower()
        if result in original_lower:
            start_idx = original_lower.find(result)
            result = transcript[start_idx:start_idx + len(result)].strip()
        
        return result
    
    def _reset_session(self):
        """Reset the session - clear all processed texts"""
        self.processed_texts = []
        self.last_transcript = None
        self.last_processed_time = 0
        self.llm.clear_history()
        print("🔄 Session reset - cleared processed text history and LLM context")
    
    async def _upload_session_data(self, websocket):
        """Upload session transcript and recording to blob storage on disconnect"""
        session = self.session_data.get(websocket)
        if not session:
            return
        
        session_id = session['session_id']
        started_at = session['started_at']
        ended_at = datetime.now()
        messages = session['messages']
        
        # Upload transcript
        if messages:
            await self.blob_logger.upload_transcript(
                session_id=session_id,
                messages=messages,
                started_at=started_at,
                ended_at=ended_at
            )
        
        # Upload recording (if audio was collected)
        audio_chunks = self.audio_recordings.get(websocket, [])
        if audio_chunks:
            await self.blob_logger.upload_recording(
                session_id=session_id,
                audio_chunks=audio_chunks
            )
    
    async def _process_complete_speech(self, complete_text: str, trigger_type: str):
        """Process complete speech through LLM. Used by both semantic and timeout triggers."""
        if not self.active_connections:
            return
        
        current_time = asyncio.get_event_loop().time()
        print(f"\n💬 Complete speech ({trigger_type}): {complete_text}")
        
        # Update tracking
        self.last_transcript = complete_text
        self.last_processed_time = current_time
        self.processed_texts.append(complete_text)
        if len(self.processed_texts) > 10:
            self.processed_texts = self.processed_texts[-10:]
        
        # Process through LLM
        self.is_processing = True
        websocket = list(self.active_connections)[0]
        
        await self._safe_send(websocket, {'type': 'transcript', 'text': complete_text})
        
        self.current_processing_task = asyncio.create_task(
            self.process_message(websocket, complete_text)
        )
        self.current_speech = ""
        self.last_transcript_time = None
        
        try:
            await self.current_processing_task
        except asyncio.CancelledError:
            print("🚫 Processing cancelled by user")
        finally:
            self.is_processing = False
            self.current_processing_task = None
        
    async def initialize(self):
        """Initialize all components"""
        print("Initializing Web Voice Agent...")
        
        config.validate_config()
        
        # Show recording status
        if config.ENABLE_RECORDINGS:
            recordings_path = Path(__file__).parent / "recordings"
            print(f"✓ Audio recordings enabled (saving to: {recordings_path})")
        else:
            print("ℹ️  Audio recordings disabled (set ENABLE_RECORDINGS=true to enable)")
        
        await self.llm.initialize()
        await self.stt.connect()
        
        # Warm up TTS connection (reduces first-response latency)
        await self.tts.warmup()
        
        print("All components initialized")
        print("=" * 60)
        print("Web Voice Agent Ready!")
        print("=" * 60)
    
    async def handle_websocket(self, websocket, path, request=None):
        """Handle WebSocket connection from browser
        
        Args:
            websocket: WebSocket connection (websockets library or aiohttp WebSocketResponse)
            path: Path (for websockets library, None for aiohttp)
            request: Request object (for aiohttp, None for websockets library)
        """
        # Get remote address - handle both websockets library and aiohttp
        if hasattr(websocket, 'remote_address'):
            # websockets library
            remote_addr = websocket.remote_address
        elif request and hasattr(request, 'remote'):
            # aiohttp
            remote_addr = request.remote
        else:
            remote_addr = "unknown"
        print(f"Browser connected from {remote_addr}")
        
        # Close any existing connections (only allow one at a time to prevent double audio)
        if self.active_connections:
            print(f"  Closing {len(self.active_connections)} old connection(s)")
            for old_ws in list(self.active_connections):
                try:
                    # Check if closed - handle both websockets library and aiohttp
                    is_closed = old_ws.closed if hasattr(old_ws, 'closed') else False
                    if hasattr(old_ws, 'closing'):
                        is_closed = is_closed or old_ws.closing
                    
                    if not is_closed:
                        await old_ws.close()
                except:
                    pass
            self.active_connections.clear()
        
        self.active_connections.add(websocket)
        print(f"  Active connections: {len(self.active_connections)}")
        
        # Initialize session tracking immediately upon connection
        session_id = str(uuid.uuid4())[:8]
        
        # Pass session ID to form tools for email reference
        try:
            from mcp_tools.form_tools import set_session_id
            set_session_id(session_id)
        except ImportError:
            pass
            
        self.session_data[websocket] = {
            'session_id': session_id,
            'started_at': datetime.now(),
            'messages': []
        }
        print(f"📝 Session initialized: {session_id}")
        
        # Reset opt-out state for new connection
        self.recording_opt_out.discard(websocket)
        
        try:
            # Keep connection alive and handle messages
            async for message in websocket:
                try:
                    # Handle both websockets library (string) and aiohttp (WSMessage with .data)
                    if hasattr(message, 'data'):
                        # aiohttp WebSocket message
                        message_str = message.data if isinstance(message.data, str) else message.data.decode('utf-8')
                    else:
                        # websockets library (string)
                        message_str = message
                    
                    data = json.loads(message_str)
                    msg_type = data.get('type')
                    
                    if msg_type == 'session_start':
                        # Reset session state but keep the same session ID for the connection
                        self._reset_session()
                        
                        if websocket not in self.greeted_connections:
                            await self.send_greeting(websocket)
                            self.greeted_connections.add(websocket)
                        self.asked_to_repeat = False
                    
                    elif msg_type == 'input_audio_buffer.append':
                        # Audio from browser
                        audio_base64 = data.get('audio', '')
                        audio_bytes = base64.b64decode(audio_base64)
                        
                        if config.VERBOSE:
                            print(f"📊 Received audio: {len(audio_bytes)} bytes")
                        
                        # Store audio for recording (only if recordings are enabled AND not opted out)
                        if config.ENABLE_RECORDINGS and websocket not in self.recording_opt_out:
                            if websocket not in self.audio_recordings:
                                self.audio_recordings[websocket] = []
                            self.audio_recordings[websocket].append(audio_bytes)
                        
                        # Send to STT
                        await self.stt.send_audio(audio_bytes)
                    
                    elif msg_type == 'text_message':
                        # Direct text input
                        text = data.get('text', '').strip()
                        if text:
                            await self.process_message(websocket, text)
                    
                    elif msg_type == 'form_field_update':
                        # Manual edit from UI panel
                        try:
                            from mcp_tools.form_tools import update_form_field_from_ui
                            result = await update_form_field_from_ui(
                                form_name=data.get('form_name', ''),
                                field_id=data.get('field_id', ''),
                                value=data.get('value', '')
                            )
                            if config.DEBUG:
                                print(f"📝 UI edit: {data.get('field_id')} = {data.get('value')}")
                        except Exception as e:
                            print(f"⚠️ Form field update error: {e}")
                    
                    elif msg_type == 'ping':
                        # WebSocket keep-alive ping from client
                        await self._safe_send(websocket, {'type': 'pong'})
                    
                except json.JSONDecodeError:
                    print("⚠️ Invalid JSON received")
                    await self._safe_send(websocket, {
                        'type': 'error',
                        'message': 'Invalid message format'
                    })
                except ConnectionClosed:
                    # Connection closed during message processing
                    print("⚠️ Connection closed during message processing")
                    break
                except Exception as e:
                    print(f"⚠️ Error processing message: {e}")
                    # Don't disconnect on errors, just log and continue
                    await self._safe_send(websocket, {
                        'type': 'error',
                        'message': f'Error: {str(e)}'
                    })
            
        except ConnectionClosed as e:
            print(f"⚠️ Browser disconnected: {e.code} - {e.reason if e.reason else 'Normal closure'}")
        except asyncio.CancelledError:
            print("⚠️ WebSocket handler cancelled")
            raise
        except Exception as e:
            print(f"❌ WebSocket error: {e}")
            import traceback
            traceback.print_exc()
        finally:
            # Upload transcript and recording to blob storage
            await self._upload_session_data(websocket)
            
            # Clean up session files and reset session state
            print("Session ending - cleaning up files and history...")
            self._reset_session()
            cleanup_session_files()
            
            self.active_connections.discard(websocket)
            self.greeted_connections.discard(websocket)
            
            # Clean up session tracking
            self.session_data.pop(websocket, None)
            self.audio_recordings.pop(websocket, None)
    
    async def stt_monitor_loop(self):
        """Monitor STT for transcripts and wait for complete speech before processing"""
        while True:
            try:
                # Get transcript from STT with timeout
                # Get transcript from STT with timeout
                try:
                    result_obj = await asyncio.wait_for(
                        self.stt.get_transcript(), 
                        timeout=0.5
                    )
                    
                    # Handle both old format (str) and new format (dict)
                    if isinstance(result_obj, dict):
                        transcript = result_obj.get("text", "")
                        is_final_semantic = result_obj.get("is_final", False)
                    else:
                        transcript = str(result_obj)
                        is_final_semantic = False
                    
                    if transcript and transcript.strip():
                        self.asked_to_repeat = False
                        
                        # Azure Speech sends cumulative transcripts - strip ALL previously processed text
                        original_transcript = transcript.strip()
                        transcript = self._strip_processed_text(original_transcript)
                        
                        if not transcript:
                            # All content was already processed, skip
                            continue
                        
                        # Check if this transcript arrived too late (after we already started processing)
                        current_time = asyncio.get_event_loop().time()
                        
                        # Ignore late-arriving transcripts (refined versions from Azure Speech)
                        if self._is_late_transcript(current_time):
                            time_since = current_time - self.last_processed_time
                            print(f"🔄 Ignoring late transcript ({time_since:.1f}s after processing started): '{transcript}'")
                            continue
                        
                        # Check if identical to last processed transcript within 5 seconds
                        is_duplicate = False
                        if (self.last_transcript and 
                            transcript.strip().lower() == self.last_transcript.strip().lower() and 
                            current_time - self.last_processed_time < 5.0):
                            print(f"🔄 Ignoring duplicate input: '{transcript}'")
                            is_duplicate = True
                        
                        if is_duplicate:
                            continue
                        
                        # Only interrupt if it's NOT a duplicate
                        if self.is_processing and self.current_processing_task:
                            print("⏹️ User interrupted - cancelling current response")
                            self.current_processing_task.cancel()
                            self.current_processing_task = None
                            self.is_processing = False
                        
                        self.current_speech = transcript  # Replace, don't append
                        self.last_transcript_time = current_time
                        self.asked_to_repeat = False  # Reset repeat flag
                        
                        if config.DEBUG:
                            print(f"📝 Hearing: {transcript} (Final: {is_final_semantic})")
                        
                        # Show live transcript in UI (this triggers audio stop in browser)
                        if self.active_connections:
                            websocket = list(self.active_connections)[0]
                            await self._safe_send(websocket, {
                                'type': 'transcript_partial',  # Mark as partial
                                'text': self.current_speech,
                                'is_duplicate': False
                            })
                            
                        # FAST SEMANTIC TRIGGER - process immediately
                        if is_final_semantic:
                            print(f"⚡ FAST TRIGGER: Semantic match for '{transcript}'")
                            await self._process_complete_speech(transcript, "Semantic")
                
                except asyncio.TimeoutError:
                    pass
                    
                    # No new transcript - check if we should process complete speech
                    if self.current_speech and self.last_transcript_time and not self.is_processing:
                        time_since_last = asyncio.get_event_loop().time() - self.last_transcript_time
                        
                        # If enough silence, verify it wasn't already processed
                        if time_since_last >= config.END_OF_SPEECH_TIMEOUT:
                            # Standard timeout logic as fallback for partial results
                            # ... (existing fallback logic logic below)
                            complete_text = self.current_speech.strip()
                            
                            # Check duplication again (since Fast Trigger might have handled it)
                            current_time = asyncio.get_event_loop().time()
                            is_duplicate = False
                            time_since_processed = current_time - self.last_processed_time

                            if self._is_late_transcript(current_time):
                                is_duplicate = True
                            elif (self.last_transcript and 
                                complete_text.strip().lower() == self.last_transcript.strip().lower() and 
                                time_since_processed < 5.0):
                                is_duplicate = True
                                
                            if complete_text and not is_duplicate:
                                await self._process_complete_speech(complete_text, "Timeout")
                            
                            # Clear buffer if not processed
                            if not self.is_processing:
                                self.current_speech = ""
                                self.last_transcript_time = None
                
            except Exception as e:
                print(f"⚠️ STT monitor error: {e}")
                import traceback
                traceback.print_exc()
                self.is_processing = False
                await asyncio.sleep(0.1)
    
    async def send_greeting(self, websocket):
        """Send initial greeting to user"""
        try:
            greeting = "Hello! I'm ready to help. This call is being recorded. Just say 'stop recording' if you prefer not to be recorded."
            
            # Send text greeting
            if not await self._safe_send(websocket, {
                'type': 'response_text',
                'text': greeting
            }):
                return  # Connection closed
            
            # Synthesize and send audio
            audio_data = await self.tts.synthesize(greeting)
            if audio_data:
                # Capture AI audio for recording
                if config.ENABLE_RECORDINGS and websocket not in self.recording_opt_out:
                    if websocket not in self.audio_recordings:
                        self.audio_recordings[websocket] = []
                    self.audio_recordings[websocket].append(audio_data)

                chunk_size = 8192
                for i in range(0, len(audio_data), chunk_size):
                    chunk = audio_data[i:i + chunk_size]
                    if not await self._safe_send(websocket, {
                        'type': 'audio_chunk',
                        'audio': base64.b64encode(chunk).decode('utf-8')
                    }):
                        return  # Connection closed
                
                await self._safe_send(websocket, {
                    'type': 'audio_complete'
                })
                
                if config.DEBUG:
                    print(f"✓ Greeting sent")
        except Exception as e:
            print(f"⚠️ Error sending greeting: {e}")
    
    async def _safe_send(self, websocket, message):
        """Safely send message to WebSocket, handling closed connections"""
        try:
            # Check if connection is still open - handle both websockets library and aiohttp
            is_closed = websocket.closed if hasattr(websocket, 'closed') else False
            if hasattr(websocket, 'closing'):
                is_closed = is_closed or websocket.closing
            
            if is_closed:
                if config.DEBUG:
                    print("⚠️ Cannot send: WebSocket is closed")
                return False
            
            # Handle both websockets library and aiohttp
            message_str = json.dumps(message)
            if hasattr(websocket, 'send_str'):
                # aiohttp WebSocketResponse
                send_method = websocket.send_str
            else:
                # websockets library
                send_method = websocket.send
            
            # Send message with timeout to prevent hanging
            await asyncio.wait_for(
                send_method(message_str),
                timeout=5.0
            )
            return True
        except asyncio.TimeoutError:
            print("⚠️ WebSocket send timeout")
            return False
        except ConnectionClosed:
            if config.DEBUG:
                print("⚠️ Cannot send: Connection closed")
            return False
        except Exception as e:
            if config.DEBUG:
                print(f"⚠️ WebSocket send error: {type(e).__name__}: {e}")
            return False
    

    def _log_message(self, websocket, role: str, text: str):
        """Log message to session history"""
        if websocket in self.session_data:
            self.session_data[websocket]['messages'].append({
                'timestamp': datetime.now().isoformat(),
                'role': role,
                'content': text
            })

    async def process_message(self, websocket, user_text: str):
        """Process user message with speculative TTS execution for faster response"""
        try:
            # Log user message
            self._log_message(websocket, "user", user_text)

            # Check for opt-out intent
            if config.ENABLE_RECORDINGS and ("stop recording" in user_text.lower() or "don't record" in user_text.lower()):
                self.recording_opt_out.add(websocket)
                # Delete any existing recording for this session
                if websocket in self.audio_recordings:
                    del self.audio_recordings[websocket]
                
                print(f"🚫 User opted out of recording")
                await self._safe_send(websocket, {
                    'type': 'response_text',
                    'text': "Okay, I've stopped recording this session and deleted any audio captured so far."
                })
                self._log_message(websocket, "assistant", "Okay, I've stopped recording this session and deleted any audio captured so far.")
                # Speak the confirmation (but don't record it)
                confirmation_audio = await self.tts.synthesize("Okay, I've stopped recording this session.")
                if confirmation_audio:
                     # Send audio without appending to recording buffer
                    chunk_size = 8192
                    for i in range(0, len(confirmation_audio), chunk_size):
                        chunk = confirmation_audio[i:i + chunk_size]
                        await self._safe_send(websocket, {
                            'type': 'audio_chunk',
                            'audio': base64.b64encode(chunk).decode('utf-8')
                        })
                    await self._safe_send(websocket, {'type': 'audio_complete'})
                return

            # Notify thinking
            if not await self._safe_send(websocket, {
                'type': 'thinking',
                'status': 'start'
            }):
                return  # Connection closed
            
            if config.DEBUG:
                print("🤖 Thinking...")
            
            # Use streaming response for faster time-to-first-audio
            full_response = []
            first_audio_sent = False
            filler_sent = False  # Track if we've already sent a filler for this query
            
            # Speculative TTS: Queue for ordered audio results
            tts_queue = asyncio.Queue()
            tts_tasks = []
            sentence_order = [0]  # Use list to allow modification in nested function
            
            async def synthesize_and_queue(sentence: str, order: int):
                """Synthesize audio in parallel, queue with order for sequential playback"""
                try:
                    audio_data = await self.tts.synthesize(sentence)
                    await tts_queue.put((order, audio_data, sentence))
                except Exception as e:
                    if config.DEBUG:
                        print(f"⚠️ TTS error for sentence {order}: {e}")
                    await tts_queue.put((order, None, sentence))
            
            async def send_audio_in_order():
                """Send audio chunks maintaining sentence order"""
                nonlocal first_audio_sent
                expected_order = 0
                pending = {}
                
                while True:
                    try:
                        # Wait for next audio result with timeout
                        order, audio_data, sentence = await asyncio.wait_for(
                            tts_queue.get(), timeout=0.1
                        )
                        pending[order] = (audio_data, sentence)
                        
                        # Send any ready audio in order
                        while expected_order in pending:
                            audio, sent = pending.pop(expected_order)
                            if audio:
                                if config.DEBUG and not first_audio_sent:
                                    print(f"🔊 Starting TTS for first sentence...")
                                    first_audio_sent = True
                                
                                # Capture AI audio for recording
                                if config.ENABLE_RECORDINGS and websocket not in self.recording_opt_out:
                                    if websocket not in self.audio_recordings:
                                        self.audio_recordings[websocket] = []
                                    self.audio_recordings[websocket].append(audio)

                                chunk_size = 8192
                                for i in range(0, len(audio), chunk_size):
                                    chunk = audio[i:i + chunk_size]
                                    await self._safe_send(websocket, {
                                        'type': 'audio_chunk',
                                        'audio': base64.b64encode(chunk).decode('utf-8')
                                    })
                            expected_order += 1
                    except asyncio.TimeoutError:
                        # Check if all tasks are done and queue is empty
                        # IMPORTANT: Only exit if we have at least one task (avoid exiting during tool execution delay)
                        if tts_tasks and all(t.done() for t in tts_tasks) and tts_queue.empty():
                            # Send any remaining pending items
                            while expected_order in pending:
                                audio, _ = pending.pop(expected_order)
                                if audio:
                                    # Capture pending audio too
                                    if config.ENABLE_RECORDINGS and websocket not in self.recording_opt_out:
                                        if websocket not in self.audio_recordings:
                                            self.audio_recordings[websocket] = []
                                        self.audio_recordings[websocket].append(audio)
                                        
                                    chunk_size = 8192
                                    for i in range(0, len(audio), chunk_size):
                                        chunk = audio[i:i + chunk_size]
                                        await self._safe_send(websocket, {
                                            'type': 'audio_chunk',
                                            'audio': base64.b64encode(chunk).decode('utf-8')
                                        })
                                expected_order += 1
                            break
                    except Exception as e:
                        if config.DEBUG:
                            print(f"⚠️ Audio sender error: {e}")
                        break
            
            # Filler callback for instant audio feedback during tool execution
            async def send_filler_audio(filler_text: str):
                """Send filler audio immediately when a tool is about to execute."""
                nonlocal first_audio_sent, filler_sent
                
                if filler_sent or not filler_text:
                    return
                filler_sent = True
                
                await self._safe_send(websocket, {
                    'type': 'response_text',
                    'text': filler_text,
                    'is_filler': True
                })
                
                try:
                    audio_data = await self.tts.synthesize(filler_text)
                    if audio_data:
                        # Capture filler audio for recording
                        if config.ENABLE_RECORDINGS and websocket not in self.recording_opt_out:
                            if websocket not in self.audio_recordings:
                                self.audio_recordings[websocket] = []
                            self.audio_recordings[websocket].append(audio_data)
                            
                        if config.DEBUG:
                            print(f"🎙️ Filler: {filler_text}")
                        chunk_size = 8192
                        for i in range(0, len(audio_data), chunk_size):
                            chunk = audio_data[i:i + chunk_size]
                            await self._safe_send(websocket, {
                                'type': 'audio_chunk',
                                'audio': base64.b64encode(chunk).decode('utf-8')
                            })
                        first_audio_sent = True
                except Exception as e:
                    if config.DEBUG:
                        print(f"⚠️ Filler audio error: {e}")
            
            # Start audio sender task (runs concurrently)
            audio_sender = asyncio.create_task(send_audio_in_order())
            
            async for sentence, is_final in self.llm.generate_response_streaming(user_text, filler_callback=send_filler_audio):
                if not sentence:
                    continue
                    
                full_response.append(sentence)
                
                # Send text progressively
                current_text = ' '.join(full_response)
                if not await self._safe_send(websocket, {
                    'type': 'response_text',
                    'text': current_text,
                    'is_streaming': not is_final
                }):
                    # Connection closed - cancel tasks
                    audio_sender.cancel()
                    for t in tts_tasks:
                        t.cancel()
                    return
                
                # Fire-and-forget TTS synthesis (speculative execution)
                if sentence.strip():
                    task = asyncio.create_task(
                        synthesize_and_queue(sentence, sentence_order[0])
                    )
                    tts_tasks.append(task)
                    sentence_order[0] += 1
            
            # Wait for all TTS to complete
            if tts_tasks:
                await asyncio.gather(*tts_tasks, return_exceptions=True)
            
            # Wait for audio sender to finish
            await audio_sender
            
            # Check for any form updates from the LLM (via form_tools)
            try:
                from mcp_tools.form_tools import get_pending_form_updates
                form_updates = get_pending_form_updates()
                if form_updates:
                    if config.DEBUG:
                        print(f"📝 Applying {len(form_updates)} form updates from LLM")
                    for update in form_updates:
                        await self._safe_send(websocket, update)
            except ImportError:
                pass
            
            # Log full response
            if full_response:
                complete_response = " ".join(full_response)
                self._log_message(websocket, "assistant", complete_response)
                
                if config.DEBUG:
                    print(f"💬 AI: {complete_response[:100]}..." if len(complete_response) > 100 else f"💬 AI: {complete_response}")

            # Send completion signal
            await self._safe_send(websocket, {
                'type': 'audio_complete'
            })
        
        except Exception as e:
            print(f"❌ Error processing message: {e}")
            import traceback
            traceback.print_exc()
            
            # Send error to client
            await self._safe_send(websocket, {
                'type': 'error',
                'message': 'Failed to process your message. Please try again.'
            })
    
    async def save_recording(self, websocket):
        """Save the recorded audio to a WAV file"""
        if not config.ENABLE_RECORDINGS:
            return
        
        if websocket not in self.audio_recordings:
            return
        
        audio_chunks = self.audio_recordings[websocket]
        if not audio_chunks:
            # Remove empty recording
            del self.audio_recordings[websocket]
            return
        
        try:
            # Combine all audio chunks
            audio_data = b''.join(audio_chunks)
            
            if len(audio_data) == 0:
                del self.audio_recordings[websocket]
                return
            
            # Generate filename with timestamp
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"recording_{timestamp}.wav"
            filepath = self.recordings_dir / filename
            
            # Write WAV file
            # Audio format: 16-bit PCM, mono, 24000 Hz sample rate
            with wave.open(str(filepath), 'wb') as wav_file:
                wav_file.setnchannels(1)  # Mono
                wav_file.setsampwidth(2)  # 16-bit = 2 bytes per sample
                wav_file.setframerate(config.STT_SAMPLE_RATE)  # 24000 Hz
                wav_file.writeframes(audio_data)
            
            # Calculate duration
            duration = len(audio_data) / (config.STT_SAMPLE_RATE * 2)  # 2 bytes per sample
            
            print(f"💾 Recording saved: {filepath} ({duration:.2f} seconds, {len(audio_data)} bytes)")
            
            # Clear the recording buffer
            del self.audio_recordings[websocket]
            
        except Exception as e:
            print(f"⚠️ Error saving recording: {e}")
            import traceback
            traceback.print_exc()
            # Still remove the recording to prevent memory issues
            if websocket in self.audio_recordings:
                del self.audio_recordings[websocket]
    
    async def cleanup(self):
        """Clean up resources"""
        # Save any remaining recordings (only if recordings are enabled)
        if config.ENABLE_RECORDINGS:
            for websocket in list(self.audio_recordings.keys()):
                await self.save_recording(websocket)
        
        await self.stt.close()
        await self.llm.cleanup()


async def serve_static(request):
    """Serve static files"""
    _current_dir = Path(__file__).parent
    static_dir = _current_dir / "web_ui"
    if not static_dir.exists():
        static_dir = _current_dir.parent / "web_ui"
    
    if request.path == '/' or request.path == '':
        file_path = static_dir / "voice_agent.html"
    else:
        file_path = static_dir / request.path.lstrip('/')
    
    if file_path.exists() and file_path.is_file():
        content_type = 'text/html'
        if file_path.suffix == '.js':
            content_type = 'application/javascript'
        elif file_path.suffix == '.css':
            content_type = 'text/css'
        
        return web.Response(
            body=file_path.read_bytes(),
            content_type=content_type
        )
    
    return web.Response(text="File not found", status=404)


async def serve_pdf(request):
    """Serve PDF files from Document folder"""
    from pathlib import Path
    
    filename = request.match_info.get('filename', '')
    
    # Security: only allow .pdf files, no path traversal
    if '..' in filename or '/' in filename or '\\' in filename:
        return web.Response(text="Invalid filename", status=400)
    
    if not filename.endswith('.pdf'):
        return web.Response(text="Not a PDF", status=400)
    
    # Document folder is at project root (resolved to absolute path)
    # This handles cases where __file__ is relative or symlinked
    file_path = Path(__file__).resolve()
    document_dir = file_path.parent.parent / "Document"
    pdf_path = document_dir / filename
    
    if pdf_path.exists() and pdf_path.is_file():
        return web.Response(
            body=pdf_path.read_bytes(),
            content_type='application/pdf',
            headers={
                'Cache-Control': 'no-cache, no-store, must-revalidate',
                'Pragma': 'no-cache',
                'Expires': '0'
            }
        )
    
    return web.Response(text="PDF not found", status=404)

async def websocket_handler(request, agent):
    """Handle WebSocket upgrade requests on HTTP server with keep-alive"""
    ws = web.WebSocketResponse(
        heartbeat=20.0,       # Send ping every 20 seconds
        receive_timeout=30.0  # Close if no response within 30 seconds
    )
    await ws.prepare(request)
    await agent.handle_websocket(ws, None, request=request)
    return ws

async def init_http_server(agent):
    """Start HTTP server with WebSocket support"""
    app = web.Application()
    
    # WebSocket endpoint
    app.router.add_get('/ws', lambda request: websocket_handler(request, agent))
    
    # PDF serving endpoint (for document panel viewer)
    app.router.add_get('/pdf/{filename}', serve_pdf)
    
    # Static file serving (must be last to catch all other paths)
    app.router.add_get('/{path:.*}', serve_static)
    
    port = 8080
    host = '0.0.0.0'  # Bind to all interfaces for Docker compatibility
    print(f"Web interface: http://localhost:{port}")
    print(f"WebSocket endpoint: ws://localhost:{port}/ws")
    
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host, port)
    await site.start()
    
    await asyncio.Future()


async def init_websocket_server(agent):
    """Start WebSocket server"""
    port = 3000
    host = '0.0.0.0'  # Bind to all interfaces for Docker compatibility
    print(f"WebSocket server: ws://localhost:{port}")
    
    # Configure WebSocket server with ping/pong for keepalive
    async with serve(
        agent.handle_websocket,
        host,
        port,
        ping_interval=20,  # Send ping every 20 seconds
        ping_timeout=10,    # Wait 10 seconds for pong
        close_timeout=10    # Wait 10 seconds for close handshake
    ):
        # Also run STT monitor in background
        await agent.stt_monitor_loop()


async def main():
    """Main entry point"""
    print("\n" + "=" * 70)
    print(" " * 15 + "WEB VOICE AGENT")
    print("=" * 70)
    print("\n  Uses browser for reliable audio capture")
    print("=" * 70)
    print()
    

    
    agent = WebVoiceAgent()
    await agent.initialize()
    
    print()
    print("=" * 70)
    print("All systems ready!")
    print("Open http://localhost:8080 in your browser")
    print("=" * 70)
    print()
    
    try:
        # Run both HTTP server (with WebSocket support) and standalone WebSocket server
        # The standalone WebSocket server on port 3000 is for backward compatibility
        # The HTTP server also handles WebSocket on /ws for production deployments
        await asyncio.gather(
            init_http_server(agent),
            init_websocket_server(agent)
        )
    except KeyboardInterrupt:
        print("\n\n🛑 Shutting down...")
    finally:
        await agent.cleanup()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Goodbye!")
