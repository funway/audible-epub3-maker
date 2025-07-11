import pytest
from audible_epub3_gen.epub import parser

def test_extract_text_from_epub():
    result = parser.extract_text_from_epub("tests/sample.epub")
    assert isinstance(result, list)
