import os
from pathlib import Path
from dotenv import load_dotenv

## Configuration that can be modified by users via environment variables ##
load_dotenv(override=False)  # Load the .env file into system env if it exists
AZURE_TTS_KEY = os.environ.get("AZURE_TTS_KEY", "YOUR_AZURE_SPEECH_KEY")
AZURE_TTS_REGION = os.environ.get("AZURE_TTS_REGION", "YOUR_REGION")


## User-specified command-line options ##
class UserSettings:
    def __init__(self):
        self._args = {}

        self.input_file: Path = None
        self.output_dir: Path = None

        self.log_level: str = getattr(self._args, "log_level", "DEBUG").upper()

        # TTS settings
        self.tts_engine: str = "azure"
        self.tts_lang: str = "en-US"
        self.tts_voice: str = "en-US-AvaMultilingualNeural"

        self.force: bool = False  # Force all prompts to be accepted (non-interactive mode)
        pass
    
    def update_args(self, args: dict) -> None:
        self._args = args.copy()
        
        for k, v in args.items():
            if hasattr(self, k):
                setattr(self, k, v)
        
        if self.input_file and self.output_dir is None:
            self.output_dir = self.input_file.parent / (self.input_file.stem + "_audible")

        pass

settings = UserSettings()