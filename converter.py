"""
File-to-text converter for @HengAudioBKBot.
Supports PDF, EPUB, DOCX, TXT, Images via OCR.
"""
import os, subprocess, tempfile, logging
from pathlib import Path

log = logging.getLogger(__name__)

def file_to_text(file_path: str) -> str:
    ext = os.path.splitext(file_path)[1].lower()
    log.info(f"Converting {file_path} (ext={ext})")
    if ext == '.pdf':
        return _pdf_to_text(file_path)
    elif ext == '.epub':
        return _epub_to_text(file_path)
    elif ext in ('.docx', '.doc'):
        return _docx_to_text(file_path)
    elif ext in ('.txt', '.csv', '.json', '.md'):
        return _read_text(file_path)
    elif ext in ('.html', '.htm'):
        return _html_to_text(file_path)
    elif ext in ('.jpg', '.jpeg', '.png', '.tiff', '.tif', '.bmp', '.gif'):
        return _image_to_text(file_path)
    else:
        raise ValueError(f"Unsupported format: {ext}")

def _read_text(path):
    with open(path, 'r', encoding='utf-8', errors='replace') as f:
        return f.read()

def _pdf_to_text(path):
    import fitz
    doc = fitz.open(path)
    text = "\n".join(page.get_text() for page in doc)
    if text.strip():
        return text
    log.info("No text in PDF, trying OCR...")
    return _pdf_ocr(path)

def _pdf_ocr(path):
    from pdf2image import convert_from_path
    import pytesseract
    images = convert_from_path(path, dpi=200)
    text = "\n".join(pytesseract.image_to_string(img) for img in images)
    return text

def _epub_to_text(path):
    try:
        r = subprocess.run(['pandoc', path, '-t', 'plain', '--wrap=none'],
                          capture_output=True, text=True, timeout=30)
        if r.returncode == 0 and r.stdout.strip():
            return r.stdout
    except:
        pass
    import zipfile, xml.etree.ElementTree as ET
    texts = []
    with zipfile.ZipFile(path) as z:
        for name in z.namelist():
            if name.endswith(('.xhtml', '.html', '.htm', '.xml')):
                try:
                    root = ET.fromstring(z.read(name))
                    texts.append(''.join(root.itertext()))
                except:
                    pass
    return '\n'.join(texts)

def _docx_to_text(path):
    from docx import Document
    doc = Document(path)
    return '\n'.join(p.text for p in doc.paragraphs)

def _html_to_text(path):
    from html.parser import HTMLParser
    class TextExtractor(HTMLParser):
        def __init__(self):
            super().__init__()
            self.text = []
            self.skip = False
        def handle_starttag(self, tag, attrs):
            if tag in ('script', 'style'):
                self.skip = True
        def handle_endtag(self, tag):
            if tag in ('script', 'style'):
                self.skip = False
        def handle_data(self, data):
            if not self.skip:
                self.text.append(data)
    parser = TextExtractor()
    with open(path, 'r', encoding='utf-8', errors='replace') as f:
        parser.feed(f.read())
    return ''.join(parser.text)

def _image_to_text(path):
    import pytesseract
    from PIL import Image
    return pytesseract.image_to_string(Image.open(path))
