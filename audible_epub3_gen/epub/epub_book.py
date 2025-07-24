import zipfile
import logging
import uuid
import re
from pathlib import Path, PurePosixPath
from dataclasses import dataclass
from lxml import etree as ET

from audible_epub3_gen.config import INPUT_DIR, OUTPUT_DIR
from audible_epub3_gen.utils import logging_setup
from audible_epub3_gen.epub.utils import guess_media_type, parse_xml, list_zip_files

logger = logging.getLogger(__name__)

MIMETYPE = "application/epub+zip"

CONTAINER_PATH = "META-INF/container.xml"

NAMESPACES = {
    'opf': 'http://www.idpf.org/2007/opf',
    'dc': 'http://purl.org/dc/elements/1.1/',
}

@dataclass
class LazyLoad:
    def load(self) -> bytes:
        raise NotImplementedError

@dataclass
class LazyLoadFromOriginal(LazyLoad):
    zip_file_path: Path
    zip_href: str

    def load(self) -> bytes:
        with zipfile.ZipFile(self.zip_file_path, 'r') as zf:
            return zf.read(self.zip_href)

@dataclass
class LazyLoadFromNewFile(LazyLoad):
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
        """
        raw_bytes = self.get_raw()
        
        if encoding is None:
            fallback_enc = "utf-8"
            head = raw_bytes[:128]
            try:
                head_str = head.decode("ascii", errors="ignore").lower()
                xml_encoding_match = re.search(r'encoding=["\']([\w\-]+)["\']', head_str)
                if xml_encoding_match:
                    encoding = xml_encoding_match.group(1)
            except Exception:
                logger.exception("Unknown exception when searching encoding.")
                encoding = fallback_enc
        
        return raw_bytes.decode(encoding)

    def set_text(self, text: str):
        self.set_raw(text.encode())

class EpubNcx(EpubTextItem): pass
class EpubHTML(EpubTextItem): pass
class EpubNavHTML(EpubHTML): pass

class EpubSMIL(EpubTextItem): pass
class EpubAudio(EpubItem): pass
class EpubImage(EpubItem): pass

class EpubException(Exception): pass

class EpubBook:
    DEFAULT_OPTIONS = {
        # 'item_lazy_load_threshold': 16*1024*1024,
        'item_lazy_load_threshold': 50*1024,
    }

    def __init__(self, epub_path: Path, options: dict = {}):
        self.epub_path = epub_path

        self.options = dict(__class__.DEFAULT_OPTIONS)
        self.options.update(options)

        self.container_root: ET._Element = None  # container.xml 解析后的 ElementTree 根节点
        self.opf_path: str = None  # .opf 文件路径 (container.xml 中定义的字符串)
        self.opf_root: ET._Element = None  # .opf 文件解析后的 ElementTree 根节点

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
            raise EpubException("OPF root is not loaded. Cannot access metadata.")
        
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
            raise EpubException("OPF root is not loaded. Cannot access spine.")
        
        return self.opf_root.find(".//opf:spine", namespaces=NAMESPACES)
    
    def add_item(self, item: EpubItem, in_manifest: bool = True):
        item.in_manifest = in_manifest
        self.items.append(item)
        pass

    def _read_epub(self, epub_path):
        logger.debug(f"Loading epub: {epub_path}")
        with zipfile.ZipFile(epub_path, "r") as zf:
            
            # 1. read mimetype file
            mimetype = zf.read("mimetype").decode("ascii").strip()
            if mimetype != MIMETYPE:
                raise EpubException(f"Invalid mimetype: {mimetype}")

            # 2. read container.xml
            self.container_root = parse_xml(zf.read(CONTAINER_PATH))
            rootfile = self.container_root.find(".//{*}rootfile")
            if rootfile is None:
                raise EpubException("No <rootfile> found in container.xml")
            
            self.opf_path = rootfile.attrib["full-path"]
            logger.debug(f"Found .opf file: {self.opf_path}")

            # 3. read .opf file
            opf_dir = PurePosixPath(self.opf_path).parent
            opf_data = zf.read(self.opf_path)
            self.opf_root = parse_xml(opf_data)
            
            # 3.1 metadata
            # use self.metadata property

            # 3.2 manifest
            manifest_elem = self.opf_root.find(".//opf:manifest", namespaces=NAMESPACES)
            manifest_items = {}
            for item_elem in manifest_elem:
                href = item_elem.attrib["href"]
                zip_href = self.to_zip_href(href)
                manifest_items[zip_href] = item_elem
            logger.debug(f"All manifest files: {sorted(manifest_items.keys())}")
            
            all_files = list_zip_files(zf)
            ignored_files = {
                "mimetype",
                CONTAINER_PATH,
                self.opf_path,
            }
            all_files = sorted(all_files - ignored_files)
            logger.debug(f"All zip files: {all_files}")
            for zip_href in all_files:
                lazy_load = LazyLoadFromOriginal(epub_path, zip_href)
                
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
            
            pass
        pass
    
    def to_zip_href(self, opf_href: str) -> str:
        """
        将相对于 opf 的路径转换成相对于 zip 根目录的路径
        """
        zip_href = str(PurePosixPath(self.opf_path).parent / opf_href)
        return zip_href

    def get_chapters(self) -> EpubHTML:
        logger.debug(f"Getting chapters from {self.epub_path.name}")
        
        spine_elem = self.spine
        itemrefs = spine_elem.findall("opf:itemref", namespaces=NAMESPACES)
        idrefs = [r.attrib["idref"] for r in itemrefs if r.attrib.get("linear", "yes") != "no"]

        chapters = []
        for idref in idrefs:
            item = self.get_item_by_id(idref)
            if not item:
                logger.warning(f"Spine itemref {idref} not found in EPUB's items.")
            
            # ignore TOC page
            if not isinstance(item, EpubNavHTML):
                chapters.append(item)

        return chapters
    
    def save_epub(self, output_path):
        with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_DEFLATED) as zf_output:
            # 1. mimetype 必须 uncompressed 且排在第一位
            zf_output.writestr("mimetype", MIMETYPE, compress_type=zipfile.ZIP_STORED)
            
            # 2. container
            self._write_container(zf_output)
            
            # 3. opf
            self._write_opf(zf_output)

            # 4. all items
            lazyload_from_orig_epub = []
            layzload_from_new_file = []
            for item in self.items:
                if item.is_loaded:
                    content = item.get_raw()
                    zf_output.writestr(self.to_zip_href(item.href), content)
                    continue
                
                if isinstance(item.get_lazy_load(), LazyLoadFromOriginal):
                    lazyload_from_orig_epub.append(item)
                elif isinstance(item.get_lazy_load(), LazyLoadFromNewFile):
                    layzload_from_new_file.append(item)

            if len(lazyload_from_orig_epub):
                with zipfile.ZipFile(self.epub_path, "r") as zf_original:
                    for item in lazyload_from_orig_epub:
                        zip_href = self.to_zip_href(item.href)
                        data = zf_original.read(zip_href)
                        zf_output.writestr(zip_href, data)
                        logger.debug(f"save lazyload content from EPUB: {len(data)/1024:.2f} KB, {zip_href}")
            
            for item in layzload_from_new_file:
                file_path = item.get_lazy_load().file_path
                zf_output.write(file_path, arcname=self.to_zip_href(item.href))
                logger.debug(f"save lazyload content from new file: {file_path} -> {self.to_zip_href(item.href)}")
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

    def _update_opf_manifest(self):
        manifest_elem = self.opf_root.find(".//opf:manifest", namespaces=NAMESPACES)
        if manifest_elem is None:
            raise EpubException("OPF manifest element not found.")
        
        indent = manifest_elem.text if manifest_elem.text and manifest_elem.text.strip() == "" else "\n  "

        for child in list(manifest_elem):
            manifest_elem.remove(child)

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
    from audible_epub3_gen.epub.html_parser import html_text_segment

    epub_files = INPUT_DIR.glob('*old*.epub')
    for epub_file in epub_files:
        logger.debug(f"Start Processing: {epub_file}")
        book = EpubBook(epub_file)

        # items_count = len(book.items)
        # for i, item in enumerate(book.items, start=1):
        #     logger.debug(f"item [{i}/{items_count}], id: {item.id}, file: {book.to_zip_href(item.href)}")

        chapters = book.get_chapters()
        chapters_count = len(chapters)
        for i, chapter in enumerate(chapters, start=1):
            logger.debug(f"chapter [{i}/{chapters_count}], id: {chapter.id}, file: {chapter.href}")
            modified_content = html_text_segment(chapter.get_text())
            chapter.set_text(modified_content)

        output_path = OUTPUT_DIR / f"{epub_file.stem}_new.epub"
        book.save_epub(output_path)
        logger.debug("Done processing.\n")
    pass

if __name__ == "__main__":
    main()