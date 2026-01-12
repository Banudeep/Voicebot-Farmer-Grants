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
        self._init_azure()
    
    def _init_azure(self):
        """Initialize Azure Speech TTS"""
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
        
        # Set voice
        self.speech_config.speech_synthesis_voice_name = config.AZURE_SPEECH_VOICE
        
        # No audio_config needed - we'll use None to get audio data directly
        # When audio_config=None, the synthesizer returns audio data instead of playing
    
    async def synthesize(self, text: str) -> bytes:
        """Convert text to speech audio"""
        # Validate input - never synthesize None or empty text
        if text is None:
            print("⚠️ TTS: Received None text, skipping synthesis")
            return b""
        
        if not isinstance(text, str):
            print(f"⚠️ TTS: Received non-string text ({type(text)}), converting to string")
            text = str(text)
        
        text = text.strip()
        if not text:
            print("⚠️ TTS: Received empty text, skipping synthesis")
            return b""
        
        return await self._synthesize_azure(text)
    
    async def _synthesize_azure(self, text: str) -> bytes:
        """Convert text to speech using Azure Speech"""
        try:
            if config.VERBOSE:
                print(f"🔊 Synthesizing with Azure Speech: {text[:50]}...")
            
            # Create synthesizer (no audio config = returns audio data)
            synthesizer = speechsdk.SpeechSynthesizer(
                speech_config=self.speech_config,
                audio_config=None  # None = return audio data instead of playing
            )
            
            # Run synthesis in executor to avoid blocking
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                lambda: synthesizer.speak_text_async(text).get()
            )
            
            if result.reason == speechsdk.ResultReason.SynthesizingAudioCompleted:
                # Get audio data from result
                audio_bytes = bytes(result.audio_data)
                
                if config.DEBUG:
                    print(f"✓ Azure TTS generated {len(audio_bytes)} bytes")
                
                return audio_bytes
            elif result.reason == speechsdk.ResultReason.Canceled:
                cancellation = speechsdk.CancellationDetails(result)
                print(f"❌ Azure TTS canceled: {cancellation.reason}")
                if cancellation.reason == speechsdk.CancellationReason.Error:
                    print(f"   Error details: {cancellation.error_details}")
                return b""
            else:
                print(f"❌ Azure TTS failed: {result.reason}")
                return b""
            
        except Exception as e:
            print(f"❌ Azure TTS error: {e}")
            import traceback
            traceback.print_exc()
            return b""
    
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
