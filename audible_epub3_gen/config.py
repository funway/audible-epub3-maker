import os
from dotenv import load_dotenv

# Load the .env file into system env if it exists
load_dotenv(override=False)

AZURE_TTS_KEY = os.environ.get("AZURE_TTS_KEY")
AZURE_TTS_REGION = os.environ.get("AZURE_TTS_REGION")

DEFAULT_LANGUAGE = os.environ.get("DEFAULT_LANGUAGE", "en-US")
DEFAULT_VOICE = os.environ.get("DEFAULT_VOICE", "en-US-AriaNeural")

if not AZURE_TTS_KEY or not AZURE_TTS_REGION:
    raise ValueError(
        "Please set AZURE_TTS_KEY and AZURE_TTS_REGION. "
        "You can define them as system environment variables "
        "or in a .env file in the project root!"
    )