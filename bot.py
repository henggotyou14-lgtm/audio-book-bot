"""
@HengAudioBKBot — reads e-books aloud. Clean single-audio interface.
Generates one MP3 per session, progress updates via editable message.
"""
import os, sys, json, time, asyncio, uuid, logging, tempfile, subprocess
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

TMP = Path(__file__).parent / "tmp"
TMP.mkdir(exist_ok=True)
DATA = Path(__file__).parent / "data"
DATA.mkdir(exist_ok=True)
SESSIONS_FILE = DATA / "sessions.json"

MAX_PAGES = 30
MAX_CHARS = MAX_PAGES * 3000

def load_session(uid):
    if SESSIONS_FILE.exists():
        try:
            all_s = json.loads(SESSIONS_FILE.read_text())
            return all_s.get(str(uid), {})
        except: return {}
    return {}

def save_session(uid, data):
    all_s = {}
    if SESSIONS_FILE.exists():
        try: all_s = json.loads(SESSIONS_FILE.read_text())
        except: pass
    all_s[str(uid)] = {"fname": data.get("fname"), "lang": data.get("lang"),
                       "page": data.get("page"), "pages": data.get("pages"),
                       "status": data.get("status"), "voice": data.get("voice", "default"),
                       "file_size": data.get("file_size"), "text_start": data.get("text","")[:100]}
    SESSIONS_FILE.write_text(json.dumps(all_s, indent=2))

def user_dir(uid):
    p = TMP / str(uid)
    p.mkdir(exist_ok=True)
    return p

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🎧 *Audio Book Bot*\n\n"
        "Send me a file (PDF, EPUB, DOCX, TXT, image) and I'll read it aloud.\n\n"
        "• Single audio file — no spam\n"
        "• Auto language detection\n"
        "• Supports text + scanned PDFs (OCR)\n"
        "• Max ~30 pages per session\n\n"
        "/help — Commands",
        parse_mode="Markdown"
    )

async def help_cmd(update, context):
    await update.message.reply_text(
        "*/start* — Welcome\n"
        "*/status* — Current session\n"
        "*/stop* — Stop and clear\n"
        "*/goto <n>* — Jump to page n\n"
        "*/url <link>* — Read from URL (bypasses 20MB limit)\n"
        "*/lang* — Change TTS language\n"
        "*/convert* — Open Web Converter for ebook format conversion\n\n"
        "📎 *Large files?* Use /url or compress at:\n"
        "https://macmac-mini.tail926eff.ts.net/convert",
        parse_mode="Markdown"
    )

