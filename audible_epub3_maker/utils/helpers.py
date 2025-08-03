import logging, math, json, os, sys
import requests
from html import escape
from pathlib import Path
from rapidfuzz import fuzz
from dataclasses import asdict

from audible_epub3_maker.config import settings, AZURE_TTS_KEY, AZURE_TTS_REGION, in_dev
from audible_epub3_maker.utils import logging_setup
from audible_epub3_maker.utils.types import WordBoundary, TagAlignment
from audible_epub3_maker.utils.constants import DEV_OUTPUT

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


def align_sentences_and_wordboundaries(sentences: list[str], 
                                       word_boundaries: list[WordBoundary], 
                                       threshold: float = 95.0, 
                                       aligns_output_file: Path | None = None) -> list[tuple[int, int]]:
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
        threshold (float): Minimum fuzzy match score (0-100) required to accept a match. Default is 95.0.
        aligns_output_file (Path | None): Path to save force alignment debug output (used only in development).

    Returns:
        list[tuple[int, int]]: A list of `(start_index, end_index)` tuples corresponding to the indices in 
        `word_boundaries` that best align with each sentence in `sentences` list. If a sentence cannot be aligned, `(-1, -1)` is returned for that entry.

    Notes:
        - Matching is case-insensitive and ignores all whitespace.
        - `normalize_text()` is used on both sentences and word texts to standardize content.
        - Alignment is greedy and advances `cur_offset` after each sentence match.
        - Assumes sentences and word boundaries are in correct temporal/textual order.
    """
    result = [(-1, -1)] * len(sentences)
    dev_output = []

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
    matched_counter = 0

    for sent_idx, sent in enumerate(sentences):
        # logger.debug(f"Matching sentence [{sent_idx}]: {sent}")
        dev_output.append(f"Matching sentence [{sent_idx}]: {sent}")
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
                # logger.debug(f"  Start too far ahead of last matched position ({wb_texts[cur_wb_start_idx]} -> {unmatched_sent_chars + max_start_shift}). quit sliding.")
                dev_output.append(f"  [{sent_idx}] Start too far ahead of last matched position ({wb_texts[cur_wb_start_idx]} -> {unmatched_sent_chars + max_start_shift}). quit sliding.")
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
                # logger.debug(f"  [{sent_idx}] score:{score:.3f}, target:[{target_text}], wbs:[{buffer}]")
                dev_output.append(f"  [{sent_idx}] score:{score:.3f}, target:[{target_text}], wbs:[{buffer}]")
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
                dev_output.append(f"  [{sent_idx}] Left-shift refinement. (current best_score: {best_score:.3f})")
                start, end = best_match
                for new_start in range(start+1, end+1):
                    buffer = "".join(wb_texts[new_start: end+1])
                    buffer_len = len(buffer)
                    if buffer_len < len(target_text):
                        break
                    score = fuzz.ratio(buffer, target_text)
                    # logger.debug(f"  [{sent_idx}] Left-shifted score:{score:.3f}, target:[{target_text}], wbs:[{buffer}]")
                    dev_output.append(f"  [{sent_idx}] Left-shifted score:{score:.3f}, target:[{target_text}], wbs:[{buffer}]")
                    if score > best_score:
                        best_score = score
                        best_match = (new_start, end)
                    else:
                        break
            
            result[sent_idx] = best_match
            cur_wb_start_idx = best_match[1] + 1
            unmatched_sent_chars = 0  # reset unmatched chars
            matched_counter += 1
        else:
            result[sent_idx] = (-1, -1)
            unmatched_sent_chars += target_text_len  # increase unmatched chars
            
        match_status = "success" if result[sent_idx][1] >= 0 else "failed"
        best_match_words = "".join(wb_texts[best_match[0]: best_match[1]+1])
        dev_output.append(f"  Alignment {match_status} for sentence [{sent_idx}]: [{sent}]\n"
                          f"  best_score: {best_score:.3f}, match: {best_match}, words: [{best_match_words}]")
        logger.debug(dev_output[-1])

    if in_dev() and aligns_output_file:
        # save alignments data in development env.
        dev_output.append(f"\n📊 Total sentences: {len(sentences)}, Matched sentences: {matched_counter}, Word boundaries: {len(word_boundaries)}")
        aligns_output_file.write_text("\n".join(dev_output))

    return result

def force_alignment(taged_sentences: list[tuple[str, str]], 
                    word_boundaries: list[WordBoundary], 
                    threshold: float = 95.0,
                    aligns_output_file: Path | None = None) -> list[TagAlignment]:
    """
    Generate a list of TagAlignment objects for EPUB Media Overlay (SMIL) playback.

    In EPUB Media Overlays, <par> elements are played in sequence, and any gap between
    adjacent audio segments will will cause a playback jump, skipping the unaligned time range. 
    To ensure smooth playback, this function guarantees time continuity by adjusting alignments so that:
        
        `alignment[i].end_ms == alignment[i+1].start_ms`
    
    Args:
        taged_sentences (list[(tag_id, tag_text)]): A list of (tag_id, tag_text) in tuple form.
        word_boundaries (list[WordBoundary]): A list of word boundary objects, assumed to be in correct order.
        threshold (float): Minimum fuzzy match score (0-100) required to accept a match. Default is 95.0.
        aligns_output_file (Path | None): Path to save force alignment debug output (used only in development).
    """
    sentences = [idx_sent[1] for idx_sent in taged_sentences]
    raw_aligns = align_sentences_and_wordboundaries(sentences, 
                                                    word_boundaries, 
                                                    threshold, 
                                                    aligns_output_file.with_suffix(".raw.txt") if aligns_output_file else None)
    alignments: list[TagAlignment] = []
    
    unmatched_counter = 0
    unmatched_groups = []
    unmatched_group = []
    unmatched_chars = 0
    for idx, (tag_id, sentence) in enumerate(taged_sentences):
        start_wb, end_wb = raw_aligns[idx]
        
        if end_wb < 0:
            # Sentence failed to align — store in group for later interpolation
            unmatched_counter += 1
            unmatched_group.append(idx)
            unmatched_chars += len(sentence)
            alignments.append(TagAlignment(tag_id=tag_id, start_ms=-1, end_ms=-1))  # placeholder
        else:
            start_ms = word_boundaries[start_wb].start_ms
            end_ms = word_boundaries[end_wb].end_ms
            alignments.append(TagAlignment(tag_id=tag_id, start_ms=start_ms, end_ms=end_ms))        
        
            if unmatched_group:
                # 1. Collect unmatched_group
                unmatched_groups.append( (unmatched_group, unmatched_chars) )

                # 2. Flush previously unmatched group
                unmatched_group = []
                unmatched_chars = 0
    
    # Interpolate alignment spans for unmatched sentences
    for gp, gp_chars in unmatched_groups:
        gp_start_idx = gp[0]
        gp_end_idx = gp[-1]
        gp_start_ms = alignments[gp_start_idx-1].end_ms if gp_start_idx > 0 else word_boundaries[0].start_ms
        gp_end_ms = alignments[gp_end_idx+1].start_ms if (gp_end_idx+1) < len(alignments) else word_boundaries[-1].end_ms
        gp_total_ms = gp_end_ms - gp_start_ms
        cur_offset_ms = 0
        for idx in gp:
            alignments[idx].start_ms = gp_start_ms + cur_offset_ms
            idx_ms = gp_total_ms * len(taged_sentences[idx][1]) / gp_chars
            alignments[idx].end_ms = alignments[idx].start_ms + idx_ms
            cur_offset_ms += idx_ms 
        pass

    # Ensure continuous playback: a[i].end_ms == a[i+1].start_ms
    for i in range(len(alignments) - 1):
        alignments[i].end_ms = alignments[i+1].start_ms

    total_counter = len(alignments)
    match_counter = total_counter - unmatched_counter
    logger.debug(
        f"[FA] Matched alignments: {match_counter}/{total_counter} ({match_counter / total_counter:.1%}), "
        f"Interpolated alignments: {unmatched_counter}/{total_counter} ({unmatched_counter / total_counter:.1%})"
    )

    # save force alignment info
    if in_dev() and aligns_output_file:
        align_map: dict[str, TagAlignment] = {align.tag_id: align for align in alignments}
        
        with aligns_output_file.open("w", encoding="utf-8") as f:
            for idx, (tag_id, sentence) in enumerate(taged_sentences):
                align = align_map.get(tag_id)
                if align:
                    f.write(f"sentence [{idx}]: {align} [{sentence}]\n")
                else:
                    f.write(f"sentenct [{idx}]: <NO ALIGN FOUND> [{sentence}]")
            f.write(f"\n📊 {len(sentences)} sentences, {len(alignments)} alignments, {match_counter} matched, {unmatched_counter} interpolated.")
        pass

    return alignments


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
        # raise NotImplementedError()
        pass
    

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


def format_smil_time(ms: float) -> str:
    total_seconds = int(ms // 1000)
    milliseconds = int(ms % 1000)
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    seconds = total_seconds % 60
    return f"{hours}:{minutes:02}:{seconds:02}.{milliseconds:03}"


def format_seconds(seconds: float) -> str:
    seconds = int(round(seconds))
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)

    parts = []
    if hours > 0:
        parts.append(f"{hours}h")
    if minutes > 0 or hours > 0:
        parts.append(f"{minutes}m")
    parts.append(f"{secs}s")
    return " ".join(parts)


def generate_smil_content(smil_href: str, xhtml_href: str, audio_href: str, alignments: list[TagAlignment]) -> str:
    """
    Generates a SMIL XML content for EPUB 3 Media Overlay.

    Args:
        smil_href (str): The href of the SMIL file (relative to EPUB root).
        xhtml_href (str): Relative path to the XHTML file (e.g., "text/ch1.xhtml").
        audio_href (str): Relative path to the MP3 file (e.g., "audio/ch1.mp3").
        alignments (list of TagAlignment): Each item links an HTML tag to an audio time span.

    Returns:
        str: A string of SMIL XML content.
    """
    smil_lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<smil xmlns="http://www.w3.org/ns/SMIL" xmlns:epub="http://www.idpf.org/2007/ops" version="3.0">',
        '  <body>',
        '    <seq>'
    ]

    for idx, align in enumerate(alignments, start=1):
        smil_dir = Path(smil_href).parent
        xhtml_rel = os.path.relpath(xhtml_href, start=smil_dir)
        audio_rel = os.path.relpath(audio_href, start=smil_dir)
        
        text_src   = f"{escape(xhtml_rel)}#{escape(align.tag_id)}"
        audio_src  = escape(audio_rel)
        clip_begin = format_smil_time(align.start_ms)
        clip_end   = format_smil_time(align.end_ms)

        smil_lines += [
            f'      <par id="p{idx:05d}">',
            f'        <text src="{text_src}"/>',
            f'        <audio src="{audio_src}" clipBegin="{clip_begin}" clipEnd="{clip_end}"/>',
            f'      </par>'
        ]

    smil_lines += [
        '    </seq>',
        '  </body>',
        '</smil>'
    ]

    return "\n".join(smil_lines)


def format_bytes(size_bytes: int) -> str:
    """
    Converts a file size in bytes to a human-readable string.
    
    Args:
        size_bytes (int): File size in bytes.
    
    Returns:
        str: Formatted file size (e.g., '2.34 MB').
    """
    units = ["B", "KB", "MB", "GB", "TB"]
    size = float(size_bytes)
    for unit in units:
        if size < 1024:
            return f"{size:.2f} {unit}"
        size /= 1024
    return f"{size:.2f} PB"


def save_text(text: str, file_path: Path, encoding: str = "utf-8"):
    if not file_path.parent.exists():
        raise FileNotFoundError(f"Directory does not exist: {file_path.parent}")
    
    file_path.write_text(text, encoding=encoding)