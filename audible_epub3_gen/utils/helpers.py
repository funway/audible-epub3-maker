import logging, math, json, os, sys
import requests
from pathlib import Path
from rapidfuzz import fuzz
from dataclasses import asdict

from audible_epub3_gen.config import settings, AZURE_TTS_KEY, AZURE_TTS_REGION
from audible_epub3_gen.utils import logging_setup
from audible_epub3_gen.utils.types import WordBoundary

logger = logging.getLogger(__name__)

def is_char_based_language(lang: str) -> bool:
    """Languages like Chinese, Japanese, Korean treat one char as one word."""
    return lang[:2].lower() in ["zh", "ja", "ko"]


def normalize_text(s: str) -> str:
    return "".join(s.lower().split())


def save_wbs_as_json(word_boundaries: list[WordBoundary], output_file: Path):
    output_file = Path(output_file)
    
    with output_file.open("w", encoding="utf-8") as wbs_output:
        json.dump([asdict(wb) for wb in word_boundaries], wbs_output, ensure_ascii=False, indent=2)
        logger.debug(f"Wrote {len(word_boundaries)} word boundaries to {output_file}")
    pass


def force_alignment(sentences: list[str], word_boundaries: list[WordBoundary], threshold: float = 95.0) -> list[tuple[int, int]]:
    """
    Aligns each sentence in `sentences` to a best-matching span of word boundaries using fuzzy string matching.

    This function attempts to find, for each sentence, the most likely corresponding subsequence of `word_boundaries`
    such that the concatenated words (with no spaces) are approximately equal to the normalized sentence (also with no spaces).
    
    Matching is performed using fuzzy matching (`fuzz.ratio`), and spans whose similarity score exceeds the `threshold`
    are accepted. If multiple spans match, the best-scoring one is selected. After alignment, a left-side boundary refinement
    is applied to improve alignment accuracy by shifting the start index to the fixed right if it yields a better score.

    Args:
        sentences (list[str]): A list of segmented sentences in text form.
        word_boundaries (list[WordBoundary]): A list of word boundary objects, assumed to be in correct order.
        threshold (float): Minimum fuzzy match score (0-100) required to accept a match. Default is 98.0.

    Returns:
        list[tuple[int, int]]: A list of `(start_index, end_index)` tuples corresponding to the indices in 
        `word_boundaries` that best align with each sentence. If a sentence cannot be aligned, `(-1, -1)` is returned for that entry.

    Notes:
        - Matching is case-insensitive and ignores all whitespace.
        - `normalize_text()` is used on both sentences and word texts to standardize content.
        - Alignment is greedy and advances `cur_offset` after each sentence match.
        - Assumes sentences and word boundaries are in correct temporal/textual order.
    """
    result = []

    wb_texts = [normalize_text(wb.text) for wb in word_boundaries]
    wb_chars = "".join(wb_texts)
    wb_cumulative_chars_offsets = [0]
    for wb_text in wb_texts:
        wb_cumulative_chars_offsets.append(wb_cumulative_chars_offsets[-1] + len(wb_text))
    
    sent_texts = [normalize_text(sent) for sent in sentences]
    sent_chars = "".join(sent_texts)
    sent_cumulative_chars_offsets = [0]  # each sentence's chars offset in all sentences normalized char stream.
    
    cur_wb_start_idx = 0  # current starting index in word boundaries
    unmatched_sent_chars = 0

    for sent_idx, sent in enumerate(sentences):
        logger.debug(f"Matching sentence [{sent_idx}]: {sent}")
        target_text = sent_texts[sent_idx]
        target_text_len = len(target_text)
        sent_cumulative_chars_offsets.append(sent_cumulative_chars_offsets[-1] + target_text_len)
        
        best_score = -1
        best_match = (0, -1)

        # sliding window's size range in chars
        min_len = int(target_text_len * 0.6) if target_text_len < 50 else int(target_text_len * 0.8)
        max_len = int(target_text_len * 1.4) if target_text_len < 50 else int(target_text_len * 1.2)
        max_len = max(max_len, 5)

        # max starting position in chars
        max_start_shift = 5 if is_char_based_language(settings.tts_lang) else 10
        max_start_pos = wb_cumulative_chars_offsets[cur_wb_start_idx] + unmatched_sent_chars + max_start_shift

        for start in range(cur_wb_start_idx, len(wb_texts)):
            if wb_cumulative_chars_offsets[start] > max_start_pos:
                logger.debug(f"  Start too far ahead of last matched position ({wb_texts[cur_wb_start_idx]} -> {unmatched_sent_chars + max_start_shift}). quit sliding.")
                break  # Start too far ahead of target sentence position

            buffer = ""
            buffer_len = 0
            for end in range(start, len(wb_texts)):
                buffer += wb_texts[end]
                buffer_len = len(buffer)

                if buffer_len > max_len:
                    break
                if buffer_len < min_len:
                    continue

                score = fuzz.ratio(buffer, target_text)
                logger.debug(f"  [{sent_idx}] score:{score:.3f}, target:[{target_text}], wbs:[{buffer}]")
                if score > best_score:
                    best_score = score
                    best_match = (start, end)
                if math.isclose(score, 100):
                    break  # early exit
            
            if best_score >= threshold:
                break  # early exit outer loop
        
        if best_score >= threshold:
            if not math.isclose(best_score, 100):
                # Left-shift refinement
                logger.debug(f"Left-shift refinement [{sent_idx}]")
                start, end = best_match
                for new_start in range(start+1, end+1):
                    buffer = "".join(wb_texts[new_start: end+1])
                    buffer_len = len(buffer)
                    if buffer_len < len(target_text):
                        break
                    score = fuzz.ratio(buffer, target_text)
                    logger.debug(f"  [{sent_idx}] Left-shifted score:{score:.3f}, target:[{target_text}], wbs:[{buffer}]")
                    if score > best_score:
                        best_score = score
                        best_match = (new_start, end)
                    else:
                        break
            
            result.append(best_match)
            cur_wb_start_idx = best_match[1] + 1
            unmatched_sent_chars = 0  # reset
            logger.debug(f"Alignment success for sentence: [{sent}] (best_score: {best_score:.3f}) (best_match: {''.join(wbtext for wbtext in wb_texts[best_match[0]: best_match[1]+1])})")
        else:
            result.append((-1, -1))
            unmatched_sent_chars += target_text_len
            logger.warning(f"Alignment faild for sentence: [{sent}] (best_score: {best_score:.3f}) (best_match: {''.join(wbtext for wbtext in wb_texts[best_match[0]: best_match[1]+1])})")
    
    return result


