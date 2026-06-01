"""
@HengAudioBKBot — Telegram e-book to audiobook converter.
Reads PDF, EPUB, DOCX, TXT, images aloud with language detection + TTS.
"""
import os, sys, json, time, asyncio, re, html, uuid, logging
from pathlib import Path
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters
from converter import file_to_text
from tts_engine import synthesize

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
log = logging.getLogger(__name__)

TOKEN = os.environ.get("AUDIO_BOOK_TOKEN")
if not TOKEN:
    log.error("Set AUDIO_BOOK_TOKEN environment variable")
    sys.exit(1)

DATA_DIR = Path(__file__).parent / "data"
TMP_DIR = Path(__file__).parent / "tmp"
DATA_DIR.mkdir(exist_ok=True)
TMP_DIR.mkdir(exist_ok=True)

CHUNK_SIZE = 4000
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB
CACHE_TTL = 86400  # 24h

def get_user_path(user_id):
    p = TMP_DIR / str(user_id)
    p.mkdir(exist_ok=True)
    return p

def cleanup_path(p):
    for f in p.iterdir():
        try:
            if time.time() - f.stat().st_mtime > CACHE_TTL:
                f.unlink()
        except:
            pass

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🎧 *Audio Book Bot*\n\n"
        "Send me an e-book file and I'll read it aloud!\n\n"
        "Supported formats:\n"
        "📄 PDF, 📖 EPUB, 📝 DOCX, 📃 TXT, 🖼️ Images\n\n"
        "Commands:\n"
        "/help — Show help\n"
        "/status — Current session\n"
        "/stop — Stop playback\n"
        "/lang — Set TTS language\n"
        "/goto <page> — Jump to page\n"
        "/resume — Resume paused book\n\n"
        "_Powered by gTTS + Tesseract OCR_",
        parse_mode="Markdown"
    )

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await start(update, context)

