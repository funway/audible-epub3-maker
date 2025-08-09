import logging, io
from pathlib import Path
from pydub import AudioSegment

from audible_epub3_maker.config import in_dev
from audible_epub3_maker.utils.types import WordBoundary

logger = logging.getLogger(__name__)


class BaseTTS(object):
    
    def __init__(self):
        super(BaseTTS, self).__init__()
        pass

    
    def html_to_speech(html_text: str, output_file: str, metadata):
        raise NotImplementedError
    
    
    @classmethod
    def download_model(cls, lang: str, voice: str):
        """
        Optional hook for subclasses to download model files (if needed)
        """
        pass

    
    @classmethod
    def merge_audios_and_word_boundaries(cls, 
                                         chunk_results: list[dict],
                                         key: str = "audio_file"
                                         ) -> tuple[AudioSegment, list[WordBoundary]]:
        """
        Merges multiple audio chunks and their corresponding word boundaries into a single audio stream
        and a unified word boundary list with adjusted timestamps.

        Args:
            chunk_results: List of dicts with:
                - `key`: key_name poins to the WAV data (e.g., 'audio_file' or 'audio_data')
                - 'wbs': list of WordBoundary
            key: Key_name in each chunk dict pointing to WAV data (file Path or BytesIO)

        Returns:
            - merged_audio: Combined AudioSegment
            - merged_wbs: List of WordBoundary with updated start/end times
        """
        merged_audio = AudioSegment.empty()
        merged_wbs = []
        current_offset = 0.0

        for idx, chunk in enumerate(chunk_results):
            audio_file = chunk[key]
            wbs: list[WordBoundary] = chunk["wbs"]

            # 1. Merge audio
            # AudioSegment.from_file 支持读取文件，也支持读取 file-like 对象 (BytesIO)
            audio = AudioSegment.from_file(audio_file, format="wav")
            merged_audio += audio
            
            # 2. Merge and shift word boundaries
            for wb in wbs:
                adjusted_wb = WordBoundary(
                    start_ms = wb.start_ms + current_offset,
                    end_ms = wb.end_ms + current_offset,
                    text = wb.text,
                )
                merged_wbs.append(adjusted_wb)
            
            # 3. Update offset
            current_offset += len(audio)
            logger.debug(f"Audio [{idx}] {audio_file}: duration = {len(audio)}ms")
        
        logger.debug(f"Total merged audio duration (calculated): {current_offset}ms")
        return merged_audio, merged_wbs
    

    @classmethod
    def merge_audios(cls, audio_files: list[Path | io.BytesIO]) -> AudioSegment:
        """
        Merges a list of audio files (WAV format) into a single AudioSegment.

        Args:
            audio_files: List of audio inputs, each being either:
                      - a Path to a WAV file
                      - or a BytesIO object containing WAV data

        Returns:
            AudioSegment: The concatenated audio segment.
        """
        merged_audio = AudioSegment.empty()
        for idx, audio_file in enumerate(audio_files):
            audio = AudioSegment.from_file(audio_file, format="wav")
            merged_audio += audio
            logger.debug(f"Audio [{idx}] {audio_file}: duration = {len(audio)}ms")

        logger.debug(f"Total merged audio duration: {len(merged_audio)}ms")
        return merged_audio
    

    @classmethod
    def save_audio(cls, audio: AudioSegment, output_file: Path, metadata: dict|None = None):
        """
        Save an AudioSegment to a file, with optional metadata.

        Supports .mp3 and .wav formats. Falls back to .mp3 if unsupported.
        """
        metadata = metadata or {}

        export_format = output_file.suffix.lower().lstrip('.') or "mp3"
        if export_format not in ["wav", "mp3"]:
            logger.warning(f"Unsupported output format '{export_format}', falling back to 'mp3'")
            export_format = "mp3"
        
        audio.export(str(output_file), format=export_format, tags=metadata)
        logger.debug(f"Audio saved to {output_file}")

        # check audio time length
        if in_dev():
            final_audio = AudioSegment.from_file(output_file, format=export_format)
            logger.debug(f"Final audio duration (actual): {len(final_audio)}ms")