def get_langs_voices_azure(subscription_key: str, region: str) -> dict[str, list[str]]:
    """
    获取 Azure TTS 支持的语言与语音，并返回格式如下：
    {
        "en-US": ["en-US-JennyNeural", "en-US-GuyNeural", ...],
        "zh-CN": ["zh-CN-XiaoxiaoNeural", ...],
        ...
    }
    """
    url = f"https://{region}.tts.speech.microsoft.com/cognitiveservices/voices/list"
    headers = {
        "Ocp-Apim-Subscription-Key": subscription_key
    }

    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        voices = response.json()
    except requests.RequestException as e:
        raise RuntimeError("Failed to fetch voices from Azure API") from e

    langs_voices = {}
    for voice in voices:
        locale = voice.get("Locale")
        short_name = voice.get("ShortName")

        if locale and short_name:
            langs_voices.setdefault(locale, []).append(short_name)

    return langs_voices


def get_langs_voices_kokoro():
    pass


def validate_tts_settings():
    if "azure" == settings.tts_engine:
        langs_voices = get_langs_voices_azure(AZURE_TTS_KEY, AZURE_TTS_REGION)
        langs_voices_lowers = {
            lang.lower(): [v.lower() for v in voices]
            for lang, voices in langs_voices.items()
        }
        # 检查语言是否受支持
        if settings.tts_lang.lower() not in (k.lower() for k in langs_voices_lowers):
            logger.debug(f"TTS language '{settings.tts_lang}' not supported by Azure TTS.")
            raise ValueError(f"Azure TTS does not support language: {settings.tts_lang}")

        # 检查声音是否在该语言中受支持
        if settings.tts_voice.lower() not in langs_voices_lowers[settings.tts_lang.lower()]:
            logger.debug(f"TTS voice '{settings.tts_voice}' not supported for language '{settings.tts_lang}' in Azure TTS.")
            raise ValueError(
                f"Azure TTS does not support voice '{settings.tts_voice}' for language '{settings.tts_lang}'"
            )

    elif "kokoro" == settings.tts_engine:
        raise NotImplementedError()
    

def validate_settings():

    if not settings.input_file or not settings.input_file.is_file():
        raise FileNotFoundError(f"Input file not found: {settings.input_file}")
    
    if settings.input_file.suffix.lower() != ".epub":
        raise ValueError(f"Input file must be an EPUB file (.epub), got: {settings.input_file.name}")
    
    try:
        settings.output_dir.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        raise PermissionError(f"Cannot create or access output directory: {settings.output_dir}") from e

    if not os.access(settings.output_dir, os.W_OK):
        raise PermissionError(f"Output directory is not writable: {settings.output_dir}")

    validate_tts_settings()
    pass


def confirm_or_exit(msg: str):
    if settings.force:
        logger.debug(f"{msg} → [force-confirm] proceeding without prompt.")
        print(f"{msg} → [force-confirm] proceeding without prompt.")
        return
    
    ans = input(f"{msg} [y/n]: ").strip().lower()
    if ans != 'y':
        logger.debug(f"{msg} → Aborted by user.")
        print("Aborted by user.")
        sys.exit(1)


def test_mp(chapter):
    logger.debug(f"测试 mp: {type(chapter)}, {chapter.href}")
    logger.debug(f"当前 settings: {settings.__dict__}")
    pass