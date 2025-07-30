import logging
from logging.handlers import RotatingFileHandler

from audible_epub3_gen.config import settings
from audible_epub3_gen.utils.constants import LOG_FILE, LOG_DIR, LOG_FORMAT

def setup_logging():
    """Sets up logging configuration for the application.
    """
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    root_logger = logging.getLogger()
    root_logger.setLevel(settings.log_level)

    formatter = logging.Formatter(LOG_FORMAT)

    file_handler = RotatingFileHandler(filename=LOG_FILE, 
                                       mode='a', 
                                       maxBytes=16*1024*1024,
                                       backupCount=3,
                                       encoding='utf-8',)
    file_handler.setFormatter(formatter)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    if not root_logger.hasHandlers():
        root_logger.addHandler(file_handler)
        root_logger.addHandler(console_handler)

# Initialize logging when this module is first imported
setup_logging()
