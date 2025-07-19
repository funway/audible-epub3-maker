import os
from pathlib import Path
from dotenv import load_dotenv

# Load the .env file into system env if it exists
load_dotenv(override=False)

BASE_DIR = Path(__file__).resolve().parent.parent

LOG_DIR = BASE_DIR / "logs"
LOG_FILE = LOG_DIR / "app.log"
LOG_LEVEL = os.environ.get("LOG_LEVEL", "DEBUG").upper()
LOG_FORMAT = "%(asctime)s %(levelname)s [p%(process)d] %(name)s.%(funcName)s - %(message)s"

OUTPUT_DIR = BASE_DIR / "output"
INPUT_DIR = BASE_DIR / "input"

AZURE_TTS_KEY = os.environ.get("AZURE_TTS_KEY")
AZURE_TTS_REGION = os.environ.get("AZURE_TTS_REGION")

DEFAULT_LANGUAGE = os.environ.get("DEFAULT_LANGUAGE", "en-US")
DEFAULT_VOICE = os.environ.get("DEFAULT_VOICE", "en-US-AriaNeural")

BEAUTIFULSOUP_PARSER = os.environ.get("BEAUTIFULSOUP_PARSER", "lxml-xml")