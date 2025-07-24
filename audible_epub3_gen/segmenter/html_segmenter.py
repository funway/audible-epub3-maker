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
    assert isinstance(soup, BeautifulSoup), "soup must be a BeautifulSoup instance"
    assert isinstance(node, Tag), "node must be a Tag instance"
    
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


def html_text_segment(html_text: str, wrapping_tag: str = "span") -> str:
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
        
        '''<body><header/><section class="chapter" title="The Old Man and the Sea" epub:type="chapter" id="id70295538646860"><div class="titlepage"><div><div><h1 class="title">The Old Man and the Sea</h1></div></div></div><p>He was an old man who fished alone in a skiff in the Gulf Stream and he
had gone eighty–four days now without taking a fish.  In the first
forty days a boy had been with him.  But after forty days without a
fish the boy's parents had told him that the old man was now definitely
and finally <span class="emphasis"><em>salao</em></span>, which is the worst form of unlucky, and the boy
had gone at their orders in another boat which caught three good fish
the first week.</p></section></body>
        ''',

        '''<?xml version="1.0" encoding="UTF-8" standalone="no"?>
        <!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.01//EN" "http://www.w3.org/TR/html4/strict.dtd">
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" xmlns:m="http://www.w3.org/1998/Math/MathML" xmlns:pls="http://www.w3.org/2005/01/pronunciation-lexicon" xmlns:ssml="http://www.w3.org/2001/10/synthesis" xmlns:svg="http://www.w3.org/2000/svg">
<head><title>The Old Man and the Sea</title>
<link rel="stylesheet" type="text/css" href="docbook-epub.css"/><meta name="generator" content="DocBook XSL Stylesheets Vsnapshot_9885"/>
<style type="text/css"> img { max-width: 100%; }</style>
</head>
<body><div id="cover-image"><img src="bookcover-generated.jpg"/><h1>Cover Page</h1></div><p>Hello <b>World</b></p> <br/><br> <img src="cover.jpg"></body>
</html>
        ''',
    ]
    
    for i, html in enumerate(test_htmls, start=1):
        logger.debug(f"--- HTML {i} ---")
        
        processed_html = html_text_segment(html)
        logger.debug(f"--- 处理后 HTML {i} ---\n{processed_html}")
        
        logger.debug("\n\n" + "-" * 30 + "\n")

    pass

if __name__ == "__main__":
    main()