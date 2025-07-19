import re
import logging
from bs4 import BeautifulSoup, Tag, NavigableString

from audible_epub3_gen.utils import logging_setup
from audible_epub3_gen.config import BEAUTIFULSOUP_PARSER
from audible_epub3_gen.utils.text_parser import segment_text_by_re, is_readable


logger = logging.getLogger(__name__)

def get_hierarchy_name(tag: Tag) -> str:
    """Returns a string representation of the tag's hierarchy."""
    hierarchy = []
    while tag:
        hierarchy.append(tag.name)
        tag = tag.parent
    return " > ".join(reversed(hierarchy))


def wrap_text_in_tag(soup: BeautifulSoup, text: str, wrapping_tag: str = "span", attrs: dict = {"data-aeg-x":"1"}) -> Tag:
    """Wraps the given text in a new tag with specified attributes.

    Args:
        soup (BeautifulSoup): The BeautifulSoup object used to create new tags.
        text (str): The text to wrap.
        wrapping_tag (str): The name of the tag to wrap the text in.
        attrs (dict, optional): Attributes to set on the new tag. Defaults to {"data-aeg-x":"1"}.

    Returns:
        Tag: The newly created tag containing the text.
    """
    assert isinstance(soup, BeautifulSoup), "soup must be a BeautifulSoup instance"
    tag = soup.new_tag(name=wrapping_tag, attrs=attrs, string=text)
    return tag


def _segment_node(soup: BeautifulSoup, node: Tag, wrapping_tag: str = "span") -> None:
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
    logger.debug(f"{get_hierarchy_name(node)}'s original contents [{len(node.contents)}]: {node.contents}")
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
                        new_tag = wrap_text_in_tag(soup, fragment)
                        new_contents.append(new_tag)
                    else:
                        # append as NavigableString
                        new_contents.append(fragment)
            else:
                logger.debug("  Keep empty NavigableString child")
                new_contents.append(child)  # 保留空白的 NavigableString
        elif isinstance(child, Tag):
            logger.debug(f"  Handle Tag: {get_hierarchy_name(child)}")
            _segment_node(soup, child, wrapping_tag)
            new_contents.append(child)  # don't forget processed child
        else:
            logger.debug(f"  Keep unknown type child: {type(child)}")
            new_contents.append(child)
    
    logger.debug(f"{get_hierarchy_name(node)}'s new contents [{len(new_contents)}]: {new_contents}")
    
    # TODO: 定义一个 contents_smooth 函数，将新 contents 中超短的 <span> 或者 NavigableString 并入前后 span

    node.clear()
    for child in new_contents:
        node.append(child)
    
    return


def html_text_segment(html_str: str, wrapping_tag: str = "span") -> str:
    """
    Segments the text content of the given HTML string into readable fragments,
    wrapping each fragment in a specified tag (default: <span>).
    Returns the processed HTML as a string.
    """
    soup = BeautifulSoup(html_str, BEAUTIFULSOUP_PARSER)
    root = soup.body or soup
    
    if not root.contents:
        logger.warning(f"No content found in html_str【{html_str[:10]}{' ...' if len(html_str) > 10 else ''}】")        

    
    _segment_node(soup, root, wrapping_tag)
    return str(soup)


def main():
    test_htmls = [
        '''<p id="p1">
            <span class="strong">The sky is <strong>blue</strong>. The grass</span> is green.
        </p>
        ''',
        
        '''<div>
            <!-- This is a comment -->
            <span>First sentence.</span> Second sentence.<br/> Hi there!
        </div>
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