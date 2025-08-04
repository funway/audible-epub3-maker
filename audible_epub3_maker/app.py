import logging, time
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor, as_completed
from multiprocessing import Queue, current_process

from audible_epub3_maker.config import settings
from audible_epub3_maker.utils import helpers
from audible_epub3_maker.utils import logging_setup
from audible_epub3_maker.utils.constants import BASE_DIR, APP_FULLNAME, AUDIO_MIMETYPES
from audible_epub3_maker.utils.types import TaskPayload
from audible_epub3_maker.epub.epub_book import EpubBook, EpubHTML, EpubAudio, LazyLoadFromFile, EpubSMIL
from audible_epub3_maker.segmenter.html_segmenter import html_segment_and_wrap
from audible_epub3_maker.worker import init_worker, task_fn_wrap

logger = logging.getLogger(__name__)

class App(object):
    """docstring for App."""
    
    def __init__(self):
        super(App, self).__init__()
        pass
    
    def run(self):
        helpers.validate_settings()
        logger.info(f"⚙️ Settings: {settings.to_dict()}")
        
        book = EpubBook(settings.input_file)
        logger.info(f"📕 EPUB Book Info: title = [{book.title}], identifier = [{book.identifier}], language = [{book.language}]")
        print(f"📕 EPUB Book Info: title = [{book.title}], identifier = [{book.identifier}], language = [{book.language}]")

        if book.language != settings.tts_lang:
            msg = (
                f"⚠️ EPUB language ({book.language}) does not match TTS language setting ({settings.tts_lang}).\n"
                f"Do you want to continue using TTS language '{settings.tts_lang}'?"
            )
            helpers.confirm_or_exit(msg)

        chapters = book.get_chapters()
        task_payloads: list[TaskPayload] = []
        for idx, chapter in enumerate(chapters):
            # logger.debug(f"chatper [{idx}/{len(chapters)}]: {chapter.id}, {chapter.href}")
            # segmented_html = html_segment_and_wrap(chapter.get_text())
            
            chapter_filename = Path(chapter.href).stem  # filename, not real content Chapter
            chapter_audio_output_file = settings.output_dir / f"{book.identifier}_aud{idx}.mp3"
            chapter_audio_metadata = {
                "title": f"{book.title} - {chapter_filename}",
                "album": book.epub_path.stem,
                "publisher": APP_FULLNAME,
            }

            task_payloads.append(TaskPayload(task_id=idx,
                                             html_text=chapter.get_text(),
                                             audio_output_file=chapter_audio_output_file,
                                             audio_metadata=chapter_audio_metadata,
                                             ))
            pass
        
        # Dispatch tasks and wait for completion
        print(f"🚀 Start processing {settings.input_file} ...")
        start_time = time.perf_counter()
        with ProcessPoolExecutor(max_workers=min(settings.max_workers, len(chapters)),
                                 initializer=init_worker,
                                 initargs=(settings.to_dict(),
                                           logging_setup.get_log_queue(), 
                                           )
                                 ) as executor:
            # # executor.map returns a lazy iterator
            # results = executor.map(task_fn_wrap, task_payloads)
            future_to_task_id = {}
            futures = []

            for payload in task_payloads:
                future = executor.submit(task_fn_wrap, payload)
                futures.append(future)
                future_to_task_id[future] = payload.task_id
            
            for future in as_completed(futures):
                try:
                    success, task_result = future.result()
                except Exception as e:
                    task_id = future_to_task_id[future]
                    logger.exception(f"⛔ Unexpected executor-level error for task {task_id}: {e}")
                    continue

                if success:
                    logger.info(f"✅ [Task {task_result.task_id}] complete. {task_result}")
                    
                    # 0. Get the corresponding chapter item
                    chapter: EpubHTML = chapters[task_result.task_id]

                    # 1. Add audio to EPUB
                    aud_id = f"aud_{task_result.task_id}"
                    aud_suffix = task_result.audio_file.suffix
                    aud_href = f"audio/{aud_id}{aud_suffix}"
                    audio_item = EpubAudio(raw_content = LazyLoadFromFile(task_result.audio_file),
                                           id = aud_id,
                                           href = aud_href,
                                           media_type = AUDIO_MIMETYPES[aud_suffix]
                                           )
                    book.add_item(audio_item)

                    # 2. Add SMIL
                    smil_href = str(chapter.href) + ".smil"
                    smil_text = helpers.generate_smil_content(smil_href, chapter.href, aud_href, task_result.alignments)
                    smil_id = f"sm_{task_result.task_id}"
                    smil_item = EpubSMIL(raw_content = smil_text.encode(),
                                         id = smil_id,
                                         href = smil_href,
                                         media_type = "application/smil+xml",
                                         )
                    book.add_item(smil_item)

                    # 3. Update the corresponding chapter item
                    chapter.attrs["media-overlay"] = smil_id  # Add overlay property 
                    chapter.set_text(task_result.taged_html)  # Modify HTML text
                else:
                    logger.error(f"❌ [Task {task_result.payload.task_id}] failed. {task_result}")
            
        # Save EPUB
        epub_output_path = settings.output_dir / settings.input_file.name
        book.save_epub(epub_output_path)

        # Cleanup
        if settings.cleanup:
            for payload in task_payloads:
                payload.audio_output_file.unlink(missing_ok=True)    

        elapsed = time.perf_counter() - start_time
        logger.info(f"🎉 Processing complete. EPUB saved to {epub_output_path} (finished in {helpers.format_seconds(elapsed)})")
        print(f"🎉 Processing complete. EPUB saved to {epub_output_path} (finished in {helpers.format_seconds(elapsed)})")
        pass