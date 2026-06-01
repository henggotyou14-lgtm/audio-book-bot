"""
Text-to-Speech engine for @HengAudioBKBot.
Primary: gTTS (Google TTS, free, no API key)
Fallback: macOS `say` command
"""
import os, subprocess, logging, tempfile
from pathlib import Path
from gtts import gTTS

log = logging.getLogger(__name__)

LANG_MAP = {
    'en': 'en', 'zh': 'zh-CN', 'es': 'es', 'fr': 'fr',
    'de': 'de', 'ja': 'ja', 'ko': 'ko', 'pt': 'pt',
    'ru': 'ru', 'it': 'it', 'nl': 'nl', 'ar': 'ar',
    'hi': 'hi', 'th': 'th', 'vi': 'vi',
}

def synthesize(text: str, lang: str = 'en', out_path: str = None) -> str:
    if not out_path:
        out_path = tempfile.mktemp(suffix='.mp3')
    gtts_lang = LANG_MAP.get(lang, 'en')
    try:
        tts = gTTS(text[:500], lang=gtts_lang, slow=False)
        tts.save(out_path)
        if os.path.getsize(out_path) > 0:
            return out_path
    except Exception as e:
        log.warning(f"gTTS failed: {e}, trying macOS say...")
    return _macos_say(text[:500], out_path)

def _macos_say(text: str, out_path: str) -> str:
    wav = out_path.replace('.mp3', '.wav')
    safe = text.replace('"', '\\"').replace('\n', ' ')
    cmd = f'say -o "{wav}" --data-format=LEI16@22000 "{safe[:300]}"'
    subprocess.run(cmd, shell=True, timeout=30, stderr=subprocess.DEVNULL)
    if os.path.exists(wav):
        import subprocess
        subprocess.run(['ffmpeg', '-y', '-i', wav, '-codec:a', 'libmp3lame', '-b:a', '32k', out_path],
                      capture_output=True, timeout=30)
        try:
            os.unlink(wav)
        except:
            pass
        if os.path.exists(out_path):
            return out_path
    return None
