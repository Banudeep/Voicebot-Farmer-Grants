"""
Speech-to-Text Streaming Module
Uses Azure Speech Services
"""
import asyncio
import traceback
import config
import azure.cognitiveservices.speech as speechsdk
from azure.cognitiveservices.speech.audio import AudioStreamFormat, PushAudioInputStream

class STTStream:
    """Streaming speech-to-text processor using Azure Speech Services"""
    
    def __init__(self):
        self.transcript_queue = asyncio.Queue()
        self.is_connected = False
        self._last_transcript = None
        self._event_loop = None
        self._init_azure()
    
    def _queue_result(self, result: dict):
        """Queue a transcript result from Azure callback thread."""
        loop = self._event_loop if self._event_loop and self._event_loop.is_running() else None
        if not loop:
            try:
                loop = asyncio.get_event_loop()
                if not loop.is_running():
                    loop = None
            except RuntimeError:
                loop = None
        if loop:
            asyncio.run_coroutine_threadsafe(self.transcript_queue.put(result), loop)
    
    def _init_azure(self):
        """Initialize Azure Speech client"""
        self.speech_config = config.create_speech_config()
        
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
            print("Starting Azure Speech STT connection...")
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
            
            # Configure recognition settings for faster response and semantic endpointing
            # Enable Semantic Segmentation (Endpointing) - helps prevent cutting off during pauses
            # Requires SDK 1.41.0+
            self.speech_config.set_property(
                speechsdk.PropertyId.Speech_SegmentationStrategy, 
                "Semantic"
            )
            
            # Set property to return interim results more frequently
            self.speech_config.set_property(
                speechsdk.PropertyId.Speech_SegmentationSilenceTimeoutMs, 
                "5000"  # 5 seconds - matches END_OF_SPEECH_TIMEOUT
            )
            
            # Start continuous recognition
            self.recognizer.start_continuous_recognition_async()
            
            self.is_connected = True
            print("Azure Speech STT connected!")
            return True
            
        except Exception as e:
            print(f"[ERROR] Azure Speech STT connection error: {e}")
            traceback.print_exc()
            return False
    
    def _on_azure_session_started(self, evt):
        """Handle session started event."""
        if config.DEBUG:
            print(f"Azure Speech session started: {evt.session_id}")

    def _on_azure_session_stopped(self, evt):
        """Handle session stopped event."""
        if config.DEBUG:
            print(f"Azure Speech session stopped: {evt.session_id}")

    def _on_azure_canceled(self, evt):
        """Handle recognition canceled event."""
        cancellation = evt.result.cancellation_details
        print(f"[WARN] Azure Speech canceled: {cancellation.reason}")
        if cancellation.reason == speechsdk.CancellationReason.Error:
            print(f"   Error details: {cancellation.error_details}")

    def _on_azure_recognizing(self, evt):
        """Handle interim recognition results (partial transcripts)."""
        try:
            if evt.result.reason == speechsdk.ResultReason.RecognizingSpeech:
                transcript = evt.result.text.strip()
                if transcript:
                    self._queue_result({"text": transcript, "is_final": False})
        except Exception as e:
            if config.DEBUG:
                print(f"[WARN] Azure Speech interim result error: {e}")
    
    def _on_azure_recognized(self, evt):
        """Handle final recognition result (after silence detected)."""
        try:
            if evt.result.reason == speechsdk.ResultReason.RecognizedSpeech:
                transcript = evt.result.text.strip()
                if transcript and transcript != self._last_transcript:
                    self._last_transcript = transcript
                    print(f"\nTRANSCRIPT (FINAL): {transcript}")
                    self._queue_result({"text": transcript, "is_final": True})
            elif evt.result.reason == speechsdk.ResultReason.NoMatch:
                if config.VERBOSE:
                    print("[WARN] Azure Speech: No speech could be recognized")
        except Exception as e:
            print(f"[ERROR] Azure Speech recognition error: {e}")

    async def send_audio(self, audio_data: bytes):
        """Send audio data for transcription"""
        if self.push_stream and self.is_connected:
            try:
                # Azure expects audio data as bytes
                self.push_stream.write(audio_data)
            except Exception as e:
                print(f"[WARN] Error sending audio to Azure Speech: {e}")
        else:
            if not self._warned_disconnected:
                print(f"[WARN] Cannot send audio: Azure Speech not connected")
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
            print("Azure Speech STT disconnected")


async def test_stt():
    """Test STT streaming"""
    print("Testing Azure Speech STT stream...")
    
    stt = STTStream()
    await stt.connect()
    
    print("Say something...")
    
    try:
        result = await asyncio.wait_for(
            stt.get_transcript(),
            timeout=10.0
        )
        print(f"Received: {result}")
    except asyncio.TimeoutError:
        print("[WARN] No speech detected")
    
    await stt.close()
    print("STT test complete")


if __name__ == "__main__":
    asyncio.run(test_stt())