import shutil
import zipfile
import logging
import uuid
import re
import codecs
from pathlib import Path, PurePosixPath
from dataclasses import dataclass
from lxml import etree as ET

from audible_epub3_gen.utils import logging_setup
from audible_epub3_gen.epub.utils import guess_media_type, parse_xml, list_files_in_zip

logger = logging.getLogger(__name__)

MIMETYPE = "application/epub+zip"

CONTAINER_PATH = "META-INF/container.xml"

NAMESPACES = {
    'opf': 'http://www.idpf.org/2007/opf',
    'dc': 'http://purl.org/dc/elements/1.1/',
}


class EpubError(Exception): pass
class EpubStructureError(EpubError): pass
class EpubContentError(EpubError): pass
class EpubIOError(EpubError): pass

@dataclass
class LazyLoad:
    def load(self) -> bytes:
        raise NotImplementedError

@dataclass
class LazyLoadFromZip(LazyLoad):
    zip_file_path: Path
    zip_href: str

    def load(self) -> bytes:
        with zipfile.ZipFile(self.zip_file_path, 'r') as zf:
            return zf.read(self.zip_href)

@dataclass
class LazyLoadFromFile(LazyLoad):
    file_path: Path

    def load(self) -> bytes:
        return self.file_path.read_bytes()

class EpubItem(object):
    # https://www.w3.org/TR/epub-33/#sec-item-elem

    def __init__(self, raw_content: bytes | LazyLoad, 
                 id: str, href: str, media_type: str, attrs: dict[str: str] | None = None):
        
        # required attrs for EPUB opf.manifest.item: [id, href, media_type]
        self.id = id
        self.href = href
        self.media_type = media_type
        # optional attrs for EPUB opf.manifest.item: [fallback, media-overlay, properties] or customized
        self.attrs = attrs or {}

        self.in_manifest = False
        
        if not isinstance(raw_content, (bytes, LazyLoad)):
            raise TypeError(f"Unsupported content type: {type(raw_content)}")
        self._raw_content = raw_content
        pass
        
    @property
    def is_loaded(self) -> bool:
        return isinstance(self._raw_content, bytes)

    def get_raw(self) -> bytes:
        # lazy load
        lazy_load = self._raw_content
        if isinstance(lazy_load, LazyLoad):
            self._raw_content = lazy_load.load()

        if not isinstance(self._raw_content, (bytes, LazyLoad)):
            raise TypeError(f"Unsupported content type: {type(self._raw_content)}")

        return self._raw_content

    def set_raw(self, raw_content: bytes):
        if not isinstance(raw_content, bytes):
            raise TypeError(f"Unsupported content type: {type(raw_content)}")
        
        self._raw_content = raw_content
        pass

    def set_lazy_load(self, lazy_load: LazyLoad):
        if not isinstance(lazy_load, LazyLoad):
            raise TypeError(f"Unsupported lazy load type: {type(lazy_load)}")
        
        self._raw_content = lazy_load
        pass

    def get_lazy_load(self) -> LazyLoad:
        if isinstance(self._raw_content, LazyLoad):
            return self._raw_content
        else:
            return None

    def __repr__(self):
        return f"<EpubItem id={self.id} href={self.href} media_type={self.media_type}>"

class EpubTextItem(EpubItem): 
    def get_text(self, encoding: str | None = None) -> str:
        """
        Decodes the raw byte content of the item into a Unicode string.

        Decoding priority:
            1. Use the explicitly provided `encoding` if given.
            2. Otherwise, try to extract the encoding from the XML declaration in the first 128 bytes.
            3. If no encoding is found, fall back to UTF-8.

        Args:
            encoding (str, optional): Character encoding to use for decoding. If None, attempt auto-detection.

        Returns:
            str: Decoded text content.
        """
        raw_bytes = self.get_raw()
        fallback_enc = "utf-8"
        if encoding is None:
            head = raw_bytes[:128]
            try:
                head_str = head.decode("ascii", errors="ignore").lower()
                xml_encoding_match = re.search(r'encoding\s*=\s*["\']([\w\-]+)["\']', head_str)
                if xml_encoding_match:
                    declared_encoding = xml_encoding_match.group(1)
                    codecs.lookup(declared_encoding)
                    encoding = declared_encoding
                else:
                    encoding = fallback_enc
            except Exception:
                logger.exception("Failed to extract or validate declared encoding, fallback to utf-8.")
                encoding = fallback_enc
        
        return raw_bytes.decode(encoding if encoding else "utf-8")

    def set_text(self, text: str):
        self.set_raw(text.encode())

    def count_chars(self, with_whitespace: bool = True) -> int:
        if with_whitespace:
            return len(self.get_text())
        else:
            return len(re.sub(r"\s+", "", self.get_text()))

