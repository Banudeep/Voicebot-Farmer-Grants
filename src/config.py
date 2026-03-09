"""
Configuration for USDA Voice Agent - loads from environment variables.
"""
import os
import yaml
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# --- Azure OpenAI (Required) ---
AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT")
AZURE_OPENAI_API_KEY = os.getenv("AZURE_OPENAI_API_KEY")
AZURE_API_VERSION = os.getenv("AZURE_API_VERSION", "2025-04-01-preview")
_deployment_raw = os.getenv("AZURE_OPENAI_DEPLOYMENT")
AZURE_OPENAI_DEPLOYMENT = _deployment_raw.strip("\"'") if _deployment_raw else None

# --- Azure Speech Services (Required for STT/TTS) ---
AZURE_SPEECH_KEY = os.getenv("AZURE_SPEECH_KEY")
AZURE_SPEECH_REGION = os.getenv("AZURE_SPEECH_REGION")
AZURE_SPEECH_ENDPOINT = os.getenv("AZURE_SPEECH_ENDPOINT")
AZURE_SPEECH_LANGUAGE = os.getenv("AZURE_SPEECH_LANGUAGE", "en-US")
AZURE_SPEECH_VOICE = os.getenv("AZURE_SPEECH_VOICE", "en-US-JennyNeural")

# --- LLM Settings ---
OPENAI_TEMPERATURE = 1
OPENAI_MAX_TOKENS = 300

# --- Audio Settings ---
STT_SAMPLE_RATE = 16000
STT_CHANNELS = 1

# --- Speech Detection ---
END_OF_SPEECH_TIMEOUT = 5  # Fallback timeout - gives users time to think/spell

# --- Conversation Settings ---
MAX_CONVERSATION_HISTORY = 60
ENABLE_TOOLS = True
ENABLE_USDA_TOOLS = os.getenv("ENABLE_USDA_TOOLS", "true").lower() == "true"
ENABLE_NASS_TOOLS = os.getenv("ENABLE_NASS_TOOLS", "true").lower() == "true"
ENABLE_FARMERS_GRANTS_TOOLS = os.getenv("ENABLE_FARMERS_GRANTS_TOOLS", "true").lower() == "true"

# --- Recording & Debug ---
ENABLE_RECORDINGS = os.getenv("ENABLE_RECORDINGS", "false").lower() == "true"
DEBUG = False
VERBOSE = False

# --- Azure Blob Storage (for logging transcripts and recordings) ---
ENABLE_BLOB_LOGGING = os.getenv("ENABLE_BLOB_LOGGING", "false").lower() == "true"
AZURE_STORAGE_CONNECTION_STRING = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
AZURE_BLOB_CONTAINER_TRANSCRIPTS = os.getenv("AZURE_BLOB_CONTAINER_TRANSCRIPTS", "transcripts")
AZURE_BLOB_CONTAINER_RECORDINGS = os.getenv("AZURE_BLOB_CONTAINER_RECORDINGS", "recordings")


# --- System Prompt ---
_current_dir = Path(__file__).parent
PROMPTS_DIR = _current_dir / "prompts"
if not PROMPTS_DIR.exists():
    PROMPTS_DIR = _current_dir.parent / "prompts"
USDA_PROMPT_FILE = PROMPTS_DIR / "USDA.yml"


def load_system_prompt():
    """Load system prompt from YAML file, fallback to default."""
    if USDA_PROMPT_FILE.exists():
        try:
            with open(USDA_PROMPT_FILE, 'r', encoding='utf-8') as f:
                prompt_data = yaml.safe_load(f)
                if prompt_data and 'system' in prompt_data:
                    return prompt_data['system'].strip()
        except Exception as e:
            print(f"[WARN] Error loading prompt from {USDA_PROMPT_FILE}: {e}")
            print("  Using default system prompt")
    
    # Default fallback prompt
    return """You are a helpful voice assistant. Keep your responses concise and natural 
for voice conversation, ideally 1-3 sentences unless more detail is specifically requested. 
Speak in a friendly, conversational tone."""


SYSTEM_PROMPT = load_system_prompt()


# =============================================================================
# Configuration Validation
# =============================================================================
def validate_config():
    """Validate that required API keys are set."""
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
        print("Configuration validated")


def create_speech_config():
    """Create and return an Azure SpeechConfig instance.

    Uses AZURE_SPEECH_ENDPOINT when available, otherwise falls back to
    subscription key + region.  Call *validate_config()* first to ensure
    the required variables are set.
    """
    import azure.cognitiveservices.speech as speechsdk

    if AZURE_SPEECH_ENDPOINT:
        speech_cfg = speechsdk.SpeechConfig(
            endpoint=AZURE_SPEECH_ENDPOINT,
            subscription=AZURE_SPEECH_KEY,
        )
    else:
        speech_cfg = speechsdk.SpeechConfig(
            subscription=AZURE_SPEECH_KEY,
            region=AZURE_SPEECH_REGION,
        )
    return speech_cfg


if __name__ == "__main__":
    validate_config()
    print("All required API keys are configured")