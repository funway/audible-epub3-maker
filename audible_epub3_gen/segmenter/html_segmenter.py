import re
import logging
from bs4 import BeautifulSoup, Tag, NavigableString

from audible_epub3_gen.utils import logging_setup
from audible_epub3_gen.config import BEAUTIFULSOUP_PARSER
from audible_epub3_gen.segmenter.text_segmenter import segment_text_by_re, is_readable

logger = logging.getLogger(__name__)

NEW_TAG_ATTR_ID_PREFIX = "ae"
NEW_TAG_ATTR_MARK = "data-ae-x"

def get_hierarchy_name(tag: Tag) -> str:
    """Returns a string representation of the tag's hierarchy."""
    hierarchy = []
    while tag:
        hierarchy.append(tag.name)
        tag = tag.parent
    return " > ".join(reversed(hierarchy))

def wrap_text_in_tag(soup: BeautifulSoup, text: str, wrapping_tag: str = "span", attrs: dict | None = None) -> Tag:
    """Wraps the given text in a new tag with specified attributes.

    Args:
        soup (BeautifulSoup): The BeautifulSoup object used to create new tags.
        text (str): The text to wrap.
        wrapping_tag (str): The name of the tag to wrap the text in.
        attrs (dict, optional): Attributes to set on the new tag.

    Returns:
        Tag: The newly created tag containing the text.
    """
    assert isinstance(soup, BeautifulSoup), "soup must be a BeautifulSoup instance"
    tag = soup.new_tag(name=wrapping_tag, attrs=attrs)
    tag.string = text
    return tag

def _segment_node(soup: BeautifulSoup, node: Tag, wrapping_tag: str = "span", wrapping_tag_attrs: dict | None = None) -> None:
    """
    Recursively processes an HTML node, segmenting its text content into readable fragments and wrapping each fragment in a new tag.
    For each child node:
        - NavigableString children are split into fragments, which are either wrapped in a tag or kept as-is based on readability.
        - Tag children are processed recursively.
        - Other types of children are preserved.
    The node's contents are replaced with the newly processed children.
    """
    
    logger.debug(f"Processing Node: {get_hierarchy_name(node)}")
    logger.debug(f"  {get_hierarchy_name(node)}'s original contents [{len(node.contents)}]: {node.contents}")
    new_contents = []

    for child in node.contents:
        if type(child) is NavigableString:
            text = str(child)
            if text.strip():
                logger.debug(f"  Handle NavigableString:【{text[:10]}{' ...' if len(text) > 10 else ''}】")
                # 对文本进行分句，每个分句包裹到一个新的 wrap_tag 标签中，然后加入到 new_contents
                fragments = segment_text_by_re(text)
                for fragment in fragments:
                    if is_readable(fragment):
                        # append as a new tag
                        new_tag = wrap_text_in_tag(soup, fragment, wrapping_tag, wrapping_tag_attrs)
                        new_contents.append(new_tag)
                    else:
                        # append as NavigableString
                        new_contents.append(fragment)
            else:
                logger.debug("  Keep empty NavigableString child")
                new_contents.append(child)  # 保留空白的 NavigableString
        elif isinstance(child, Tag):
            logger.debug(f"  Handle Tag: {get_hierarchy_name(child)}")
            _segment_node(soup, child, wrapping_tag, wrapping_tag_attrs)
            new_contents.append(child)  # don't forget processed child
        else:
            logger.debug(f"  Keep unknown type child: {type(child)}")
            new_contents.append(child)
    
    logger.debug(f"  {get_hierarchy_name(node)}'s new contents [{len(new_contents)}]: {new_contents}")
    
    # TODO: 定义一个 contents_smooth 函数，将新 contents 中超短的 <span> 或者 NavigableString 并入前后 span

    node.clear()
    for child in new_contents:
        node.append(child)
    
    return

def _append_suffix_inside(tag: Tag, suffix: str):
    # append suffix to the last no-empty NavigableString child of the tag
    for elem in reversed(tag.find_all(string=True)):
        if elem.strip():
            elem.replace_with(elem + suffix)
            return
    # fallback
    tag.append(suffix)

def append_suffix_to_tags(html_text: str, suffix_map: dict[str, str], inside: bool = False) -> str:
    soup = BeautifulSoup(html_text, BEAUTIFULSOUP_PARSER)
    for tag_name, suffix in suffix_map.items():
        tags = soup.find_all(tag_name)
        for tag in tags:
            # Skip empty tags
            if not tag.text.strip():
                continue
            
            if inside:
                _append_suffix_inside(tag, suffix)
            else:
                tag.insert_after(suffix)
    return str(soup)