class EpubNcx(EpubTextItem): pass

class EpubHTML(EpubTextItem):

    def get_title(self) -> str:
        """
        [Uncompleted] Extracts a title from the XHTML content, prioritizing in order: <title>, <h1>, <h2>, <h3>.

        Returns:
            str: The first non-empty text found in those tags, or empty string if none found.
        """
        # TODO: 从 html 中找章节标题其实不是一个好办法，好办法是从 toc.ncx 或者 nav 中找，然后 set title 给他
        raise NotImplementedError
    
        title_levels = ['h1', 'h2', 'h3']

        try:
            tree = parse_xml(self.get_text())
        except Exception as e:
            logger.warning(f"Failed to parse XHTML for {self.href}: {e}")
            return ""
        
        for level in title_levels:
            elems = tree.xpath(f"//*[local-name()='{level}']")
            for elem in elems:
                text = (elem.text or "").strip()
                if text:
                    return text
        return ""

class EpubNavHTML(EpubHTML): pass

class EpubSMIL(EpubTextItem): pass
class EpubAudio(EpubItem): pass
class EpubImage(EpubItem): pass

class EpubBook:
    """
    EPUB book structure. Refers to: https://www.w3.org/TR/epub-33/
    """
    '''
    EPUB (.epub ZIP)
        ├─ mimetype                 # required file (fixed name), must be the first file in ZIP container
        ├─ META-INF/container.xml   # required file (fixed path and name), points to .opf file
        ├─ OEBPS/package.opf        # required file (no-fixed path and name), 
            ├─ <metadata>           # required first elem under opf <package>
                ├─ <dc:identifier>      # required elem
                ├─ <dc:title>           # required elem
                ├─ <dc:language>        # required elem
            ├─ <manifest>           # required second elem under opf <package>, list of all resource files (should but not forced)
            ├─ <spine>              # reuqired third elem under opf <package>, define reading order for EPUB reader.
        ├─ [nav].xhtml / toc.ncx    # table of content (toc.ncx is kept for old version)
        ├─ [chapter1].xhtml         # actual content files
        ├─ images/, fonts/          # optional and no-fixed path name, supporting assets
    '''

    DEFAULT_OPTIONS = {
        # 'item_lazy_load_threshold': 16*1024*1024,
        'item_lazy_load_threshold': 50*1024,
    }

    def __init__(self, epub_path: Path, options: dict = {}):
        self.epub_path = epub_path

        self.options = dict(__class__.DEFAULT_OPTIONS)
        self.options.update(options)

        self.container_root: ET._Element = None # container.xml 解析后的 ElementTree 根节点
        self.opf_path: str = None               # .opf 文件路径 (container.xml 中定义的字符串)
        self.opf_root: ET._Element = None       # .opf 文件解析后的 ElementTree 根节点

        self.identifier = None
        self.title = None
        self.language = None

        self.items: list[EpubItem] = []  # EpubItem 对象

        self._read_epub(epub_path)
        pass
    
    @property
    def metadata(self) -> ET._Element:
        """
        Returns the metadata element from the OPF XML root of the EPUB book.

        https://www.w3.org/TR/epub-33/#sec-pkg-metadata
        """
        if self.opf_root is None:
            raise EpubStructureError("OPF root is not loaded. Cannot access metadata.")
        
        return self.opf_root.find(".//opf:metadata", namespaces=NAMESPACES)

    @property
    def manifest(self) -> list[EpubItem]:
        """
        Retrieves all items that are included in the EPUB manifest.

        https://www.w3.org/TR/epub-33/#sec-pkg-manifest
        """
        return [item for item in self.items if item.in_manifest]

    @property
    def spine(self) -> ET._Element:
        """
        Returns the spine element from the OPF XML root of the EPUB book.

        https://www.w3.org/TR/epub-33/#sec-pkg-spine
        """
        if self.opf_root is None:
            raise EpubStructureError("OPF root is not loaded. Cannot access spine.")
        
        return self.opf_root.find(".//opf:spine", namespaces=NAMESPACES)
    
    def add_item(self, item: EpubItem, in_manifest: bool = True):
        item.in_manifest = in_manifest
        self.items.append(item)
        pass

    def add_smil_item(self, item: EpubSMIL, target_id: str):
        self.add_item(item)
        target_item = self.get_item_by_id(target_id)
        target_item.attrs["media-overlay"] = item.id
        pass

    def _read_required_metadata(self):
        metadata = self.metadata
        if metadata is None:
            raise EpubStructureError("No <metadata> found in opf")
        
        try:
            self.identifier = metadata.find("dc:identifier", namespaces=NAMESPACES).text.strip()
            self.title = metadata.find("dc:title", namespaces=NAMESPACES).text.strip()
            self.language = metadata.find("dc:language", namespaces=NAMESPACES).text.strip()
        except Exception as e:
            raise EpubContentError("Missing required metadata: dc:identifier, dc:title, or dc:language") from e
        pass

    def _read_epub(self, epub_path):
        logger.debug(f"Loading epub: {epub_path}")
        with zipfile.ZipFile(epub_path, "r") as zf:
            
            # 1. read mimetype file
            mimetype = zf.read("mimetype").decode("ascii").strip()
            if mimetype != MIMETYPE:
                raise EpubContentError(f"Invalid mimetype: {mimetype}")

            # 2. read container.xml
            self.container_root = parse_xml(zf.read(CONTAINER_PATH))
            rootfile = self.container_root.find(".//{*}rootfile")
            if rootfile is None:
                raise EpubStructureError("No <rootfile> found in container.xml")
            
            self.opf_path = rootfile.attrib["full-path"]
            logger.debug(f"Found .opf file: {self.opf_path}")

            # 3. read .opf file
            opf_dir = PurePosixPath(self.opf_path).parent
            opf_data = zf.read(self.opf_path)
            self.opf_root = parse_xml(opf_data)
            
            # 3.1 metadata
            # use self.metadata property
            self._read_required_metadata()

            # 3.2 manifest
            manifest_elem = self.opf_root.find(".//opf:manifest", namespaces=NAMESPACES)
            if manifest_elem is None:
                raise EpubStructureError("No <manifest> found in opf")
            manifest_items = {}
            for item_elem in manifest_elem:
                href = item_elem.attrib["href"]
                zip_href = self.to_zip_href(href)
                manifest_items[zip_href] = item_elem
            # logger.debug(f"All manifest files: {sorted(manifest_items.keys())}")
            
            all_files = list_files_in_zip(zf)
            ignored_files = {
                "mimetype",
                CONTAINER_PATH,
                self.opf_path,
            }
            all_files = sorted(all_files - ignored_files)
            # logger.debug(f"All zip files: {all_files}")
            for zip_href in all_files:
                lazy_load = LazyLoadFromZip(self.epub_path, zip_href)
                
                item_elem = manifest_items.pop(zip_href, None)
                if item_elem is not None:
                    # declared item
                    attrs = dict(item_elem.attrib)
                    id = attrs.pop("id")                   
                    href = attrs.pop("href")   
                    media_type = attrs.pop("media-type") 
                    
                    guessed_type = guess_media_type(zip_href)
                    if media_type != guessed_type:
                        logger.warning(f"Media type mismatch for {zip_href}: declared={media_type}, guessed={guessed_type}")
                    
                    in_manifest = True
                else:
                    # undeclared item
                    logger.warning(f"File in zip not declared in manifest: {zip_href}")
                    id = f"auto_{uuid.uuid4().hex[:8]}"
                    href = str(PurePosixPath(zip_href).relative_to(opf_dir))
                    media_type = guess_media_type(zip_href)
                    attrs = {}
                    in_manifest = False
                item = create_epub_item(lazy_load, id, href, media_type, attrs)
                self.add_item(item, in_manifest)
                
                # load item content
                try:
                    zip_info = zf.getinfo(zip_href)
                    if zip_info.file_size <= int(self.options["item_lazy_load_threshold"]):
                        item.set_raw(zf.read(zip_href))
                except Exception:
                    logger.exception(f"Item not found in zip: {zip_href}")
            
            # 检查 manifest 声明的文件是否全部加载
            for missing_file, _ in manifest_items.items():
                logger.warning(f"Manifest declared but missing file: {zip_href}")

            # 3.3 spine
            # use self.spine property
            if self.spine is None:
                raise EpubStructureError("No <spine> found in opf")
            
            pass
        pass
    
    def to_zip_href(self, opf_href: str) -> str:
        """
        将相对于 opf 的路径转换成相对于 zip 根目录的路径
        """
        zip_href = str(PurePosixPath(self.opf_path).parent / opf_href)
        return zip_href

    def get_chapters(self) -> list[EpubHTML]:
        """Returns the linear reading items in the EPUB spine, excluding navigation pages.

        This method returns a list of EpubHTML items that:
            - Appear in the spine with linear="yes" (i.e., meant to be read in order)
            - Are not navigation documents (e.g., EPUB TOC)

        Note:
            The returned list may include non-chapter items such as forewords, appendices, 
            or image pages, depending on how the EPUB is structured.

        Returns:
            list[EpubHTML]: Ordered list of main content items in reading sequence
        """
        spine_elem = self.spine
        itemrefs = spine_elem.findall("opf:itemref", namespaces=NAMESPACES)
        
        # skip no linear items
        idrefs = [r.attrib["idref"] for r in itemrefs if r.attrib.get("linear", "yes") != "no"]

        chapters = []
        for idref in idrefs:
            item = self.get_item_by_id(idref)
            if not item:
                logger.warning(f"Spine itemref {idref} not found in EPUB's items.")
            
            # ignore TOC page
            if not isinstance(item, EpubNavHTML):
                chapters.append(item)

        logger.debug(f"Found {len(chapters)} linear reading items from {self.epub_path.name}")
        return chapters
    
    def save_epub(self, output_path: Path, extra_meta: dict | None = None):
        # TODO: 
        # 1. 如果 output_path 与原文件 self.epub_path 冲突了，在移动临时文件之前，将原文件 mv 成 .epub.bak 的形式
        # 2. 添加 extra_meta 给 epub。我想增加一个元数据表示 generated by APP_FULL_NAME

        tmp_path = output_path.with_suffix(".tmp.epub")
        try:
            with zipfile.ZipFile(tmp_path, "w", compression=zipfile.ZIP_DEFLATED) as zf_output:
                # 1. mimetype 必须 uncompressed 且排在第一位
                zf_output.writestr("mimetype", MIMETYPE, compress_type=zipfile.ZIP_STORED)
                
                # 2. container
                self._write_container(zf_output)
                
                # 3. opf
                self._write_opf(zf_output)

                # 4. all items
                self._write_items(zf_output)
            
            if output_path.resolve() == self.epub_path.resolve():
                backup_path = self.epub_path.with_suffix(".epub.bak")
                logger.warning(f"Output path conflicts with original file. Backing up to {backup_path}")
                shutil.move(self.epub_path, backup_path)
            
            shutil.move(tmp_path, output_path)
            logger.debug(f"EPUB saved to {output_path}")
        except Exception as e:
            raise e
        finally:
            if tmp_path.exists():
                tmp_path.unlink(missing_ok=True)
        pass
        

    def _write_container(self, zp: zipfile.ZipFile):
        tree = self.container_root.getroottree()
        container_bytes = ET.tostring(tree, 
                                      encoding=tree.docinfo.encoding,
                                      xml_declaration=None,
                                      standalone=tree.docinfo.standalone,
                                      )
        zp.writestr(CONTAINER_PATH, container_bytes)
        pass

    def _update_opf_metadata(self, extra_meta: dict | None = None, overwrite: bool = True):
        """
        Updates the <metadata> element of the OPF with additional `<meta property="key">value</meta>` tags.

        Args:
            extra_meta (dict | None): Dictionary of additional metadata entries (key=property, value=text).
            overwrite (bool): Whether to overwrite existing properties. Default: True.

        需要修改：
        1. 先更新 extra_meta， 增加三个属性
        官方的 modified 时间
        aeg:generator = APP_NAME
        aeg:version = APP_VERSION
        2. 根据 overwrite 参数判断是否覆盖原有的属性
        3. 使用 epub3 的 property 方式
        """
        extra_meta = extra_meta or {}
        
        # modified_str = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        # defaults = {
        #     "dcterms:modified": modified_str,
        #     "aeg:generator": APP_NAME,
        #     "aeg:version": APP_VERSION,
        # }

        metadata_elem = self.metadata

        for prop, value in extra_meta.items():
            if not prop or not value:
                continue
            existing = metadata_elem.xpath(f'meta[@property="{prop}"]', namespaces=NAMESPACES)
            if existing:
                if overwrite:
                    existing[0].text = value
                else:
                    pass  # skip
            else:
                ET.SubElement(metadata_elem, "meta", {"property": prop}).text = value
        pass

    def _update_opf_manifest(self):
        """
        Rebuilds the <manifest> section of the OPF document based on the current list of manifest items.

        This function clears the existing <item> elements under <manifest> and appends new <item> elements 
        for each `EpubItem` in `self.manifest`.
        """
        # Locate the <manifest> element in the OPF XML
        manifest_elem = self.opf_root.find(".//opf:manifest", namespaces=NAMESPACES)
        if manifest_elem is None:
            raise EpubStructureError("No <manifest> found in opf")
        
        indent = manifest_elem.text if manifest_elem.text and manifest_elem.text.strip() == "" else "\n  "

        # Remove all existing <item> children under <manifest>
        for child in list(manifest_elem):
            manifest_elem.remove(child)

        # Add new <item> elements for each resource from `manifest` var list in current EpubBook instance
        for item in self.manifest:
            item_elem = ET.Element("item", {
                "id": item.id,
                "href": item.href,
                "media-type": item.media_type,
                **item.attrs
            })
            item_elem.tail = indent
            manifest_elem.append(item_elem)
        
        manifest_elem[-1].tail = "\n  "
        pass

    def _write_opf(self, zp: zipfile.ZipFile):
        self._update_opf_manifest()

        tree = self.opf_root.getroottree()
        opf_bytes = ET.tostring(tree, 
                                encoding=tree.docinfo.encoding,
                                xml_declaration=None,
                                standalone=tree.docinfo.standalone,
                                )
        zp.writestr(self.opf_path, opf_bytes)
        pass

    def _write_items(self, zp: zipfile.ZipFile):
        lazyload_from_orig_epub = []
        layzload_from_other_zip = []
        layzload_from_other_file = []
        
        for item in self.items:
            if item.is_loaded:
                content = item.get_raw()
                zp.writestr(self.to_zip_href(item.href), content)
                continue
            
            lazyload = item.get_lazy_load()
            if isinstance(lazyload, LazyLoadFromZip):
                if lazyload.zip_file_path == self.epub_path:
                    lazyload_from_orig_epub.append(item)
                else:
                    layzload_from_other_zip.append(item)
            elif isinstance(lazyload, LazyLoadFromFile):
                layzload_from_other_file.append(item)

        if len(lazyload_from_orig_epub):
            with zipfile.ZipFile(self.epub_path, "r") as zp_original:
                for item in lazyload_from_orig_epub:
                    zip_href = self.to_zip_href(item.href)
                    data = zp_original.read(zip_href)
                    zp.writestr(zip_href, data)
                    logger.debug(f"save lazyload content from EPUB: {len(data)/1024:.2f} KB, {zip_href}")
        
        for item in layzload_from_other_zip:
            other_zip_file = item.get_lazy_load().zip_file_path
            content = item.get_raw()
            zp.writestr(self.to_zip_href(item.href), content)
            logger.warning(f"save lazyload content from other zip: {len(content)/1024:.2f} KB, {other_zip_file}")
        
        for item in layzload_from_other_file:
            file_path = item.get_lazy_load().file_path
            zp.write(file_path, arcname=self.to_zip_href(item.href))
            logger.debug(f"save lazyload content from new file: {file_path} -> {self.to_zip_href(item.href)}")
        pass

    def get_item_by_id(self, id: str) -> EpubItem | None:
        return next((item for item in self.items if item.id == id), None)

