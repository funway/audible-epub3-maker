import logging
import re
import unicodedata

from audible_epub3_maker.config import in_dev
from audible_epub3_maker.utils import logging_setup

logger = logging.getLogger(__name__)
if not in_dev():
    logger.setLevel(max(logger.getEffectiveLevel(), logging.INFO))

DELIMITERS=set([
    '.', '?', '!', ',', ';',     # English
    '。', '？', '！', '，', '；',  # Chinese
])

DIALOG_CLOSING_PUNCTUATION = set([
    "'", '"',                  # English
    '’', '”', '」', '』', '】',  # Chinese
])

ABBRS_NON_TERMINAL = set(["Mr.", "Mrs.", "Ms.", "Dr.", "Prof."])
ABBRS_MAY_TERMINAL = set(["U.S.", "U.S.A.", "U.K.", "U.N.", "Inc.", "Ltd."])
ABBREVIATIONS = sorted(ABBRS_NON_TERMINAL | ABBRS_MAY_TERMINAL, key=len, reverse=True)

def replace_non_terminal_dot(text: str, replacement: str = "_DOT_") -> str:
    """Replaces non-terminal dots in the text with a specified replacement string.
    
    Args:
        text (str): The input text.
        replacement (str): The string to replace non-terminal dots with.
        
    Returns:
        str: The modified text with non-terminal dots replaced.
    """
    if not text:
        return text
    
    # 1. 替换 数字序列 中的点号
    while re.search(r'\d+\.\d+', text): # 只要还存在 "数字.数字" 模式就继续
        text = re.sub(r'(\d+)\.(\d+)', fr'\1{replacement}\2', text)
    logger.debug(f"Replaced numeric dots: \n{text}")

    def _abbr_replacer(match):
        total, abbr, next_char = match.group(0), match.group(1), match.group(2)
        suffix = total[len(abbr):]

        replaced_abbr = abbr.replace('.', replacement) if abbr in ABBRS_NON_TERMINAL else abbr[:-1].replace('.', replacement) + abbr[-1]
        
        if next_char is None or next_char in DIALOG_CLOSING_PUNCTUATION:
            replaced_abbr = abbr[:-1].replace('.', replacement) + abbr[-1]
        elif next_char.islower() and abbr in ABBRS_MAY_TERMINAL:
            replaced_abbr = abbr.replace('.', replacement)
        
        logger.debug(f"match: {total}, abbr: {abbr}, next_char: {next_char}, replaced_abbr: {replaced_abbr}")        
        return replaced_abbr + suffix

    # 2. 替换 缩写 中的点号
    abbr_pattern = r'(' + '|'.join(re.escape(abbr) for abbr in ABBREVIATIONS) + r')(?=\s*(\S)?)'
    text = re.sub(abbr_pattern, _abbr_replacer, text)
    logger.debug(f"Replaced common abbreviations dots: \n{text}")
    
    return text


def restore_non_terminal_dot(text: str, replacement: str = "_DOT_") -> str:
    """Restores dots in the text that were replaced by the specified replacement string.
    
    Args:
        text (str): The input text with replaced dots.
        replacement (str): The string that was used to replace dots.
        
    Returns:
        str: The modified text with dots restored.
    """
    return text.replace(replacement, '.')


def segment_text_by_re(text: str) -> list:
    """Segments text into sentences based on regular expressions.
    根据正则表达式对文本进行分句，并保留分隔符以及原始空格。
    规则包括:
    1. 西文 delimiters: .?!,;:
        - 数字和缩写的西文句号不应分句，比如 "v1.2.3" 或 "Dr. Smith"
    2. 中文 delimiters: 。？！，；：
    3. 连续的标点符号视为一个分句点
    4. 保留原有空格和换行符
    """
    if not text.strip():
        return [text]
    
    # 替换存在于 数字、缩写 中的点号，因为它们不是分句的标准
    text = replace_non_terminal_dot(text)

    reg_d = re.escape("".join(sorted(DELIMITERS)))
    reg_q = re.escape("".join(sorted(DIALOG_CLOSING_PUNCTUATION)))
    # split_pattern = r"([{d}][{q}])|([{d}])".format(d=reg_d, q=reg_q)
    split_pattern = r"(?<=[{d}])([{q}]?)".format(d=reg_d, q=reg_q)
    logger.debug(f"Using split pattern: {split_pattern}")

    raw_fragments = re.split(split_pattern, text)
    # logger.debug(f"Segmented text into {len(raw_fragments)} raw fragments: \n{raw_fragments}")
    
    res_fragments = []
    for fragment in raw_fragments:
        if not fragment:  # ignore empty fragment
            continue
        fragment = restore_non_terminal_dot(fragment)  # 还原先前被替换的点号
        
        is_delimiter_or_quote = len(fragment) == 1 and fragment in (DELIMITERS | DIALOG_CLOSING_PUNCTUATION)
        if is_delimiter_or_quote and res_fragments:
            res_fragments[-1] += fragment  # 如果当前片段是分隔符且上一个片段已经存在，则合并到上一个分句
        else:
            res_fragments.append(fragment)  # 否则认为该片段是一个分句
    
    # logger.debug(f"Segmented text into {len(res_fragments)} final fragments. \n{res_fragments}")
    return [f for f in res_fragments]


def is_readable(text: str) -> bool:
    """
    Checks if the text contains any readable characters (letters or numbers), supporting multiple languages.

    Args:
        text (str): The input text.

    Returns:
        bool: True if the text contains at least one readable character, False otherwise.
    """
    for ch in text:
        category = unicodedata.category(ch)
        if category.startswith(("L", "N")):
            return True
    return False


if __name__ == "__main__":
    from datetime import datetime
    # Example usage
    sample_text = "Dr. Smith#BK# went to the \nlab at 3.14 PM.\nMr. Wang said the project version is 1.2.3. Call U.S.A.   It's from U.S. Mr. Wang doesn't like it."
    text = ' "Oh! This is a test...""It\'s so hard!"他说。Another sentence! 比如 "v1.12.3" 或 "Dr. Smith"? '
    sample_text += text

    modified_text = replace_non_terminal_dot(sample_text)
    logger.debug(f"original: \n{sample_text}")
    logger.debug(f"replace dot: \n{modified_text}")  # Output: "Dr_DOT_ Smith went to the lab at 3_DOT_14 PM. The version is 1_DOT_2_DOT_3."
    logger.debug(f"restore dot: \n{restore_non_terminal_dot(modified_text)}")  # Output: "Dr. Smith went to the lab at 3.14 PM. The version is 1.2.3."

    # start = datetime.now()
    # segments = segment_text_by_re(sample_text)
    # end = datetime.now()
    # logger.debug(f"\n=== Segmented {len(segments)} sentences in {end - start} seconds. ===\n")
    # for i, segment in enumerate(segments, start=1):
    #     logger.debug(f"Segment {i}: {segment}")