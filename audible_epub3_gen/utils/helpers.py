import logging, math
from rapidfuzz import fuzz

from audible_epub3_gen.utils import logging_setup
from audible_epub3_gen.utils.types import WordBoundary, TagAlignment

logger = logging.getLogger(__name__)

def join_words(wb_list: list[WordBoundary], lang: str = "en") -> str:
    if lang[:2].lower() in ["zh", "ja", "ko"]:
        return "".join(wb.text for wb in wb_list)
    else:
        return " ".join(wb.text for wb in wb_list)

def normalize_text(s: str) -> str:
    return "".join(s.lower().split())

def force_alignment(sentences: list[str], word_boundaries: list[WordBoundary], threshold: float = 98.0) -> list[tuple[int, int]]:
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

    wb_texts = [normalize_text(wb.text) for wb in word_boundaries]
    result = []
    
    cur_offset = 0  # current starting index
    
    for sent_idx, sentence in enumerate(sentences):
        logger.debug(f"Matching sentence [{sent_idx}]: {sentence}")
        target_text = normalize_text(sentence) 
        best_score = -1
        best_match = None

        min_len = int(len(target_text) * 0.6)  # min window size
        max_len = int(len(target_text) * 1.4)  # max windows size

        for start in range(cur_offset, len(wb_texts)):
            buffer = ""
            char_len = 0

            for end in range(start, len(wb_texts)):
                buffer += wb_texts[end]
                char_len = len(buffer)

                if char_len > max_len:
                    break
                if char_len < min_len:
                    continue

                score = fuzz.ratio(buffer, target_text)
                # logger.debug(f"  [{sent_idx}] socre:{score:.3f}, target:[{target_text}], wbs:[{buffer}]")
                if score > best_score:
                    best_score = score
                    best_match = (start, end)
                if math.isclose(score, 100):
                    break  # early exit
            
            if best_score >= threshold:
                break  # early exit outer loop
        
        logger.debug(f"  [{sent_idx}] Best socre:{best_score:.3f}, target:[{target_text}], wbs:[{''.join(wbtext for wbtext in wb_texts[best_match[0]: best_match[1]+1])}]")
        
        if best_score >= threshold:
            if not math.isclose(best_score, 100):
                # Left-shift refinement
                logger.debug(f"Left-shift refinement [{sent_idx}]")
                start, end = best_match
                for new_start in range(start+1, end+1):
                    buffer = "".join(wb_texts[new_start: end+1])
                    char_len = len(buffer)
                    if char_len < len(target_text):
                        break
                    score = fuzz.ratio(buffer, target_text)
                    logger.debug(f"  [{sent_idx}] Left-shifted socre:{score:.3f}, target:[{target_text}], wbs:[{buffer}]")
                    if score > best_score:
                        best_score = score
                        best_match = (new_start, end)
                    else:
                        break

            result.append(best_match)
            cur_offset = best_match[1] + 1
        else:
            result.append((-1, -1))
            logger.warning(f"Alignment faild for sentence: {sentence} (best_score: {best_score:.3f}) (best_match: {''.join(wbtext for wbtext in wb_texts[best_match[0]: best_match[1]+1])})")
    
    return result