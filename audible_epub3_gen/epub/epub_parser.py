import logging
from ebooklib import epub
from bs4 import BeautifulSoup

from audible_epub3_gen.config import INPUT_DIR, OUTPUT_DIR
from audible_epub3_gen.utils import logging_setup
from audible_epub3_gen.epub.html_parser import html_text_segment


logger = logging.getLogger(__name__)

class EpubWrite(epub.EpubWriter):
    def _write(self, arg):
        pass

class EpubParser(object):
    def __init__(self, epub_path, ignore_ncx=True):
        self.epub_path = epub_path
        self.book = epub.read_epub(epub_path)
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")

    def get_chapters(self):
        """
        Extracts and returns all chapter items from the EPUB file.

        Returns:
            list: A list of EpubHtml chapter objects found in the EPUB spine.
        """
        self.logger.debug(f"Getting chapters from {self.epub_path.name}")
        chapters = []
        
        # Ignore no-linear items in spine
        spine_item_ids = [item[0] for item in self.book.spine if item[1] == "yes"]
        
        for item_id in spine_item_ids:
            item = self.book.get_item_with_id(item_id)
            
            # Ignore nav item
            if isinstance(item, epub.EpubHtml) and item.is_chapter():
                chapters.append(item)
        
        self.logger.debug(f"Found {len(chapters)} chapters in {self.epub_path.name}")
        return chapters


    def save_epub(self, file_path):
        # Don't use ebooklib's write_epub function cause it modifies the <head> section of the HTML.
        # ebooklib.epub.write_epub(file_path, self.book)

        pass


def main():
    epub_files = INPUT_DIR.glob('*old*.epub')
    for epub_file in epub_files:
        logger.debug(f"Load Book: {epub_file}")
        
        bookparser = EpubParser(epub_file) 

        chapters = bookparser.get_chapters()
        for i, chapter in enumerate(chapters, start=1):  
            logger.debug(f"Processing Chapter [{i}/{len(chapters)}]: {chapter.file_name}")
            # logger.debug(chapter.content)
            
            # 保存 content 到 OUTPUT_DIR
            # output_path = OUTPUT_DIR / f"{epub_file.stem}_chapter_{i}.xhtml"
            # print(type(chapter.content))
            # with open(output_path, "wb") as f:
            #     f.write(chapter.content)
            
        #     modified_content = html_text_segment(chapter.content)
        #     output_path = output_path.with_name(output_path.stem + "_mod" + ".xhtml")
        #     print(type(modified_content))
        #     with open(output_path, "wb") as f:
        #         f.write(modified_content.encode("utf-8"))
            
        #     chapter.set_content(modified_content.encode("utf-8"))
        
        output_path = OUTPUT_DIR / f"{epub_file.stem}_new.epub"
        bookparser.save_epub(output_path)

        
        logger.debug("Done processing.\n")
    pass

if __name__ == "__main__":
    main()