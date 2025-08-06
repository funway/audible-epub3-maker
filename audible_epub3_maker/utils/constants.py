from pathlib import Path
## Internal configuration (not intended for user modification) ##

APP_NAME = "Audible EPUB3 Maker"
APP_VERSION = "0.1.1"
APP_FULLNAME = APP_NAME + " v" + APP_VERSION
APP_IN_DEV = True

BASE_DIR = Path(__file__).resolve().parent.parent.parent
OUTPUT = BASE_DIR / "output"
DEV_OUTPUT = BASE_DIR / "dev_output"

# logging config
LOG_DIR = BASE_DIR / "logs"
LOG_FILE = LOG_DIR / "app.log"
LOG_FORMAT = "%(asctime)s [%(levelname)5s] [p%(process)d,t%(thread)d] %(name)s.%(funcName)s:%(lineno)d - %(message)s"
LOG_FORMAT_SIMPLE = "[%(asctime)s] [p%(process)d] [%(levelname)s] - %(message)s"

# HTML segmentation config
BEAUTIFULSOUP_PARSER = "lxml-xml"
SEG_TAG = "span"
SEG_ID_PREFIX = "ae"
SEG_MARK_ATTR = "data-ae-x"

AUDIO_MIMETYPES = {
    ".mp3": "audio/mpeg",
    ".m4a": "audio/mp4",
    ".mp4": "audio/mp4",
    ".ogg": "audio/ogg",
}