def create_epub_item(raw_content: bytes | LazyLoad, id: str, href: str, media_type: str, attrs: dict[str, str] | None = None) -> EpubItem:
    if media_type == "application/xhtml+xml":
        if "nav" in attrs.get("properties", "").split():
            return EpubNavHTML(raw_content, id, href, media_type, attrs)
        
        return EpubHTML(raw_content, id, href, media_type, attrs)
    
    elif media_type == "application/x-dtbncx+xml":
        return EpubNcx(raw_content, id, href, media_type, attrs)
    
    elif media_type == "application/smil+xml":
        return EpubSMIL(raw_content, id, href, media_type, attrs)
    
    elif media_type.startswith("audio/"):
        return EpubAudio(raw_content, id, href, media_type, attrs)
    
    elif media_type.startswith("image/"):
        return EpubImage(raw_content, id, href, media_type, attrs)
    
    else:
        return EpubItem(raw_content, id, href, media_type, attrs)

def main():
    from audible_epub3_gen.segmenter.html_segmenter import html_segment_and_wrap

    epub_files = Path('input/').glob('*otter*.epub')
    for epub_file in epub_files:
        logger.debug(f"Start Processing: {epub_file}")
        book = EpubBook(epub_file)

        # items_count = len(book.items)
        # for i, item in enumerate(book.items, start=1):
        #     logger.debug(f"item [{i}/{items_count}], id: {item.id}, file: {book.to_zip_href(item.href)}")

        chapters = book.get_chapters()
        chapters_count = len(chapters)
        for i, chapter in enumerate(chapters, start=1):
            logger.debug(f"chapter [{i}/{chapters_count}], id: {chapter.id}, file: {chapter.href}, title: {chapter.get_title()}")
            # modified_content = html_segment_and_wrap(chapter.get_text())
            # chapter.set_text(modified_content)

        # output_path = Path('output') / f"{epub_file.stem}_new.epub"
        # book.save_epub(output_path)
        logger.debug("Done processing.")
    pass

if __name__ == "__main__":
    main()