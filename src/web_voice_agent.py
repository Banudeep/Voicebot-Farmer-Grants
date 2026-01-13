"""
Web-Based Voice Agent
Uses browser for audio capture (more reliable than PyAudio)
"""
import asyncio
import json
import base64
import wave
import struct
from datetime import datetime
from pathlib import Path
from aiohttp import web
from websockets.server import serve
from websockets.exceptions import ConnectionClosed

from llm_stream import LLMStream
from stt_stream import STTStream
from tts_stream import TTSStream
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
        # Create recordings directory only if recordings are enabled
        if config.ENABLE_RECORDINGS:
            self.recordings_dir = Path(__file__).parent / "recordings"
            self.recordings_dir.mkdir(exist_ok=True)
        else:
            self.recordings_dir = None
    
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
        print("🔄 Session reset - cleared processed text history")
        
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
                        # Reset session for new connection
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
                        
                        # Store audio for recording (only if recordings are enabled)
                        if config.ENABLE_RECORDINGS:
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
            # Save recording before disconnecting (only if recordings are enabled)
            if config.ENABLE_RECORDINGS and websocket in self.audio_recordings:
                await self.save_recording(websocket)
            
            self.active_connections.discard(websocket)
            self.greeted_connections.discard(websocket)
    
    async def stt_monitor_loop(self):
        """Monitor STT for transcripts and wait for complete speech before processing"""
        while True:
            try:
                # Get transcript from STT with timeout
                try:
                    transcript = await asyncio.wait_for(
                        self.stt.get_transcript(), 
                        timeout=0.5
                    )
                    
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
                            print(f"📝 Hearing: {transcript}")
                        
                        # Show live transcript in UI (this triggers audio stop in browser)
                        # Only send if not a duplicate
                        if self.active_connections:
                            websocket = list(self.active_connections)[0]
                            await self._safe_send(websocket, {
                                'type': 'transcript_partial',  # Mark as partial
                                'text': self.current_speech,
                                'is_duplicate': False  # Explicitly mark as not duplicate
                            })
                
                except asyncio.TimeoutError:
                    pass
                    
                    # No new transcript - check if we should process complete speech
                    if self.current_speech and self.last_transcript_time and not self.is_processing:
                        time_since_last = asyncio.get_event_loop().time() - self.last_transcript_time
                        
                        # If enough silence, collect transcripts for a bit to get the best one
                        if time_since_last >= config.END_OF_SPEECH_TIMEOUT:
                            # Collect transcripts for 0.3 seconds to get the second (more accurate) version (reduced for faster response)
                            collected_transcripts = [self.current_speech.strip()]
                            start_collection_time = asyncio.get_event_loop().time()
                            
                            # Keep checking for better transcripts for 0.3 seconds
                            while (asyncio.get_event_loop().time() - start_collection_time) < 0.3:
                                try:
                                    # Quick check for new transcript
                                    new_transcript = await asyncio.wait_for(
                                        self.stt.get_transcript(),
                                        timeout=0.1
                                    )
                                    if new_transcript and new_transcript.strip():
                                        collected_transcripts.append(new_transcript.strip())
                                        self.current_speech = new_transcript  # Update buffer
                                        self.last_transcript_time = asyncio.get_event_loop().time()
                                except asyncio.TimeoutError:
                                    # No new transcript, continue waiting
                                    await asyncio.sleep(0.1)
                            
                            # Pick the BEST transcript (usually the longest/most complete = second one)
                            if collected_transcripts:
                                # Sort by length (longer usually = more complete with punctuation)
                                collected_transcripts.sort(key=len, reverse=True)
                                complete_text = collected_transcripts[0]
                                
                                if len(collected_transcripts) > 1:
                                    print(f"📝 Collected {len(collected_transcripts)} versions, using best: '{complete_text}'")
                            else:
                                complete_text = self.current_speech.strip()
                            
                            # DEDUPLICATION - check before processing
                            current_time = asyncio.get_event_loop().time()
                            is_duplicate = False
                            time_since_processed = current_time - self.last_processed_time
                            
                            # 1. Ignore late-arriving transcripts (Azure Speech refined versions)
                            if self._is_late_transcript(current_time):
                                print(f"🔄 Ignoring late transcript ({time_since_processed:.1f}s after last): '{complete_text}'")
                                is_duplicate = True
                            
                            # 2. Check if identical to last processed transcript
                            elif (self.last_transcript and 
                                complete_text.strip().lower() == self.last_transcript.strip().lower() and 
                                time_since_processed < 5.0):
                                print(f"🔄 Ignoring duplicate input: '{complete_text}'")
                                is_duplicate = True
                                
                            # 3. Check if it's a substring of the last one
                            elif (self.last_transcript and 
                                  complete_text.strip().lower() in self.last_transcript.strip().lower() and 
                                  time_since_processed < 3.0):
                                print(f"🔄 Ignoring substring input: '{complete_text}'")
                                is_duplicate = True

                            if complete_text and not is_duplicate:
                                print(f"\n💬 Complete speech: {complete_text}")
                                
                                # Update tracking
                                self.last_transcript = complete_text
                                self.last_processed_time = current_time
                                # Add to list of processed texts (for stripping from cumulative transcripts)
                                self.processed_texts.append(complete_text)
                                # Limit to last 10 processed texts to prevent memory issues
                                if len(self.processed_texts) > 10:
                                    self.processed_texts = self.processed_texts[-10:]
                                
                                # Process through LLM
                                if self.active_connections:
                                    self.is_processing = True
                                    websocket = list(self.active_connections)[0]
                                    
                                    # Send final transcript
                                    await self._safe_send(websocket, {
                                        'type': 'transcript',
                                        'text': complete_text
                                    })
                                    
                                    # Process and send response (track task for cancellation)
                                    self.current_processing_task = asyncio.create_task(
                                        self.process_message(websocket, complete_text)
                                    )
                                    
                                    # Clear buffer IMMEDIATELY after starting processing
                                    self.current_speech = ""
                                    self.last_transcript_time = None
                                    
                                    try:
                                        await self.current_processing_task
                                    except asyncio.CancelledError:
                                        print("🚫 Processing cancelled by user")
                                    finally:
                                        self.is_processing = False
                                        self.current_processing_task = None
                            
                            # Double ensure clear buffer if not processed
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
            greeting = "Hello! I'm ready to help. Just start talking when you're ready."
            
            # Send text greeting
            if not await self._safe_send(websocket, {
                'type': 'response_text',
                'text': greeting
            }):
                return  # Connection closed
            
            # Synthesize and send audio
            audio_data = await self.tts.synthesize(greeting)
            if audio_data:
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
    
    async def process_message(self, websocket, user_text: str):
        """Process user message through LLM and TTS with streaming for faster response"""
        try:
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
            
            async for sentence, is_final in self.llm.generate_response_streaming(user_text):
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
                    return  # Connection closed
                
                # Synthesize and send audio for this sentence immediately
                if sentence.strip():
                    if config.DEBUG and not first_audio_sent:
                        print("🔊 Starting TTS for first sentence...")
                        first_audio_sent = True
                    
                    audio_data = await self.tts.synthesize(sentence)
                    
                    if audio_data:
                        # Send audio in chunks
                        chunk_size = 8192
                        for i in range(0, len(audio_data), chunk_size):
                            chunk = audio_data[i:i + chunk_size]
                            if not await self._safe_send(websocket, {
                                'type': 'audio_chunk',
                                'audio': base64.b64encode(chunk).decode('utf-8')
                            }):
                                return  # Connection closed
            
            # Check for any form updates from the LLM (via form_tools)
            try:
                from mcp_tools.form_tools import get_pending_form_updates
                form_updates = get_pending_form_updates()
                if form_updates:
                    for update in form_updates:
                        for conn in self.active_connections:
                            try:
                                await conn.send(json.dumps(update))
                            except:
                                pass
                    if config.DEBUG:
                        print(f"📝 Sent {len(form_updates)} form update(s)")
            except ImportError:
                pass
            
            # Send completion signal
            await self._safe_send(websocket, {
                'type': 'audio_complete'
            })
            
            final_text = ' '.join(full_response)
            if config.DEBUG:
                print(f"💬 AI: {final_text[:100]}..." if len(final_text) > 100 else f"💬 AI: {final_text}")
        
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


async def websocket_handler(request, agent):
    """Handle WebSocket upgrade requests on HTTP server"""
    ws = web.WebSocketResponse()
    await ws.prepare(request)
    await agent.handle_websocket(ws, None, request=request)
    return ws

async def init_http_server(agent):
    """Start HTTP server with WebSocket support"""
    app = web.Application()
    
    # WebSocket endpoint
    app.router.add_get('/ws', lambda request: websocket_handler(request, agent))
    
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