async def handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    ud = user_dir(user.id)

    file_id = None
    fname = "unknown"
    if update.message.document:
        file_id = update.message.document.file_id
        fname = update.message.document.file_name or "doc"
    elif update.message.photo:
        file_id = update.message.photo[-1].file_id
        fname = "photo.jpg"
    else:
        await update.message.reply_text("Send a file (PDF, EPUB, DOCX, TXT, or image).")
        return

    ext = os.path.splitext(fname)[1].lower()
    if ext not in ('.pdf','.epub','.docx','.txt','.csv','.json','.md','.html','.htm',
                   '.jpg','.jpeg','.png','.tiff','.tif','.bmp','.gif'):
        await update.message.reply_text(f"Format `{ext}` not supported. Try PDF, EPUB, DOCX, TXT, or image.", parse_mode="Markdown")
        return

    # Warn if file is large, but try anyway
    file_obj = update.message.document or (update.message.photo and update.message.photo[-1])
    if file_obj and file_obj.file_size and file_obj.file_size > 20 * 1024 * 1024:
        keyboard = [[InlineKeyboardButton("📎 Use URL Instead", callback_data="show_url_help")]]
        await update.message.reply_text(
            "⚠️ File is over 20MB — Telegram bot API may reject download.\n\n"
            "Options:\n"
            "1. Send a direct URL with /url <link>\n"
            "2. Upload to Web Converter at https://macmac-mini.tail926eff.ts.net/convert to shrink it, then re-send",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    msg = await update.message.reply_text("📥 Downloading...")
    try:
        f = await context.bot.get_file(file_id)
        log.info(f"Got file: {f.file_id}, size: {f.file_size}, path: {f.file_path}")
        if not f.file_path:
            await msg.edit_text("❌ Telegram cannot serve this file (path unavailable). It may be too large.\n\nTry /url <direct_link> instead.")
            return
        in_path = str(ud / f"input{ext}")
        await f.download_to_drive(custom_path=in_path)
        actual_size = os.path.getsize(in_path)
        if actual_size < 100:
            await msg.edit_text(f"❌ File too small ({actual_size} bytes). The download may have expired. Try re-sending the file immediately or use /url <direct_link>.")
            return
    except Exception as e:
        await msg.edit_text(f"❌ Download failed: {e}\n\nThe file may be too large for Telegram's bot API (20MB limit). Try /url <direct_link> instead.")
        return

    await process_text(msg, context, user.id, fname, in_path, context.user_data)

async def process_text(msg, context, user_id, fname, in_path, ud):
    file_size = os.path.getsize(in_path) if os.path.exists(in_path) else 0
    await msg.edit_text(f"📖 Extracting text from {fname} ({_human_size(file_size)})...")
    # Quick integrity check
    if file_size < 100:
        await msg.edit_text(f"❌ File too small ({file_size} bytes). The download may have failed. Try using /url <direct_link> instead.")
        return
    with open(in_path, 'rb') as f:
        magic = f.read(4)
    if magic[:2] == b'PK':
        import zipfile
        try:
            with zipfile.ZipFile(in_path) as z:
                pass
        except zipfile.BadZipFile:
            await msg.edit_text("❌ File appears to be damaged (invalid ZIP/EPUB). Try re-downloading or use /url <direct_link>.")
            return
    try:
        text = file_to_text(in_path)
    except Exception as e:
        err = str(e)
        await msg.edit_text(f"❌ Could not read file: {err}\n\nTry using /url <direct_link> or convert via https://macmac-mini.tail926eff.ts.net/convert first.")
        return
    if not text.strip():
        await msg.edit_text("❌ No text found.")
        return

    pages = max(1, len(text) // 2000)
    total_chunks = min(pages, MAX_PAGES)
    await msg.edit_text(f"✅ {len(text)} chars (~{total_chunks} parts). Detecting language...")

    from langdet import detect_language
    lang = detect_language(text[:2000])
    lang_name = {"en":"English","zh":"中文","es":"Español","fr":"Français","de":"Deutsch"}.get(lang, lang)

    ud.clear()
    ud.update(text=text, lang=lang, pages=total_chunks, fname=fname, page=0, status="ready", file_size=file_size, voice="default")

    keyboard = [
        [InlineKeyboardButton(f"📖▶️🎧 Start Reading ({lang_name})", callback_data="start")],
        [InlineKeyboardButton("🎙️ Voice: Default", callback_data="voice_menu")]
    ]
    await msg.edit_text(
        f"📖 *{fname}* ({_human_size(file_size)}) — ~{total_chunks} parts • 🌐 {lang_name}\n\nReady to read aloud!",
        parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    data = q.data
    ud = context.user_data

    if data == "start":
        await generate_and_send(q.message, context, ud)
    elif data == "stop":
        ud["status"] = "stopped"
        await q.edit_message_text("⏹️ Stopped.")
    elif data == "voice_menu":
        from tts_engine import VOICES
        rows = []
        row = []
        for i, (vid, vinfo) in enumerate(VOICES.items()):
            current = ud.get("voice", "default")
            mark = "✅" if vid == current else ""
            row.append(InlineKeyboardButton(f"{mark}{vinfo['desc']}", callback_data=f"voice_{vid}"))
            if len(row) >= 2:
                rows.append(row)
                row = []
        if row:
            rows.append(row)
        rows.append([InlineKeyboardButton("🔙 Back", callback_data="back_to_ready")])
        await q.edit_message_text("🎙️ *Select Voice*", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(rows))
    elif data.startswith("voice_"):
        vid = data.replace("voice_", "")
        ud["voice"] = vid
        await q.edit_message_text(f"✅ Voice set to: {vid}. You can now start reading.", reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("📖▶️🎧 Start Reading", callback_data="start")]]
        ))
    elif data == "back_to_ready":
        lang_name = {"en":"English","zh":"中文"}.get(ud.get("lang","en"), ud.get("lang","en"))
        await q.edit_message_text(
            f"📖 *{ud.get('fname','Book')}* — ~{ud.get('pages','?')} parts • 🌐 {lang_name}\n\nReady to read aloud!",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(f"📖▶️🎧 Start Reading ({lang_name})", callback_data="start")],
                [InlineKeyboardButton("🎙️ Voice: " + ud.get("voice","default"), callback_data="voice_menu")],
            ])
        )
    elif data == "show_url_help":
        await q.edit_message_text(
            "📎 *URL Upload*\n\n"
            "Instead of uploading directly, share a direct download link:\n\n"
            "`/url https://example.com/book.pdf`\n\n"
            "Works with PDF, EPUB, DOCX, TXT files hosted online.\n"
            "No 20MB Telegram limit — downloads directly to server.",
            parse_mode="Markdown"
        )
    elif data == "lang_en":
        ud["lang"] = "en"
        await q.edit_message_text("🌐 Language: English. Send a file.")
    elif data == "lang_zh":
        ud["lang"] = "zh"
        await q.edit_message_text("🌐 Language: 中文. Send a file.")

