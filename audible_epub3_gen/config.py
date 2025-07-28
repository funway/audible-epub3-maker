import os
from pathlib import Path
from dotenv import load_dotenv

## Internal configuration (not intended for user modification) ##
APP_NAME = "Audible EPUB3 Gen"
APP_VERSION = "0.1.1"
BASE_DIR = Path(__file__).resolve().parent.parent

INPUT_DIR = BASE_DIR / "input"    # only used for dev and testing
OUTPUT_DIR = BASE_DIR / "output"  # only used for dev and testing

# logging config
LOG_DIR = BASE_DIR / "logs"
LOG_FILE = LOG_DIR / "app.log"
LOG_FORMAT = "%(asctime)s %(levelname)s [p%(process)d,t%(thread)d] %(name)s.%(funcName)s - %(message)s"

# HTML segmentation config
BEAUTIFULSOUP_PARSER = "lxml-xml"
SEG_ID_PREFIX = "ae"
SEG_MARK_ATTR = "data-ae-x"

## Configuration that can be modified by users via environment variables ##
load_dotenv(override=False)  # Load the .env file into system env if it exists
AZURE_TTS_KEY = os.environ.get("AZURE_TTS_KEY", "YOUR_AZURE_SPEECH_KEY")
AZURE_TTS_REGION = os.environ.get("AZURE_TTS_REGION", "YOUR_REGION")


## User-specified command-line options ##
class UserSettings:
    def __init__(self):
        self._args = {}
        
        self.log_level: str = getattr(self._args, "log_level", "DEBUG").upper()

        # TTS settings
        self.tts_engine = getattr(self._args, "tts_engine", "azure").lower()
        self.tts_lang = getattr(self._args, "tts_lang", "en-US")
        self.tts_voice = getattr(self._args, "tts_voice", "en-US-AvaMultilingualNeural")
        pass
    
    def update_args(self, args: dict[str, str]) -> None:
        self._args = args.copy()
        pass

settings = UserSettings()