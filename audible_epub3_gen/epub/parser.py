from ebooklib import epub
from bs4 import BeautifulSoup

def extract_text_from_epub(epub_path):
    book = epub.read_epub(epub_path)
    items = []
    for item in book.get_items_of_type(ebooklib.ITEM_DOCUMENT):
        soup = BeautifulSoup(item.get_content(), 'html.parser')
        paragraphs = []
        for p in soup.find_all('p'):
            text = p.get_text().strip()
            pid = p.get('id')
            if text and pid:
                paragraphs.append({'id': pid, 'text': text})
        if paragraphs:
            items.append({'file_name': item.file_name, 'paragraphs': paragraphs})
    return items
