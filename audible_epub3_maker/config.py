import os
from pathlib import Path
from dotenv import load_dotenv

## Configuration that can be modified by users via environment variables ##
load_dotenv(override=False)  # Load variables from .env into os.environ if not already set

AZURE_TTS_KEY = os.environ.get("AZURE_TTS_KEY", "")
AZURE_TTS_REGION = os.environ.get("AZURE_TTS_REGION", "")

AUDIBLE_EPUB3_MAKER_ENV = os.environ.get("AUDIBLE_EPUB3_MAKER_ENV", "production")


def in_dev() -> bool:
    return AUDIBLE_EPUB3_MAKER_ENV.lower() in {"dev", "development"}


## User-specified command-line options ##
class UserSettings:
    def __init__(self):
        self.input_file: Path | None = None
        self.output_dir: Path | None = None

        self.log_level: str = "INFO"
        if in_dev():
            self.log_level = "DEBUG"

        # TTS settings
        self.tts_engine: str = "azure"
        self.tts_lang: str = "en-US"
        self.tts_voice: str = "en-US-AvaMultilingualNeural"
        self.tts_chunk_len: int = -1  # Max chars length per chunk for a TTS request.
        self.tts_speed: float = 1.0

        # Force alignment similarity threshold
        self.align_threshold: float = 95.0

        # Confirmation prompt
        self.force: bool = False  # Force all prompts to be accepted (non-interactive mode)

        # Multi-process (workers)
        self.max_workers: int = 3

        self.newline_mode: str = "multi"

        self.cleanup: bool = False
        pass
    
    def update(self, args: dict) -> None:
        for k, v in args.items():
            if hasattr(self, k):
                setattr(self, k, v)
        
        if self.input_file and not self.output_dir:
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