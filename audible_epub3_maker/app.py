import logging, time, sys, signal
import psutil
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor, Executor, as_completed

from audible_epub3_maker.config import settings
from audible_epub3_maker.utils import helpers
from audible_epub3_maker.utils import logging_setup
from audible_epub3_maker.utils.constants import BASE_DIR, APP_FULLNAME, AUDIO_MIMETYPES
from audible_epub3_maker.utils.types import TaskPayload
from audible_epub3_maker.epub.epub_book import EpubBook, EpubHTML, EpubAudio, LazyLoadFromFile, EpubSMIL
from audible_epub3_maker.worker import init_worker, task_fn_wrap

logger = logging.getLogger(__name__)
executor: Executor | None = None


class App(object):
    """docstring for App."""
    
    def __init__(self):
        super(App, self).__init__()
        pass

    def prepare_payloads(self, chapters: list[EpubHTML]) -> list[TaskPayload]:
        pass
    
    def run(self):
        global executor
        setup_signal_handlers()

        # 1. Load EPUB file
        book = EpubBook(settings.input_file)
        logger.info(f"📕 EPUB Book Info: title = [{book.title}], identifier = [{book.identifier}], language = [{book.language}]")

        if book.language != settings.tts_lang:
            msg = (
                f"⚠️ == EPUB language ({book.language}) does not match TTS language setting ({settings.tts_lang}).\n"
                f"Do you want to continue using TTS language '{settings.tts_lang}'?"
            )
            helpers.confirm_or_exit(msg)

        # 2. Prepare payloads for TTS and Forcealignment tasks
        chapter_list = [ch for ch in book.get_chapters() if ch.count_visible_chars() > 0]
        payload_list: list[TaskPayload] = []
        success_list: list[int] = []
        failed_list: list[int] = []
        for idx, chapter in enumerate(chapter_list):
            chapter_filename = Path(chapter.href).stem  # filename, not real content Chapter
            chapter_audio_output_file = settings.output_dir / f"{book.identifier}_aud{idx}.mp3"
            chapter_audio_metadata = {
                "title": f"{book.title} - {chapter_filename}",
                "album": book.epub_path.stem,
                "publisher": APP_FULLNAME,
            }
            payload_list.append(TaskPayload(idx=idx,
                                             html_text=chapter.get_text(),
                                             audio_output_file=chapter_audio_output_file,
                                             audio_metadata=chapter_audio_metadata,
                                             ))
        
        # 3. Dispatch tasks and wait for completion
        logger.info(f"🚀 Start processing [{settings.input_file.name}] ... (Total tasks: {len(payload_list)})")
        start_time = time.perf_counter()
        with ProcessPoolExecutor(max_workers=min(settings.max_workers, len(chapter_list)),
                                 initializer=init_worker,
                                 initargs=(settings.to_dict(),
                                           logging_setup.get_log_queue(), 
                                           )
                                 ) as executor:
            future_to_idx = {}
            futures = []

            for payload in payload_list:
                future = executor.submit(task_fn_wrap, payload)
                futures.append(future)
                future_to_idx[future] = payload.idx
            
            for future in as_completed(futures):
                idx = future_to_idx[future]
                try:
                    success, task_result = future.result()
                except Exception as e:
                    logger.exception(f"🛑 Unexpected executor-level error for task {idx}: {e}")
                    raise e

                if success:
                    logger.info(f"✅ [Task {idx}] complete. {task_result}")
                    
                    # s0. Get the corresponding chapter item
                    chapter: EpubHTML = chapter_list[idx]

                    # s1. Add audio to EPUB
                    aud_id = f"aud_{idx}"
                    aud_suffix = task_result.audio_file.suffix
                    aud_href = f"audio/{aud_id}{aud_suffix}"
                    audio_item = EpubAudio(raw_content = LazyLoadFromFile(task_result.audio_file),
                                           id = aud_id,
                                           href = aud_href,
                                           media_type = AUDIO_MIMETYPES[aud_suffix]
                                           )
                    book.add_item(audio_item)

                    # s2. Add SMIL
                    smil_href = str(chapter.href) + ".smil"
                    smil_text = helpers.generate_smil_content(smil_href, chapter.href, aud_href, task_result.alignments)
                    smil_id = f"sm_{idx}"
                    smil_item = EpubSMIL(raw_content = smil_text.encode(),
                                         id = smil_id,
                                         href = smil_href,
                                         media_type = "application/smil+xml",
                                         )
                    book.add_item(smil_item)

                    # s3. Update the corresponding chapter item
                    chapter.attrs["media-overlay"] = smil_id  # Add overlay property 
                    chapter.set_text(task_result.taged_html)  # Modify HTML text
                    
                    success_list.append(idx)
                else:
                    logger.warning(f"❌ [Task {idx}] failed. {task_result}")
                    failed_list.append(idx)
        
        # 4. Report and save
        elapsed = time.perf_counter() - start_time
        logger.info(f"🎉 Processing complete. {len(success_list)} success, {len(failed_list)} failed. (finished in {helpers.format_seconds(elapsed)})")
        if len(success_list) == 0:
            # All failed
            logger.warning("😔 Oops! All tasks failed - no EPUB could be created.")
        else:
            # Save EPUB
            epub_output_path = settings.output_dir / settings.input_file.name
            book.save_epub(epub_output_path)
            logger.info(f"💾 EPUB saved to {epub_output_path}")

        # 5. Cleanup
        if settings.cleanup:
            for payload in payload_list:
                payload.audio_output_file.unlink(missing_ok=True)    
        pass


def terminate_worker_processes(timeout: int = 1):
    """
    Gracefully terminate child processes (excluding resource_tracker), then force kill if needed.

    Args:
        timeout (int): Time to wait before force killing. Defaults to 1 second.
    """
    try:
        main_process = psutil.Process()
        children = main_process.children(recursive=True)
        worker_processes = [p for p in children if "multiprocessing.resource_tracker" not in " ".join(p.cmdline())]
        
        for child in worker_processes:
            logger.info(f"Terminating child process PID={child.pid}")
            child.terminate()  # grace kill
        
        gone, alive = psutil.wait_procs(worker_processes, timeout)
        for p in alive:
            logger.warning(f"Killing stubborn child process PID={p.pid}")
            p.kill()  # force kill
    except Exception as e:
        logger.exception("Error terminating children:")
        pass


def handle_signal(signum, frame):
    signal_name = signal.Signals(signum).name
    logger.warning(f"🔔 Received signal {signum} ({signal_name}), MainProcess exiting...")

    if executor:
        executor.shutdown(wait=False, cancel_futures=True) 
        # Cancel pending tasks and return immediately; running tasks still continue.
        
    terminate_worker_processes()
    sys.exit(1)


def setup_signal_handlers():
    signal.signal(signal.SIGINT, handle_signal)   # 监听 Ctrl+C （终端中断信号）
    signal.signal(signal.SIGTERM, handle_signal)  # 监听 SIGTERM（通常由 kill 命令或 subprocess.terminate() 发送）
    pass