async def handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_dir = get_user_path(user.id)
    cleanup_path(user_dir)

    file_id = None
    file_name = "unknown"
    if update.message.document:
        file_id = update.message.document.file_id
        file_name = update.message.document.file_name or "document"
    elif update.message.photo:
        file_id = update.message.photo[-1].file_id
        file_name = "photo.jpg"
    else:
        await update.message.reply_text("Please send a file (PDF, EPUB, DOCX, TXT, or image).")
        return

    ext = os.path.splitext(file_name)[1].lower()
    sup = {'.pdf', '.epub', '.docx', '.txt', '.csv', '.json', '.html', '.htm',
           '.jpg', '.jpeg', '.png', '.tiff', '.tif', '.bmp', '.gif'}
    if ext not in sup:
        await update.message.reply_text(f"Unsupported format `{ext}`. Try PDF, EPUB, DOCX, TXT, or image.", parse_mode="Markdown")
        return

    msg = await update.message.reply_text("⏳ Downloading file...")
    try:
        file = await context.bot.get_file(file_id)
        in_path = str(user_dir / f"input{ext}")
        await file.download_to_drive(in_path)
    except Exception as e:
        await msg.edit_text(f"❌ Download failed: {e}")
        return

    await msg.edit_text("📖 Extracting text...")
    try:
        text = file_to_text(in_path)
    except Exception as e:
        await msg.edit_text(f"❌ Text extraction failed: {e}")
        return

    if not text.strip():
        await msg.edit_text("❌ No text could be extracted from this file.")
        return

    pages_est = max(1, len(text) // 2500)
    await msg.edit_text(f"✅ Extracted ~{len(text)} chars (~{pages_est} pages). Detecting language...")

    from langdet import detect_language
    lang = detect_language(text[:2000])
    lang_name = {"en": "English", "zh": "Chinese", "es": "Spanish", "fr": "French",
                 "de": "German", "ja": "Japanese", "ko": "Korean", "und": "Unknown"}.get(lang, lang)

    user_data = context.user_data
    user_data["text"] = text
    user_data["lang"] = lang
    user_data["page"] = 0
    user_data["pages"] = pages_est
    user_data["file_name"] = file_name
    user_data["status"] = "ready"

    keyboard = [
        [InlineKeyboardButton("▶️ Start Reading", callback_data="start_read")],
        [InlineKeyboardButton(f"🌐 Language: {lang_name}", callback_data="change_lang")],
    ]
    await msg.edit_text(f"📖 *{file_name}*\n~{pages_est} pages | 🌐 {lang_name}\n\nReady to read!",
                        parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user_data = context.user_data

    if data == "start_read":
        await stream_audio(query.message, context, user_data)
    elif data == "change_lang":
        keyboard = [
            [InlineKeyboardButton("English 🇬🇧", callback_data="setlang_en")],
            [InlineKeyboardButton("Chinese 🇨🇳", callback_data="setlang_zh")],
            [InlineKeyboardButton("Spanish 🇪🇸", callback_data="setlang_es")],
            [InlineKeyboardButton("French 🇫🇷", callback_data="setlang_fr")],
            [InlineKeyboardButton("German 🇩🇪", callback_data="setlang_de")],
            [InlineKeyboardButton("Auto-detect", callback_data="setlang_auto")],
        ]
        await query.edit_message_text("Select TTS language:", reply_markup=InlineKeyboardMarkup(keyboard))
    elif data.startswith("setlang_"):
        lang = data.replace("setlang_", "")
        user_data["lang"] = lang
        await query.edit_message_text(f"✅ Language set to {lang}. Send a file to begin.")
    elif data == "pause":
        user_data["status"] = "paused"
        keyboard = [[InlineKeyboardButton("▶️ Resume", callback_data="resume")],
                    [InlineKeyboardButton("⏹️ Stop", callback_data="stop")]]
        await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup(keyboard))
    elif data == "resume":
        user_data["status"] = "playing"
        await stream_audio(query.message, context, user_data, resume=True)
    elif data == "stop":
        user_data["status"] = "stopped"
        user_data["page"] = 0
        await query.edit_message_text("⏹️ Playback stopped. Send a new file or type /resume.")

async def stream_audio(message, context, user_data, resume=False):
    text = user_data.get("text", "")
    if not text:
        await message.reply_text("No book loaded. Send a file first.")
        return

    lang = user_data.get("lang", "en")
    user_data["status"] = "playing"
    total = len(text)
    start_pos = user_data.get("page", 0) * CHUNK_SIZE if resume else 0

    for i in range(start_pos, total, CHUNK_SIZE):
        if user_data.get("status") != "playing":
            break
        chunk = text[i:i + CHUNK_SIZE]
        if not chunk.strip():
            continue
        pct = min(100, (i + len(chunk)) * 100 // total)
        page_num = i // CHUNK_SIZE + 1

        status_text = f"📖 Page {page_num}/{user_data.get('pages', '?')} ({pct}%)"

        try:
            audio_path = synthesize(chunk, lang, str(TMP_DIR / f"{uuid.uuid4().hex}.mp3"))
            if audio_path and os.path.exists(audio_path):
                with open(audio_path, "rb") as f:
                    await message.reply_audio(
                        audio=f,
                        caption=status_text,
                        reply_markup=InlineKeyboardMarkup([
                            [InlineKeyboardButton("⏸️ Pause", callback_data="pause"),
                             InlineKeyboardButton("⏹️ Stop", callback_data="stop")],
                            [InlineKeyboardButton("⏭️ Skip", callback_data="next")],
                        ])
                    )
                os.unlink(audio_path)
            user_data["page"] = page_num
        except Exception as e:
            log.error(f"TTS error: {e}")
            await message.reply_text(f"❌ Audio generation failed at page {page_num}: {e}")
            break

        await asyncio.sleep(0.5)

    if user_data.get("status") == "playing":
        user_data["status"] = "done"
        await message.reply_text("✅ Finished reading! Send another file or /help.")

async def cmd_goto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_data = context.user_data
    text = user_data.get("text", "")
    if not text:
        await update.message.reply_text("No book loaded.")
        return
    try:
        page = int(context.args[0]) if context.args else 0
        user_data["page"] = max(0, min(page - 1, len(text) // CHUNK_SIZE))
        await update.message.reply_text(f"🔢 Jumped to page {user_data['page'] + 1}. Use /resume to play.")
    except:
        await update.message.reply_text("Usage: /goto <page_number>")

async def cmd_resume(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_data = context.user_data
    if user_data.get("text"):
        user_data["status"] = "playing"
        msg = await update.message.reply_text("▶️ Resuming...")
        await stream_audio(msg, context, user_data, resume=True)
    else:
        await update.message.reply_text("No paused book. Send a file first.")

async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_data = context.user_data
    if user_data.get("text"):
        page = user_data.get("page", 0) + 1
        total = user_data.get("pages", "?")
        pct = min(100, page * 100 // total) if total != "?" else 0
        await update.message.reply_text(f"📖 *Status*\nPage {page}/{total} ({pct}%)\nStatus: {user_data.get('status', 'idle')}",
                                        parse_mode="Markdown")
    else:
        await update.message.reply_text("No active book.")

async def cmd_stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["status"] = "stopped"
    await update.message.reply_text("⏹️ Stopped.")

async def cmd_lang(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("English 🇬🇧", callback_data="setlang_en")],
        [InlineKeyboardButton("Chinese 🇨🇳", callback_data="setlang_zh")],
        [InlineKeyboardButton("Spanish 🇪🇸", callback_data="setlang_es")],
        [InlineKeyboardButton("French 🇫🇷", callback_data="setlang_fr")],
        [InlineKeyboardButton("German 🇩🇪", callback_data="setlang_de")],
        [InlineKeyboardButton("Auto-detect", callback_data="setlang_auto")],
    ]
    await update.message.reply_text("Select TTS language:", reply_markup=InlineKeyboardMarkup(keyboard))

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    log.error(f"Update {update} caused error {context.error}")

def main():
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("goto", cmd_goto))
    app.add_handler(CommandHandler("resume", cmd_resume))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("stop", cmd_stop))
    app.add_handler(CommandHandler("lang", cmd_lang))
    app.add_handler(MessageHandler(filters.Document.ALL | filters.PHOTO, handle_file))
    app.add_handler(CallbackQueryHandler(button_callback))
    app.add_error_handler(error_handler)
    log.info("🤖 Audio Book Bot starting...")
    app.run_polling()

if __name__ == "__main__":
    main()
