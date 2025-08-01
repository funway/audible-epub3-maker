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
        self.input_file: Path | None = None
        self.output_dir: Path | None = None

        self.log_level: str = "DEBUG"

        # TTS settings
        self.tts_engine: str = "azure"
        self.tts_lang: str = "en-US"
        self.tts_voice: str = "en-US-AvaMultilingualNeural"
        self.tts_chunk_len: int = -1  # Max chars length per chunk for a TTS request.

        # Force alignment similarity threshold
        self.fa_threshold: float = 95.0

        # Confirmation prompt
        self.force: bool = False  # Force all prompts to be accepted (non-interactive mode)

        # Multi-process (workers)
        self.max_workers: int = 3
        pass
    
    def update(self, args: dict) -> None:
        for k, v in args.items():
            if hasattr(self, k):
                setattr(self, k, v)
        
        if self.input_file and self.output_dir is None:
            self.output_dir = self.input_file.parent / (self.input_file.stem + "_audible")

        pass

    def to_dict(self) -> dict:
        """Export current settings as a dictionary."""
        return {
            k: getattr(self, k)
            for k in vars(self)
            if not k.startswith("_")  # skip private attrs
        }

settings = UserSettings()