import logging, os
import psutil
from bs4 import BeautifulSoup

from audible_epub3_maker.config import settings, in_dev
from audible_epub3_maker.utils import logging_setup, helpers
from audible_epub3_maker.utils.types import TaskPayload, TaskResult, TaskErrorResult, NoWordBoundariesError
from audible_epub3_maker.utils.constants import BEAUTIFULSOUP_PARSER, SEG_MARK_ATTR, SEG_TAG
from audible_epub3_maker.tts import create_tts_engine
from audible_epub3_maker.segmenter.html_segmenter import html_segment_and_wrap

logger = logging.getLogger(__name__)


def is_parent_alive() -> bool:
    ppid = os.getppid()
    if ppid == 1:
        return False
    
    try:
        parent = psutil.Process(ppid)
        return parent.is_running()
    except psutil.NoSuchProcess:
        return False


def init_worker(settings_dict, log_queue):
    """
    Subprocess initializer
    """
    # settings
    settings.update(settings_dict)

    # logging
    logging_setup.setup_logging_for_worker(log_queue)
    logging.getLogger().setLevel(getattr(logging, settings.log_level))

    logger.debug("👷 Worker subprocess initialized.")
    pass


def task_fn(payload: TaskPayload):
    """
    Worker function to be executed in a subprocess.

    Args:
        payload (TaskPayload): Contains task_id, HTML content, audio output path, etc.
    
    Note:
        May raise exceptions. When used with multiprocessing, wrap with `task_fn_wrap` to catch errors safely.
    """
    logger.debug(f"Task processing: {payload}")
    original_html = payload.html_text
    audio_output_file = payload.audio_output_file

    # 1. TTS synthesis
    tts = create_tts_engine(settings.tts_engine)
    wb_list = tts.html_to_speech(original_html, audio_output_file)
    logger.info(f"[Task {payload.idx}] 🔈 Generated audio: {audio_output_file}, Size: {helpers.format_bytes(audio_output_file.stat().st_size)}")

    if not wb_list:
        raise NoWordBoundariesError("The TTS engine did not return any word boundaries. It may not support this feature.")

    # 2. Parse HTML and segment by new tag.
    segmented_html = html_segment_and_wrap(original_html)
    if in_dev():
        helpers.save_text(segmented_html, audio_output_file.with_suffix(".seg_html.txt"))
    
    # 3. force alignment
    soup = BeautifulSoup(segmented_html, BEAUTIFULSOUP_PARSER)
    segment_elems = soup.select(f"{SEG_TAG}[{SEG_MARK_ATTR}]")
    taged_segments = [(tag.get("id"), tag.get_text()) for tag in segment_elems]
    alignments = helpers.force_alignment(taged_segments, 
                                         wb_list, 
                                         settings.align_threshold,
                                         audio_output_file.with_suffix(".aligns.txt"))
    return TaskResult(
        taged_html=segmented_html,
        audio_file=audio_output_file,
        alignments=alignments
    )


def test_fn(payload: TaskPayload):
    logger.debug(f"Test task processing: {payload}")
    
    import time
    time.sleep(30)
    logger.debug(f"Test worker wakeup!")

    raise NotImplementedError


def task_fn_wrap(payload: TaskPayload):
    try:
        return (True, task_fn(payload))
        # return (True, test_fn(payload))
    
    except Exception as e:
        logger.exception(f"⚠️ Task {payload.idx} failed during execution")
        return (False, TaskErrorResult(
            error_type=type(e).__name__,
            error_msg=str(e),
            payload=payload
        ))
    
    finally:
        if not is_parent_alive():
            import sys, signal
            pid = os.getpid()
            print(f"🛑 Main process (parent) has dead. Shutting down worker process [{pid}]...")
            sys.stdout.flush()
            os.kill(pid, signal.SIGTERM)