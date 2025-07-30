import logging
from concurrent.futures import ProcessPoolExecutor
from multiprocessing import Queue, current_process

from audible_epub3_gen.config import settings
from audible_epub3_gen.utils import helpers
from audible_epub3_gen.utils import logging_setup
from audible_epub3_gen.utils.constants import BASE_DIR
from audible_epub3_gen.epub.epub_book import EpubBook, EpubHTML
from audible_epub3_gen.segmenter.html_segmenter import html_segment_and_wrap

logger = logging.getLogger(__name__)

def init_worker(settings_dict, log_queue):
    """
    Subprocess initializer
    """
    # Explicitly import for safe
    from audible_epub3_gen.config import settings
    from audible_epub3_gen.utils import logging_setup

    # settings
    settings.update(settings_dict)

    # logging
    logging_setup.setup_logging_for_worker(log_queue)
    logging.getLogger().setLevel(getattr(logging, settings.log_level, logging.INFO))
    logger = logging.getLogger(__name__)

    logger.debug("Worker process initialized.")
    pass


class App(object):
    """docstring for App."""
    
    def __init__(self):
        super(App, self).__init__()
        pass
    
    def run(self):
        logger.debug(f"current process: {current_process().name}")
        helpers.validate_settings()

        book = EpubBook(settings.input_file)
        logger.debug(f"EPUB Book: title = [{book.title}], identifier = [{book.identifier}], language = [{book.language}]")

        if book.language != settings.tts_lang:
            msg = (
                f"⚠️ EPUB language ({book.language}) does not match TTS language setting ({settings.tts_lang}).\n"
                f"Do you want to continue using TTS language '{settings.tts_lang}'?"
            )
            helpers.confirm_or_exit(msg)

        chapters = book.get_chapters()
        for idx, chapter in enumerate(chapters, start=1):
            # logger.debug(f"chatper [{idx}/{len(chapters)}]: {chapter.id}, {chapter.href}")
            # segmented_html = html_segment_and_wrap(chapter.get_text())
            pass
        
        with ProcessPoolExecutor(max_workers=min(settings.max_workers, len(chapters)),
                                 initializer=init_worker,
                                 initargs=(settings.to_dict(),
                                           logging_setup.get_log_queue(), 
                                           )
                                 ) as executor:
            results = executor.map(helpers.test_mp, chapters)
        
        logger.debug(f"结束")
        pass