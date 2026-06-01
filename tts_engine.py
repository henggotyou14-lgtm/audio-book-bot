"""
Text-to-Speech engine for @HengAudioBKBot.
Supports voice selection: male, female, high pitch, low voice.
"""
import os, subprocess, logging, tempfile
from pathlib import Path

log = logging.getLogger(__name__)

LANG_MAP = {
    'en': 'en', 'zh': 'zh-CN', 'es': 'es', 'fr': 'fr',
    'de': 'de', 'ja': 'ja', 'ko': 'ko', 'pt': 'pt',
    'ru': 'ru', 'it': 'it', 'nl': 'nl', 'ar': 'ar',
    'hi': 'hi', 'th': 'th', 'vi': 'vi',
}

# macOS voices for different styles
# Use `say -v '?'` to list all available voices
VOICES = {
    "default":     {"say": None, "gtts": None, "desc": "Default (gTTS)"},
    "male_deep":   {"say": "Alex",       "gtts": None, "desc": "Male deep (Alex)"},
    "female":      {"say": "Samantha",   "gtts": None, "desc": "Female (Samantha)"},
    "male_soft":   {"say": "Tom",        "gtts": None, "desc": "Male soft (Tom)"},
    "female_warm": {"say": "Veena",      "gtts": None, "desc": "Female warm (Veena)"},
    "high_pitch":  {"say": "Cellos",     "gtts": None, "desc": "High pitch (Cellos)"},
    "narrative":   {"say": "Zarvox",     "gtts": None, "desc": "Narrative (Zarvox)"},
    "british":     {"say": "Daniel",     "gtts": None, "desc": "British male (Daniel)"},
    "australian":  {"say": "Karen",      "gtts": None, "desc": "Australian female (Karen)"},
}

def synthesize(text: str, lang: str = 'en', out_path: str = None, voice: str = "default") -> str:
    if not out_path:
        out_path = tempfile.mktemp(suffix='.mp3')
    text = text[:500]

    gtts_lang = LANG_MAP.get(lang, 'en')

    # Try gTTS for default voice (no specific macOS voice selected)
    if voice == "default":
        try:
            from gtts import gTTS
            tts = gTTS(text, lang=gtts_lang, slow=False)
            tts.save(out_path)
            if os.path.getsize(out_path) > 0:
                return out_path
        except Exception as e:
            log.warning(f"gTTS failed: {e}, falling back to macOS say...")

    # Use macOS say with specific voice
    return _macos_say(text, out_path, voice)

def _macos_say(text: str, out_path: str, voice_id: str = "default") -> str:
    wav = out_path.replace('.mp3', '.wav')
    safe = text.replace('"', '\\"').replace('\n', ' ')

    voice_info = VOICES.get(voice_id, VOICES["default"])
    voice_arg = f" -v {voice_info['say']}" if voice_info['say'] else ""
    rate_arg = ""
    if "high_pitch" in voice_id:
        rate_arg = " --rate=280"
    elif "deep" in voice_id or "male_deep" in voice_id:
        rate_arg = " --rate=140"

    cmd = f'say{voice_arg}{rate_arg} -o "{wav}" --data-format=LEI16@22000 "{safe[:300]}"'
    subprocess.run(cmd, shell=True, timeout=30, stderr=subprocess.DEVNULL)

    if os.path.exists(wav):
        subprocess.run(['ffmpeg', '-y', '-i', wav, '-codec:a', 'libmp3lame', '-b:a', '32k', out_path],
                      capture_output=True, timeout=30)
        try:
            os.unlink(wav)
        except:
            pass
        if os.path.exists(out_path):
            return out_path
    return None

def get_voice_options():
    return list(VOICES.keys())
