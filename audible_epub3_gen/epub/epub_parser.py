import logging
import ebooklib
from ebooklib import epub
from bs4 import BeautifulSoup

from audible_epub3_gen.config import INPUT_DIR
from audible_epub3_gen.utils import logging_setup


logger = logging.getLogger(__name__)

class EpubParser(object):
    def __init__(self, epub_path, ignore_ncx=True):
        self.epub_path = epub_path
        self.book = epub.read_epub(epub_path, {"ignore_ncx": ignore_ncx})
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")

    def get_chapters(self):
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
    


def main():
    epub_files = INPUT_DIR.glob('*old*.epub')
    for epub_file in epub_files:
        print(f"Processing {epub_file}...")
        
        bookparser = EpubParser(epub_file)        
        
        for chapter in bookparser.get_chapters():
            soup = BeautifulSoup(chapter.content, "lxml-xml")
            for s in soup.body.contents:
                logger.debug(f"Chapter [{chapter.file_name}], content: {s}")
            logger.debug(f"Chapter [{chapter.file_name}] has {len(soup.body.contents)} elements.")

        
        print("Done processing.\n")
    pass

if __name__ == "__main__":
    main()