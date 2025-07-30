import logging

from audible_epub3_gen.config import settings
from audible_epub3_gen.utils import logging_setup

logger = logging.getLogger(__name__)

def init_worker(settings_dict, log_queue):
    """
    Subprocess initializer
    """
    # settings
    settings.update(settings_dict)

    # logging
    logging_setup.setup_logging_for_worker(log_queue)
    logging.getLogger().setLevel(getattr(logging, settings.log_level, logging.INFO))
    logger = logging.getLogger(__name__)

    logger.debug("Worker process initialized.")
    pass

def task_fn(chapter):
    """Subprocess working function

    Args:
        task_payload (_type_): _description_
    """
    
    logger.debug(f"测试 mp: {type(chapter)}, {chapter.href}")
    logger.debug(f"当前 settings: {settings.__dict__}")
    return f"子进程 {chapter.id} 结束"