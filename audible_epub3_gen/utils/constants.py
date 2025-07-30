from pathlib import Path
## Internal configuration (not intended for user modification) ##

APP_NAME = "Audible EPUB3 Gen"
APP_VERSION = "0.1.1"
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# logging config
LOG_DIR = BASE_DIR / "logs"
LOG_FILE = LOG_DIR / "app.log"
LOG_FORMAT = "%(asctime)s %(levelname)s [p%(process)d,t%(thread)d] %(name)s.%(funcName)s - %(message)s"

# HTML segmentation config
BEAUTIFULSOUP_PARSER = "lxml-xml"
SEG_ID_PREFIX = "ae"
SEG_MARK_ATTR = "data-ae-x"