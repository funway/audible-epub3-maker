import mimetypes
import zipfile
from urllib.parse import quote, unquote
from lxml import etree as ET
from lxml import html as HTML


_EPUB_MIMETYPES_INITIALIZED = False

def init_epub_mimetypes():
    global _EPUB_MIMETYPES_INITIALIZED
    if _EPUB_MIMETYPES_INITIALIZED:
        return

    mimetypes.init()
    mimetypes.add_type("application/xhtml+xml", ".htm")   # modify .htm default to text/html
    mimetypes.add_type("application/xhtml+xml", ".html")  # modify .html default to text/html
    mimetypes.add_type("application/xhtml+xml", ".xhtml")
    mimetypes.add_type("application/x-dtbncx+xml", ".ncx")
    mimetypes.add_type("application/smil+xml", ".smil")
    mimetypes.add_type("application/oebps-package+xml", ".opf")
    mimetypes.add_type("application/font-sfnt", ".ttf")
    mimetypes.add_type("application/vnd.ms-opentype", ".otf")
    mimetypes.add_type("audio/mp4", ".m4a")

    _EPUB_MIMETYPES_INITIALIZED = True
    return


def guess_media_type(file_path: str) -> str:
    init_epub_mimetypes()

    media_type, _ = mimetypes.guess_type(file_path)
    if media_type is None:
        media_type = "application/octet-stream"
        
    return media_type


def parse_xml(data: bytes | str, recover: bool = True, resolve_entities: bool = False) -> ET._Element:
    """
    Parse XML or HTML content into an lxml Element.

    Args:
        data (bytes | str): XML or HTML content as bytes or UTF-8 string.
        recover (bool): Enable recovery mode for malformed markup. Defaults to True.
        resolve_entities (bool): Whether to resolve external entities. Defaults to False.

    Returns:
        ET._Element: Parsed root element.
    """
    if isinstance(data, str):
        data = data.encode("utf-8")

    parser = ET.XMLParser(recover=recover, resolve_entities=resolve_entities)
    return ET.fromstring(data, parser=parser)

def parse_html(data: bytes | str) -> HTML.HtmlElement:
    """
    Parse HTML content into a lxml HTMLElement
    """
    if isinstance(data, str):
        data = data.encode("utf-8")

    html_tree = HTML.document_fromstring(data)
    return html_tree


def list_files_in_zip(zf: zipfile.ZipFile, prefix: str = "") -> set[str]:
    return {
        zi.filename for zi in zf.infolist()
        if not zi.is_dir() and zi.filename.startswith(prefix)
    }


def safe_requote_uri(uri: str) -> str:
    """Re-quote the given URI.

    This function passes the given URI through an `unquote`/`quote` cycle to
    ensure that it is fully and consistently quoted.

    Args:
        uri (str): _description_

    Returns:
        str: _description_
    """
    unquoted_uri = unquote(uri)
    return quote(unquoted_uri)