import os
import pytest

from audible_epub3_maker.config import INPUT_DIR
from audible_epub3_maker.epub.epub_parser import EpubParser


epub_files = list(INPUT_DIR.glob('*.epub'))

@pytest.mark.parametrize("epubfile", epub_files)
def test_extract_text_from_epub(epubfile):
    print(f"Testing with EPUB file: {epubfile}")
    # result = parser.extract_text_from_epub(epubfile)
    # assert isinstance(result, list)

@pytest.mark.parametrize("epubfile", epub_files)
def test_chapters_match_spin(epubfile):
    print(f"Testing chapters match spine for EPUB file: {epubfile}")
    epub = EpubParser(epubfile)
    chapters = epub.get_chapters()

    spine_ids = [item[0] for item in epub.book.spine]
    chapter_ids = [chapter.get_id() for chapter in chapters]

    assert all(chapter_id in spine_ids for chapter_id in chapter_ids), "All chapter IDs should be in spine IDs"
    spine_filtered = [spine_id for spine_id in spine_ids if spine_id in chapter_ids]
    assert spine_filtered == chapter_ids, "Chapter IDs should match spine IDs in order"
    pass