# TODO: 先分句，得到 text_segments, 然后再去原 html 中匹配每个分句进行切分。
def html_segment_and_wrap2(html_text: str, wrapping_tag: str = "span") -> str:
    """
    1. 先用 append_suffix_to_tags 给 html_text 中的 <h1> <h2> <h3> <h4> <h5> <h6> <li> <p> 等标签添加 break 标记。
    2. 再将 html_text 转换为纯文本，使用 segment_text_by_re 分句。
    3. 对每个分句，根据可能存在的 break 标记再切分 (避免 <h1> 标签这些标签因为没有标点符号做结尾导致无法被 segment_text_by_re 切分。其实这个可能都不用做，后面根据遇到的结束标签是 </h1></h2> 还是 </i> 来判断是否添加分句)。
    4. 再对每个过长的分句，判断是否有 and, or 等连接词，如果有则将其切分成更小的片段。
    # 然后下面就是开始匹配 html 了
    5. 使用流式处理 html_text 字符串, 跳过 < > 符号包裹的标签字符串，遇到跟 segment 相同的文本，将其包裹在 wrapping_tag 中。
       先不管<wrapping_tag> 中是否有未闭合的标签。
    6. 检查修改后的 html_text, 处理跟 <wrapping_tag> 有交叉的标签。
    """
    final_segments = []
    soup = BeautifulSoup(html_text, BEAUTIFULSOUP_PARSER)
    body = soup.body or soup
    if isinstance(body, BeautifulSoup):
        logger.warning(f"No body element found in the input text.")
    
    segments = segment_text_by_re(body.get_text("_#BRK#"))
    logger.debug(f"segments with brk: \n{segments}")
    for seg in segments:
        breaked_seg = seg.split("_#BRK#")
        final_segments.extend(breaked_seg)
    
    # break_map = {
    #     "h1": "_#BRK1_",
    #     "h2": "_#BRK2_",
    #     "h3": "_#BRK3_",
    #     "h4": "_#BRK4_",
    #     "h5": "_#BRK5_",
    #     "h6": "_#BRK6_",
    #     "li": "_#BRK4_",
    #     "p" : "_#BRK3_",
    # }
    # breaked_html = append_suffix_to_tags(html_text, break_map)
    # text_segments = segment_text_by_re(BeautifulSoup(breaked_html, BEAUTIFULSOUP_PARSER).get_text())
    
    # break_pattern = re.compile(r"_#BRK\d+_")
    # for segment in text_segments:
    #     small_segs = [s for s in break_pattern.split(segment) if s.strip()]
    #     final_segments.extend(small_segs)
    #     pass
    
    return final_segments

def html_segment_and_wrap(html_text: str, wrapping_tag: str = "span") -> str:
    """
    Segments the text content of the given HTML string into readable fragments,
    wrapping each fragment in a specified tag (default: <span>).
    Returns the processed HTML as a string.
    """
    soup = BeautifulSoup(html_text, BEAUTIFULSOUP_PARSER)
    root = soup.body or soup
    
    if not root.contents:
        logger.warning(f"No content found in html text【{html_text[:10]}{' ...' if len(html_text) > 10 else ''}】")        
    
    _segment_node(soup, root, wrapping_tag, {f"{NEW_TAG_ATTR_MARK}":"1"})

    counter = 1
    new_elems = soup.select(f"{wrapping_tag}[{NEW_TAG_ATTR_MARK}]")
    for new_elem in new_elems:
        if not new_elem.has_attr("id"):
            id_value = f"{NEW_TAG_ATTR_ID_PREFIX}{counter:05d}"
            new_elem["id"] = id_value
            counter += 1
        else:
            logger.warning(f"One <{wrapping_tag}> tag already has an id: {new_elem["id"]}")

    return str(soup)


def main():
    test_htmls = [
        '''<p id="p1">
            <span class="strong">The sky is <strong>blue</strong>. The grass</span> is green.
        </p>
        ''',
        
        '''<html><head><title>The Old Man and the Sea</title><style type="text/css"> img { max-width: 100%; }</style>
        <body><header/><section class="chapter" title="The Old Man and the Sea" epub:type="chapter" id="id70295538646860"><div class="titlepage"><div><div><h1 class="title">The Old Man and the Sea</h1></div></div></div><p>He was an old man who fished alone in a skiff in the Gulf Stream and he had gone <strong>eighty–four</strong> days now without taking a fish. "<i>he</i>'s so good." said Mrs Wei.</p>
        <!-- 注释 -->
        <span class="strong">The sky is <strong>blue</strong>. The grass</span> is green.</section></body></html>
        ''',

#         '''<?xml version="1.0" encoding="UTF-8" standalone="no"?>
#         <!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.01//EN" "http://www.w3.org/TR/html4/strict.dtd">
# <html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" xmlns:m="http://www.w3.org/1998/Math/MathML" xmlns:pls="http://www.w3.org/2005/01/pronunciation-lexicon" xmlns:ssml="http://www.w3.org/2001/10/synthesis" xmlns:svg="http://www.w3.org/2000/svg">
# <head><title>The Old Man and the Sea</title>
# <link rel="stylesheet" type="text/css" href="docbook-epub.css"/><meta name="generator" content="DocBook XSL Stylesheets Vsnapshot_9885"/>
# <style type="text/css"> img { max-width: 100%; }</style>
# </head>
# <body><div id="cover-image"><img src="bookcover-generated.jpg"/><h1>Cover Page</h1></div><p>Hello <b>World</b></p> <br/><br> <img src="cover.jpg"></body>
# </html>
#         ''',
    ]
    
    for i, html in enumerate(test_htmls, start=1):
        logger.debug(f"--- HTML {i} ---\n{html}")
        processed_html = html_segment_and_wrap2(html)
        logger.debug(f"--- 处理后 HTML {i} ---\n{processed_html}")
        logger.debug("\n" + "-" * 30 + "\n")

    pass



if __name__ == "__main__":
    main()
    # from audible_epub3_gen.tts.azure_tts import AzureTTS
    # text_segments_with_break = [
    #     "Harry Potter and the Philosopher's Stone_#BRK#",
    #     "Hello World_#BRK# _#BRK# It's 2025!",
    #     "Let's_#BRK# see what_#BRK# happens._#BRK#",
    # ]
    # text_segments = []
    # break_pattern = re.compile(r"(_#BRK#)")
    # for segment_with_break in text_segments_with_break:
    #     segs = break_pattern.split(segment_with_break)
    #     for idx, seg in enumerate(segs):
    #         if idx % 2 == 0 and seg.strip():
    #             text_segments.append(seg)
    #         else:  # even index is text, odd index is break
    #             text_segments.append(AzureTTS.get_break_ssml())
    # logger.debug(f"Text segments: {text_segments}")
