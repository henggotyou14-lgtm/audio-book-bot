"""
File-to-text converter for @HengAudioBKBot.
Supports PDF, EPUB, DOCX, TXT, Images via OCR.
"""
import os, subprocess, logging, zipfile
from pathlib import Path

log = logging.getLogger(__name__)

def file_to_text(file_path: str) -> str:
    ext = os.path.splitext(file_path)[1].lower()
    log.info(f"Converting {file_path} (ext={ext})")

    # Read magic bytes to detect actual file type
    with open(file_path, 'rb') as f:
        magic = f.read(8)

    is_pdf = magic[:4] == b'%PDF'
    is_zip = magic[:2] == b'PK'
    is_png = magic[:8] == b'\x89PNG\r\n\x1a\n'
    is_jpeg = magic[:3] == b'\xff\xd8\xff'

    # Try based on magic bytes first, fall back to extension
    if is_pdf or ext == '.pdf':
        return _pdf_or_epub_to_text(file_path, is_pdf)
    if ext == '.epub' or (is_zip and not ext):
        return _epub_to_text(file_path)
    if ext in ('.docx', '.doc'):
        return _docx_to_text(file_path)
    if ext in ('.txt', '.csv', '.json', '.md'):
        return _read_text(file_path)
    if ext in ('.html', '.htm'):
        return _html_to_text(file_path)
    if is_png or is_jpeg or ext in ('.jpg', '.jpeg', '.png', '.tiff', '.tif', '.bmp', '.gif'):
        return _image_to_text(file_path)
    # Unknown format - try as text, then try fitz, then try pandoc
    return _try_anything(file_path)

def _try_anything(path):
    """Last resort: try every parser we have."""
    try: return _read_text(path)
    except: pass
    try: return _pdf_or_epub_to_text(path, False)
    except: pass
    try: return _epub_to_text(path)
    except: pass
    try: return _image_to_text(path)
    except: pass
    raise ValueError("Could not extract text from this file. Try a different format.")

def _read_text(path):
    with open(path, 'r', encoding='utf-8', errors='replace') as f:
        return f.read()

def _pdf_or_epub_to_text(path, is_pdf):
    import fitz
    try:
        doc = fitz.open(path)
        text = "\n".join(page.get_text() for page in doc)
        doc.close()
        if text.strip():
            return text
        if is_pdf:
            return _pdf_ocr(path)
        return text
    except Exception as e:
        if is_pdf:
            raise
        return ""

def _pdf_ocr(path):
    from pdf2image import convert_from_path
    import pytesseract
    images = convert_from_path(path, dpi=200)
    text = "\n".join(pytesseract.image_to_string(img) for img in images)
    return text

def _epub_to_text(path):
    try:
        r = subprocess.run(['pandoc', path, '-t', 'plain', '--wrap=none'],
                          capture_output=True, text=True, timeout=60)
        if r.returncode == 0 and r.stdout.strip():
            return r.stdout
        log.warning(f"pandoc failed ({r.returncode}): {r.stderr[:200]}")
    except Exception as e:
        log.warning(f"pandoc error: {e}")
    try:
        import fitz
        doc = fitz.open(path)
        text = "\n".join(page.get_text() for page in doc)
        doc.close()
        if text.strip():
            return text
    except Exception as e:
        log.warning(f"fitz epub failed: {e}")
    try:
        import xml.etree.ElementTree as ET
        with zipfile.ZipFile(path) as z:
            texts = []
            for name in z.namelist():
                if name.endswith(('.xhtml', '.html', '.htm', '.xml', '.opf')):
                    try:
                        root = ET.fromstring(z.read(name))
                        texts.append(''.join(root.itertext()))
                    except:
                        pass
            if texts:
                return '\n'.join(texts)
    except zipfile.BadZipFile:
        log.warning("Not a valid zip file")
    except Exception as e:
        log.warning(f"zip parse error: {e}")
    raise ValueError("Could not extract text from EPUB. The file may be corrupted or DRM-protected.")

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
