"""
Speech-to-Text Streaming Module
Uses Azure Speech Services
"""
import asyncio
import config
import azure.cognitiveservices.speech as speechsdk
from azure.cognitiveservices.speech.audio import AudioStreamFormat, PushAudioInputStream

class STTStream:
    """Streaming speech-to-text processor using Azure Speech Services"""
    
    def __init__(self):
        self.transcript_queue = asyncio.Queue()
        self.is_connected = False
        self._last_transcript = None
        self._event_loop = None  # Store event loop for Azure callbacks
        
        self._init_azure()
    
    def _init_azure(self):
        """Initialize Azure Speech client"""
        if not config.AZURE_SPEECH_KEY or not config.AZURE_SPEECH_REGION:
            raise ValueError("AZURE_SPEECH_KEY and AZURE_SPEECH_REGION must be set for Azure Speech")
        
        # Create speech config
        if config.AZURE_SPEECH_ENDPOINT:
            self.speech_config = speechsdk.SpeechConfig(
                endpoint=config.AZURE_SPEECH_ENDPOINT,
                subscription=config.AZURE_SPEECH_KEY
            )
        else:
            self.speech_config = speechsdk.SpeechConfig(
                subscription=config.AZURE_SPEECH_KEY,
                region=config.AZURE_SPEECH_REGION
            )
        
        self.speech_config.speech_recognition_language = config.AZURE_SPEECH_LANGUAGE
        
        # Audio input stream
        self.audio_format = AudioStreamFormat(
            samples_per_second=config.STT_SAMPLE_RATE,
            bits_per_sample=16,
            channels=config.STT_CHANNELS
        )
        self.push_stream = PushAudioInputStream(stream_format=self.audio_format)
        self.audio_config = speechsdk.audio.AudioConfig(stream=self.push_stream)
        
        # Recognizer
        self.recognizer = None
        self._transcript_buffer = []
        self._warned_disconnected = False
        
    async def connect(self):
        """Connect to Azure Speech STT service"""
        try:
            print("🔌 Starting Azure Speech STT connection...")
            print(f"   Language: {config.AZURE_SPEECH_LANGUAGE}")
            print(f"   Sample Rate: {config.STT_SAMPLE_RATE}")
            
            # Store event loop for callbacks
            self._event_loop = asyncio.get_event_loop()
            
            # Create recognizer
            self.recognizer = speechsdk.SpeechRecognizer(
                speech_config=self.speech_config,
                audio_config=self.audio_config
            )
            
            # Set up event handlers
            # IMPORTANT: Connect to 'recognizing' for interim results (faster) AND 'recognized' for final results
            self.recognizer.recognizing.connect(self._on_azure_recognizing)  # Interim results - fires quickly
            self.recognizer.recognized.connect(self._on_azure_recognized)  # Final results - fires after silence
            self.recognizer.session_started.connect(self._on_azure_session_started)
            self.recognizer.session_stopped.connect(self._on_azure_session_stopped)
            self.recognizer.canceled.connect(self._on_azure_canceled)
            
            # Configure recognition settings for faster response
            # Set property to return interim results more frequently
            self.speech_config.set_property(
                speechsdk.PropertyId.Speech_SegmentationSilenceTimeoutMs, 
                "500"  # 500ms silence timeout (faster than default)
            )
            
            # Start continuous recognition
            self.recognizer.start_continuous_recognition_async()
            
            self.is_connected = True
            print("✓ Azure Speech STT connected!")
            return True
            
        except Exception as e:
            print(f"❌ Azure Speech STT connection error: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def _on_azure_recognizing(self, evt):
        """Handle Azure Speech interim recognition results (faster, partial transcripts)"""
        try:
            if evt.result.reason == speechsdk.ResultReason.RecognizingSpeech:
                transcript = evt.result.text.strip()
                if transcript:
                    # Send interim results immediately
                    # These are partial/refined results that update as you speak
                    if self._event_loop and self._event_loop.is_running():
                        asyncio.run_coroutine_threadsafe(
                            self.transcript_queue.put(transcript),
                            self._event_loop
                        )
                    else:
                        try:
                            loop = asyncio.get_event_loop()
                            if loop.is_running():
                                asyncio.run_coroutine_threadsafe(
                                    self.transcript_queue.put(transcript),
                                    loop
                                )
                        except RuntimeError:
                            pass
        except Exception as e:
            if config.DEBUG:
                print(f"⚠️ Azure Speech interim result error: {e}")
    
    def _on_azure_recognized(self, evt):
        """Handle Azure Speech final recognition result (after silence detected)"""
        try:
            if evt.result.reason == speechsdk.ResultReason.RecognizedSpeech:
                transcript = evt.result.text.strip()
                if transcript and transcript != self._last_transcript:
                    self._last_transcript = transcript
                    print(f"\n✅ 📝 TRANSCRIPT: {transcript}")
                    
                    # Azure callbacks run in a different thread, so we need to use
                    # run_coroutine_threadsafe to schedule the async operation
                    if self._event_loop and self._event_loop.is_running():
                        asyncio.run_coroutine_threadsafe(
                            self.transcript_queue.put(transcript),
                            self._event_loop
                        )
                    else:
                        # Fallback: try to get current loop
                        try:
                            loop = asyncio.get_event_loop()
                            if loop.is_running():
                                asyncio.run_coroutine_threadsafe(
                                    self.transcript_queue.put(transcript),
                                    loop
                                )
                        except RuntimeError:
                            # No event loop available - this shouldn't happen but handle gracefully
                            print("⚠️ No event loop available for Azure Speech callback")
            elif evt.result.reason == speechsdk.ResultReason.NoMatch:
                if config.VERBOSE:
                    print("⚠️ Azure Speech: No speech could be recognized")
        except Exception as e:
            print(f"❌ Azure Speech recognition error: {e}")
            import traceback
            traceback.print_exc()
    
    def _on_azure_session_started(self, evt):
        """Handle Azure Speech session started"""
        if config.DEBUG:
            print("🔗 Azure Speech session started")
    
    def _on_azure_session_stopped(self, evt):
        """Handle Azure Speech session stopped"""
        if config.DEBUG:
            print("🔌 Azure Speech session stopped")
    
    def _on_azure_canceled(self, evt):
        """Handle Azure Speech cancellation"""
        if evt.reason == speechsdk.CancellationReason.Error:
            print(f"❌ Azure Speech error: {evt.error_details}")
        self.is_connected = False
    
    async def send_audio(self, audio_data: bytes):
        """Send audio data for transcription"""
        if self.push_stream and self.is_connected:
            try:
                # Azure expects audio data as bytes
                self.push_stream.write(audio_data)
            except Exception as e:
                print(f"⚠️ Error sending audio to Azure Speech: {e}")
        else:
            if not self._warned_disconnected:
                print(f"⚠️ Cannot send audio: Azure Speech not connected")
                self._warned_disconnected = True
    
    async def get_transcript(self) -> str:
        """Get next transcript from queue"""
        return await self.transcript_queue.get()
    
    async def close(self):
        """Close STT connection"""
        self.is_connected = False
        
        if self.recognizer:
            try:
                self.recognizer.stop_continuous_recognition_async()
            except:
                pass
        if self.push_stream:
            try:
                self.push_stream.close()
            except:
                pass
        
        if config.DEBUG:
            print("🔌 Azure Speech STT disconnected")


async def test_stt():
    """Test STT streaming"""
    print("Testing Azure Speech STT stream...")
    
    stt = STTStream()
    await stt.connect()
    
    print("Say something...")
    
    try:
        transcript = await asyncio.wait_for(
            stt.get_transcript(),
            timeout=10.0
        )
        print(f"✓ Received: {transcript}")
    except asyncio.TimeoutError:
        print("⚠️ No speech detected")
    
    await stt.close()
    print("✓ STT test complete")


if __name__ == "__main__":
    asyncio.run(test_stt())
