import os
import pytest
import lxml
from lxml import etree as ET

from audible_epub3_maker.utils.constants import INPUT_DIR
from audible_epub3_maker.epub.epub_book import EpubBook, EpubContentError, NAMESPACES
from audible_epub3_maker.config import UserSettings


epub_files = list(INPUT_DIR.glob('*.epub'))


@pytest.mark.parametrize(
    ("title", "suffix", "expected"),
    [
        ("Book Title", "", "Book Title"),
        ("Book Title", "   ", "Book Title"),
        ("Book Title", "by AEM", "Book Title by AEM"),
        ("Book Title by AEM", "by AEM", "Book Title by AEM"),
        ("Book Title   ", "by AEM", "Book Title by AEM"),
    ],
)
def test_append_title_suffix_updates_opf_title(title, suffix, expected):
    book = EpubBook.__new__(EpubBook)
    book.title = title
    book.opf_root = ET.fromstring(
        f"""
        <package xmlns="http://www.idpf.org/2007/opf">
            <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
                <dc:title>{title}</dc:title>
            </metadata>
        </package>
        """.encode()
    )

    book.append_title_suffix(suffix)

    title_elem = book.metadata.find("dc:title", namespaces=NAMESPACES)
    assert book.title == expected
    assert title_elem.text == expected


def test_append_title_suffix_rejects_missing_title():
    book = EpubBook.__new__(EpubBook)
    book.title = ""

    with pytest.raises(EpubContentError):
        book.append_title_suffix("by AEM")


def test_get_output_filename():
    settings = UserSettings()
    settings.input_file = INPUT_DIR / "Book Title.epub"
    settings.output_dir = INPUT_DIR / "Book Title_audible"

    assert settings.get_output_filename() == "Book Title.epub"
    assert settings.output_path == INPUT_DIR / "Book Title_audible" / "Book Title.epub"

    settings.output_filename = "New Book.epub"
    assert settings.get_output_filename() == "New Book.epub"

    settings.output_filename = "New Book"
    assert settings.get_output_filename() == "New Book.epub"

    with pytest.raises(ValueError):
        settings.output_filename = "nested/New Book.epub"
        settings.get_output_filename()

    with pytest.raises(ValueError):
        settings.output_filename = "New Book.txt"
        settings.get_output_filename()


@pytest.mark.parametrize("epubfile", epub_files)
def test_extract_text_from_epub(epubfile):
    print(f"Testing with EPUB file: {epubfile}")
    book = EpubBook(epubfile)
    assert isinstance(book.spine, lxml.etree._Element)

# @pytest.mark.parametrize("epubfile", epub_files)
# def test_chapters_match_spin(epubfile):
#     print(f"Testing chapters match spine for EPUB file: {epubfile}")
#     book = EpubBook(epubfile)
#     chapters = book.get_chapters()

#     spine_ids = [item[0] for item in book.book.spine]
#     chapter_ids = [chapter.get_id() for chapter in chapters]

#     assert all(chapter_id in spine_ids for chapter_id in chapter_ids), "All chapter IDs should be in spine IDs"
#     spine_filtered = [spine_id for spine_id in spine_ids if spine_id in chapter_ids]
#     assert spine_filtered == chapter_ids, "Chapter IDs should match spine IDs in order"
#     pass