async def generate_and_send(msg, context, ud):
    text = ud.get("text", "")
    if not text:
        await msg.reply_text("No book loaded.")
        return

    lang = ud.get("lang", "en")
    voice = ud.get("voice", "default")
    total_chars = min(len(text), MAX_CHARS)
    start_pos = (ud.get("page", 0)) * 3000
    ud["status"] = "generating"
    audio_files = []

    progress_msg = await msg.reply_text("🎧⏳ Generating audiobook... 0% of 100%")

    total_chunks = max(1, (total_chars - start_pos) // 3000 + 1)
    chunk_num = 0
    for i in range(start_pos, total_chars, 3000):
        if ud.get("status") in ("stopped", "paused"):
            break
        chunk = text[i:i+3000].strip()
        if not chunk:
            continue

        chunk_num += 1
        pct = min(99, (i - start_pos) * 100 // max(1, total_chars - start_pos))
        total = ud.get("pages", total_chunks)
        try:
            out = str(TMP / f"{uuid.uuid4().hex}.mp3")
            path = synthesize(chunk, lang, out, voice=voice)
            if path and os.path.getsize(path) > 0:
                audio_files.append(path)
                label = f"Part {chunk_num}/{total} ({pct}%)"
                await progress_msg.edit_text(f"🎧⏳ {label}")
            else:
                pass
        except Exception as e:
            log.warning(f"Chunk {i} failed: {e}")
            continue

    if not audio_files:
        await progress_msg.edit_text("❌ Could not generate audio.")
        return

    # Concatenate all audio files into one
    await progress_msg.edit_text("🎧 Combining audio...")
    final_path = str(TMP / f"book_{uuid.uuid4().hex}.mp3")
    try:
        list_path = str(TMP / f"list_{uuid.uuid4().hex}.txt")
        with open(list_path, "w") as f:
            for af in audio_files:
                f.write(f"file '{af}'\n")
        subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0",
                       "-i", list_path, "-c", "copy", final_path],
                      capture_output=True, timeout=60)
        os.unlink(list_path)
    except Exception as e:
        log.warning(f"Concat failed: {e}, sending individual chunks instead")
        await progress_msg.edit_text("✅ Done! Sending audio...")
        for af in audio_files:
            with open(af, "rb") as f:
                await msg.reply_audio(audio=f)
            try:
                os.unlink(af)
            except:
                pass
        await progress_msg.delete()
        for af in audio_files:
            try: os.unlink(af)
            except: pass
        return

    # Clean up chunks
    for af in audio_files:
        try: os.unlink(af)
        except: pass

    # Send single audio file
    await progress_msg.edit_text("✅ Done! Sending audio...")
    page_est = len(audio_files)
    total = ud.get("pages", page_est)
    btn_label = f"📖 Part 1-{page_est} 🎧✅ (100% of {total})"
    with open(final_path, "rb") as f:
        await msg.reply_audio(
            audio=f,
            caption=f"📖 {ud.get('fname','Book')} • {page_est} parts • 🌐 {lang}",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(btn_label, callback_data="noop")],
                [InlineKeyboardButton("⏹️ Stop", callback_data="stop")],
            ])
        )

    # Cleanup final
    try: os.unlink(final_path)
    except: pass
    await progress_msg.delete()
    ud["status"] = "done"
    # Persist session so /resume can work after restart

