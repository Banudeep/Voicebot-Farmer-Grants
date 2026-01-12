"""
Configuration file for Voice Agent
Stores API keys, settings, and thresholds
"""
import os
import yaml
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Azure OpenAI Settings (required)
AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT")
AZURE_OPENAI_API_KEY = os.getenv("AZURE_OPENAI_API_KEY")
# Strip quotes and whitespace from deployment name (common issue in Cloud Run)
_deployment_raw = os.getenv("AZURE_OPENAI_DEPLOYMENT")
AZURE_OPENAI_DEPLOYMENT = _deployment_raw.strip('"\'') if _deployment_raw else None
AZURE_API_VERSION = os.getenv("AZURE_API_VERSION", "2025-04-01-preview")

# Azure Speech Services Settings (required for STT and TTS)
AZURE_SPEECH_KEY = os.getenv("AZURE_SPEECH_KEY")
AZURE_SPEECH_REGION = os.getenv("AZURE_SPEECH_REGION")
AZURE_SPEECH_ENDPOINT = os.getenv("AZURE_SPEECH_ENDPOINT")  # Optional, auto-constructed if not provided
AZURE_SPEECH_LANGUAGE = os.getenv("AZURE_SPEECH_LANGUAGE", "en-US")
AZURE_SPEECH_VOICE = os.getenv("AZURE_SPEECH_VOICE", "en-US-JennyNeural")  # TTS voice

# LLM Settings
OPENAI_TEMPERATURE = 1
OPENAI_MAX_TOKENS = 300  # Reduced from 500 for faster responses

# Azure Speech STT Settings
STT_SAMPLE_RATE = 16000  # 16kHz for Azure Speech
STT_CHANNELS = 1
STT_FORMAT = "PCM"  # PCM format

# Azure Speech TTS Settings
TTS_SAMPLE_RATE = 24000  # 24kHz for Azure TTS (standard)
TTS_FORMAT = "audio-16khz-128kbitrate-mono-mp3"  # or "raw-16khz-16bit-mono-pcm"

# Audio Settings
CHUNK_SIZE = 8192
AUDIO_FORMAT = "int16"

# Voice Activity Detection
VAD_THRESHOLD = 0.005  # Voice activity threshold (0-1) - Lowered for better sensitivity
SILENCE_DURATION = 1.0  # Reduced from 1.5 for faster end-of-speech detection
MIN_SPEECH_DURATION = 0.3  # Minimum speech duration in seconds
END_OF_SPEECH_TIMEOUT = 0.5  # Reduced from 0.8 for faster processing

# Conversation Settings
# Load system prompt from YAML file if available
PROMPTS_DIR = Path(__file__).parent / "prompts"
USDA_PROMPT_FILE = PROMPTS_DIR / "USDA.yml"

def load_system_prompt():
    """Load system prompt from YAML file, fallback to default"""
    if USDA_PROMPT_FILE.exists():
        try:
            with open(USDA_PROMPT_FILE, 'r', encoding='utf-8') as f:
                prompt_data = yaml.safe_load(f)
                if prompt_data and 'system' in prompt_data:
                    return prompt_data['system'].strip()
        except Exception as e:
            print(f"⚠️ Error loading prompt from {USDA_PROMPT_FILE}: {e}")
            print("  Using default system prompt")
    
    # Default fallback prompt
    return """You are a helpful voice assistant. Keep your responses concise and natural 
for voice conversation, ideally 1-3 sentences unless more detail is specifically requested. 
Speak in a friendly, conversational tone."""

SYSTEM_PROMPT = load_system_prompt()

MAX_CONVERSATION_HISTORY = 60  # Increased from 20 to prevent context loss during long form filling sessions
ENABLE_TOOLS = True  # Enable MCP tools

# Tool Enablement Flags
ENABLE_USDA_TOOLS = os.getenv("ENABLE_USDA_TOOLS", "true").lower() == "true"
ENABLE_NASS_TOOLS = os.getenv("ENABLE_NASS_TOOLS", "true").lower() == "true"
ENABLE_FARMERS_GRANTS_TOOLS = os.getenv("ENABLE_FARMERS_GRANTS_TOOLS", "true").lower() == "true"

# Performance Settings
STT_BUFFER_SIZE = 4096
TTS_BUFFER_SIZE = 8192
AUDIO_QUEUE_MAXSIZE = 500  # Increased from 100 to handle more audio

# Recording Settings
ENABLE_RECORDINGS = os.getenv("ENABLE_RECORDINGS", "false").lower() == "true"

# Debug Settings
DEBUG = False
VERBOSE = False  # Disable verbose to reduce spam (VAD working now)

# Validate API keys
def validate_config():
    """Validate that required API keys are set"""
    errors = []
    
    # Azure OpenAI is required
    if not AZURE_OPENAI_ENDPOINT:
        errors.append("AZURE_OPENAI_ENDPOINT not set")
    if not AZURE_OPENAI_API_KEY:
        errors.append("AZURE_OPENAI_API_KEY not set")
    if not AZURE_OPENAI_DEPLOYMENT:
        errors.append("AZURE_OPENAI_DEPLOYMENT not set")
    
    # Azure Speech Services is required for STT and TTS
    if not AZURE_SPEECH_KEY:
        errors.append("AZURE_SPEECH_KEY not set (required for Azure Speech STT/TTS)")
    if not AZURE_SPEECH_REGION:
        errors.append("AZURE_SPEECH_REGION not set (required for Azure Speech STT/TTS)")
    
    if errors:
        raise ValueError(f"Configuration errors: {', '.join(errors)}")
    
    if VERBOSE:
        print("✓ Configuration validated")

if __name__ == "__main__":
    validate_config()
    print("✓ All required API keys are configured")