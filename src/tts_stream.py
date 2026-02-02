"""
Text-to-Speech Streaming Module
Uses Azure Speech Services
"""
import asyncio
import config
import azure.cognitiveservices.speech as speechsdk

class TTSStream:
    """Streaming text-to-speech processor using Azure Speech Services"""
    
    def __init__(self):
        self.audio_queue = asyncio.Queue()
        self._synthesizer = None
        self._synthesizer_lock = asyncio.Lock()
        self._warmup_done = False
        self._init_azure()
    
    def _init_azure(self):
        """Initialize Azure Speech TTS with connection pooling."""
        if not config.AZURE_SPEECH_KEY or not config.AZURE_SPEECH_REGION:
            raise ValueError("AZURE_SPEECH_KEY and AZURE_SPEECH_REGION must be set")
        
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
        
        self.speech_config.speech_synthesis_voice_name = config.AZURE_SPEECH_VOICE
        self.speech_config.set_speech_synthesis_output_format(
            speechsdk.SpeechSynthesisOutputFormat.Raw16Khz16BitMonoPcm
        )
        self._synthesizer = speechsdk.SpeechSynthesizer(
            speech_config=self.speech_config, audio_config=None
        )
    
    async def warmup(self):
        """Warm up the TTS connection to reduce first-response latency"""
        if self._warmup_done:
            return
        
        try:
            # Synthesize a minimal phrase to warm up the connection
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: self._synthesizer.speak_text_async(" ").get()
            )
            self._warmup_done = True
            if config.DEBUG:
                print("✓ TTS connection warmed up")
        except Exception as e:
            if config.DEBUG:
                print(f"⚠️ TTS warmup failed: {e}")
    
    async def synthesize(self, text: str) -> bytes:
        """Convert text to speech audio. Returns empty bytes for invalid input."""
        if not text or not isinstance(text, str):
            if text is not None and not isinstance(text, str):
                text = str(text)
            else:
                return b""
        text = text.strip()
        return await self._synthesize_azure(text) if text else b""
    
    async def _synthesize_azure(self, text: str) -> bytes:
        """Convert text to speech using pooled Azure connection."""
        try:
            if config.VERBOSE:
                print(f"🔊 Synthesizing: {text[:50]}...")
            
            async with self._synthesizer_lock:
                loop = asyncio.get_event_loop()
                result = await loop.run_in_executor(
                    None, lambda: self._synthesizer.speak_text_async(text).get()
                )
            
            if result.reason == speechsdk.ResultReason.SynthesizingAudioCompleted:
                audio_bytes = bytes(result.audio_data)
                if config.DEBUG:
                    print(f"✓ TTS generated {len(audio_bytes)} bytes")
                return audio_bytes
            
            if result.reason == speechsdk.ResultReason.Canceled:
                cancellation = speechsdk.CancellationDetails(result)
                print(f"❌ TTS canceled: {cancellation.reason}")
                if cancellation.reason == speechsdk.CancellationReason.Error:
                    print(f"   Error: {cancellation.error_details}")
            else:
                print(f"❌ TTS failed: {result.reason}")
            return b""
        except Exception as e:
            print(f"❌ TTS error: {e}")
            return b""
    
    def set_voice(self, voice_name: str):
        """Update the voice used for synthesis."""
        if not voice_name:
            return
            
        try:
            # Update config and recreate synthesizer
            self.speech_config.speech_synthesis_voice_name = voice_name
            
            # Re-initialize synthesizer with new voice config
            self._synthesizer = speechsdk.SpeechSynthesizer(
                speech_config=self.speech_config, audio_config=None
            )
            
            if config.DEBUG:
                print(f"✓ Voice updated to: {voice_name}")
        except Exception as e:
            print(f"❌ Error updating voice to {voice_name}: {e}")

    async def synthesize_stream(self, text: str, chunk_callback):
        """Stream audio synthesis with callback for each chunk"""
        await self._synthesize_stream_azure(text, chunk_callback)
    
    async def _synthesize_stream_azure(self, text: str, chunk_callback):
        """Stream Azure TTS"""
        try:
            # Azure Speech doesn't have native streaming
            # So we'll synthesize and then stream the chunks
            audio_bytes = await self._synthesize_azure(text)
            
            if audio_bytes:
                # Stream in chunks
                chunk_size = 4096
                for i in range(0, len(audio_bytes), chunk_size):
                    chunk = audio_bytes[i:i + chunk_size]
                    await chunk_callback(chunk)
            
        except Exception as e:
            print(f"❌ Azure TTS streaming error: {e}")
            import traceback
            traceback.print_exc()


async def test_tts():
    """Test TTS synthesis"""
    print("Testing Azure Speech TTS stream...")
    
    tts = TTSStream()
    
    audio = await tts.synthesize("Hello! This is a test of the text to speech system.")
    
    if audio:
        print(f"✓ Generated {len(audio)} bytes of audio")
        
        # Optionally save to file
        filename = "test_tts_azure.wav"
        with open(filename, "wb") as f:
            f.write(audio)
        print(f"✓ Saved to {filename}")
    
    print("✓ TTS test complete")


if __name__ == "__main__":
    asyncio.run(test_tts())
