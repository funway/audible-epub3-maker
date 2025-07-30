import atexit
import logging
from logging.handlers import RotatingFileHandler, QueueHandler, QueueListener
from multiprocessing import Queue, current_process

from audible_epub3_gen.config import settings
from audible_epub3_gen.utils.constants import LOG_FILE, LOG_DIR, LOG_FORMAT


_log_queue = None
_log_listener = None

def _is_main_process() -> bool:
    return current_process().name == "MainProcess"


def setup_logging_for_main():
    """
    Initialize logging system for the main process.

    - Automatically skipped when called from a subprocess.
    - Clears existing handlers on the root logger.
    - Adds both file and console handlers.
    - Creates a log queue and attaches a QueueListener.
    """
    global _log_queue 
    global _log_listener

    if not _is_main_process():
        # Skip for subprocesses
        return
    
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, settings.log_level, logging.INFO))
    root_logger.handlers.clear()

    formatter = logging.Formatter(LOG_FORMAT)
    
    file_handler = RotatingFileHandler(filename=LOG_FILE, 
                                       mode='a', 
                                       maxBytes=16*1024*1024,
                                       backupCount=3,
                                       encoding='utf-8',)
    file_handler.setFormatter(formatter)
    
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    if _log_queue is None:
        _log_queue = Queue()
    _log_listener = QueueListener(_log_queue, file_handler, console_handler)
    _log_listener.start()

    root_logger.addHandler(QueueHandler(_log_queue))
    pass


def setup_logging_for_worker(shared_log_queue: Queue):
    """
    Configure logging in a worker process to use the shared log queue.

    Args:
        shared_log_queue (Queue): The multiprocessing queue from the main process.
    """
    root_logger = logging.getLogger()
    root_logger.addHandler(QueueHandler(shared_log_queue))
    pass


def get_log_queue() -> Queue:
    """
    Get the shared log queue for use by ProcessPoolExecutor initializer.

    Returns:
        Queue: The multiprocessing log queue.
    """
    return _log_queue


def stop_logging():
    """Stop logging listener gracefully."""
    global _log_listener

    if _log_listener is not None:
        _log_listener.stop()
    pass


# Register automatic shutdown hook
atexit.register(stop_logging)


# Initialize logging when this module is first imported
# Only runs in main process (no-op in subprocesses),
# safe with multiprocessing and ProcessPoolExecutor.
setup_logging_for_main()
