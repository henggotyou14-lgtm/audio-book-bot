# 🎧 @HengAudioBKBot — Telegram E-book to Audiobook Bot

Convert any e-book file to speech directly in Telegram. Supports PDF, EPUB, DOCX, TXT, and images (OCR).

## Features

- **📚 Multi-format** — PDF, EPUB, DOCX, TXT, images (JPG, PNG, TIFF)
- **🌐 Language detection** — Auto-detects Chinese, Japanese, Korean, Thai, Arabic, Cyrillic, Latin
- **🗣️ Text-to-Speech** — gTTS (Google TTS, free) + macOS `say` fallback
- **📖 Page-by-page streaming** — Audio sent in chunks with progress tracking
- **⏯️ Playback controls** — Start, Pause, Resume, Stop, Jump to page
- **🖼️ OCR** — Scanned PDFs and images via Tesseract
- **🎯 Format auto-conversion** — heic→jpg, webp→png via file-bot integration

## Commands

| Command | Description |
|---------|-------------|
| `/start` | Show welcome message |
| `/help` | Show help |
| `/status` | Current playback status |
| `/stop` | Stop playback |
| `/goto <page>` | Jump to specific page |
| `/resume` | Resume paused book |
| `/lang` | Change TTS language |

## Quick Start

```bash
# Set token
export AUDIO_BOOK_TOKEN="your_bot_token"

# Install deps
pip install -r requirements.txt

# Run
python bot.py
```

## Architecture

```
Telegram ──→ bot.py (PTB handlers)
                ├── converter.py (PDF/EPUB/DOCX/TXT/image → text)
                ├── tts_engine.py (gTTS → MP3)
                └── langdet.py (unicode-based language detection)
```

## Deployment (Mac Mini)

Running under PM2:

```bash
pm2 start ecosystem.config.js --only audio-book-bot
```

## Dependencies

- `python-telegram-bot` — Telegram API
- `gTTS` — Google Text-to-Speech
- `PyMuPDF` — PDF text extraction
- `pytesseract` + `tesseract` — OCR
- `pdf2image` + `poppler` — PDF to images
- `python-docx` — DOCX parsing
- `pandoc` — EPUB conversion
- `ffmpeg` — Audio processing