async def cmd_goto(update, context):
    ud = context.user_data
    if not ud.get("text"):
        await update.message.reply_text("No book loaded.")
        return
    try:
        p = int(context.args[0]) - 1
        ud["page"] = max(0, p)
        await update.message.reply_text(f"🔢 Jumped to part {p+1}. Send /start to read from there.")
    except:
        await update.message.reply_text("Usage: /goto 42")

async def cmd_status(update, context):
    ud = context.user_data
    if ud.get("text"):
        p = ud.get("page", 0) + 1
        t = ud.get("pages", "?")
        await update.message.reply_text(f"📖 Part {p}/{t} • Status: {ud.get('status','idle')}")
    else:
        await update.message.reply_text("No active book.")

async def cmd_stop(update, context):
    context.user_data["status"] = "stopped"
    await update.message.reply_text("⏹️ Stopped.")

async def cmd_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /url <direct_link_to_pdf_or_ebook>\n\nExample: /url https://example.com/book.pdf")
        return
    url = context.args[0]
    user = update.effective_user
    ud = user_dir(user.id)
    msg = await update.message.reply_text("📥 Downloading from URL...")
    try:
        import httpx
        async with httpx.AsyncClient(timeout=300, follow_redirects=True) as client:
            async with client.stream("GET", url) as r:
                disp = r.headers.get("content-disposition", "")
                fname = "document.pdf"
                if "filename=" in disp:
                    fname = disp.split("filename=")[-1].split(";")[0].strip('"\'')
                elif ".pdf" in url:
                    fname = url.split("/")[-1].split("?")[0] or "document.pdf"
                ext = os.path.splitext(fname)[1].lower()
                if ext not in ('.pdf','.epub','.docx','.txt','.json','.md','.html','.htm','.csv'):
                    fname += ext if ext else '.pdf'
                in_path = str(ud / f"input{ext}")
                with open(in_path, "wb") as fp:
                    async for chunk in r.aiter_bytes(65536):
                        fp.write(chunk)
    except Exception as e:
        await msg.edit_text(f"❌ URL download failed: {e}")
        return
    # Process the downloaded file
    context.user_data.clear()
    context.user_data["file_path"] = in_path
    await process_text(msg, context, user.id, fname, in_path, context.user_data)

async def cmd_lang(update, context):
    keyboard = [
        [InlineKeyboardButton("English", callback_data="lang_en"),
         InlineKeyboardButton("中文", callback_data="lang_zh")],
    ]
    await update.message.reply_text("Select language:", reply_markup=InlineKeyboardMarkup(keyboard))

async def error_handler(update, context):
    log.error(f"Error: {context.error}")

def _human_size(size):
    for u in ("B","KB","MB","GB"):
        if size < 1024: return f"{size:.0f}{u}"
        size /= 1024
    return f"{size:.0f}TB"

def main():
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("goto", cmd_goto))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("stop", cmd_stop))
    app.add_handler(CommandHandler("url", cmd_url))
    app.add_handler(CommandHandler("lang", cmd_lang))
    app.add_handler(MessageHandler(filters.Document.ALL | filters.PHOTO, handle_file))
    app.add_handler(CallbackQueryHandler(callback))
    app.add_error_handler(error_handler)
    log.info("🤖 Audio Book Bot starting...")
    app.run_polling()

if __name__ == "__main__":
    main()
