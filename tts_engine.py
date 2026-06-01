"""
Text-to-Speech engine for @HengAudioBKBot.
Primary: edge-tts (Microsoft Neural TTS, free, natural voices)
Fallback: gTTS, then macOS say
"""
import os, asyncio, subprocess, logging, tempfile
from pathlib import Path

log = logging.getLogger(__name__)

LANG_MAP = {
    'en': 'en-US', 'zh': 'zh-CN', 'es': 'es-ES', 'fr': 'fr-FR',
    'de': 'de-DE', 'ja': 'ja-JP', 'ko': 'ko-KR', 'pt': 'pt-PT',
    'ru': 'ru-RU', 'it': 'it-IT', 'nl': 'nl-NL', 'ar': 'ar-SA',
    'hi': 'hi-IN', 'th': 'th-TH', 'vi': 'vi-VN',
}

# Edge TTS voices — natural, expressive, emotional
# Selected for quality and variety
VOICES = {
    "default":     {"edge": None, "desc": "Default (auto-select)"},
    "aria":        {"edge": "en-US-AriaNeural", "desc": "Aria (🇺🇸 female, expressive)"},
    "ava":         {"edge": "en-US-AvaMultilingualNeural", "desc": "Ava (🇺🇸 female, caring)"},
    "emma":        {"edge": "en-US-EmmaMultilingualNeural", "desc": "Emma (🇺🇸 female, cheerful)"},
    "jenny":       {"edge": "en-US-JennyNeural", "desc": "Jenny (🇺🇸 female, friendly)"},
    "michelle":    {"edge": "en-US-MichelleNeural", "desc": "Michelle (🇺🇸 female, pleasant)"},
    "andrew":      {"edge": "en-US-AndrewMultilingualNeural", "desc": "Andrew (🇺🇸 male, warm)"},
    "brian":       {"edge": "en-US-BrianNeural", "desc": "Brian (🇺🇸 male, sincere)"},
    "christopher": {"edge": "en-US-ChristopherNeural", "desc": "Christopher (🇺🇸 male, authoritative)"},
    "guy":         {"edge": "en-US-GuyNeural", "desc": "Guy (🇺🇸 male, passionate)"},
    "sonia":       {"edge": "en-GB-SoniaNeural", "desc": "Sonia (🇬🇧 female, warm)"},
    "ryan":        {"edge": "en-GB-RyanNeural", "desc": "Ryan (🇬🇧 male, friendly)"},
    "natasha":     {"edge": "en-AU-NatashaNeural", "desc": "Natasha (🇦🇺 female, friendly)"},
}

def synthesize(text: str, lang: str = 'en', out_path: str = None, voice: str = "default") -> str:
    if not out_path:
        out_path = tempfile.mktemp(suffix='.mp3')
    text = text[:500]

    voice_info = VOICES.get(voice, VOICES["default"])
    edge_voice = voice_info["edge"]

    if edge_voice:
        result = _edge_tts(text, out_path, edge_voice)
        if result:
            return result

    # Fallback: gTTS
    gtts_lang = LANG_MAP.get(lang, 'en-US')[:2]
    try:
        from gtts import gTTS
        tts = gTTS(text, lang=gtts_lang, slow=False)
        tts.save(out_path)
        if os.path.getsize(out_path) > 0:
            return out_path
    except Exception as e:
        log.warning(f"gTTS failed: {e}")

    # Last resort: macOS say
    return _macos_say(text, out_path)

def _edge_tts(text: str, out_path: str, voice: str) -> str:
    try:
        import edge_tts
        async def _run():
            communicate = edge_tts.Communicate(text, voice)
            await communicate.save(out_path)
        asyncio.run(_run())
        if os.path.exists(out_path) and os.path.getsize(out_path) > 0:
            return out_path
    except Exception as e:
        log.warning(f"edge-tts failed ({voice}): {e}")
    return None

def _macos_say(text: str, out_path: str) -> str:
    wav = out_path.replace('.mp3', '.wav')
    safe = text.replace('"', '\\"').replace('\n', ' ')
    cmd = f'say -o "{wav}" --data-format=LEI16@22000 "{safe[:300]}"'
    subprocess.run(cmd, shell=True, timeout=30, stderr=subprocess.DEVNULL)
    if os.path.exists(wav):
        subprocess.run(['ffmpeg', '-y', '-i', wav, '-codec:a', 'libmp3lame', '-b:a', '32k', out_path],
                      capture_output=True, timeout=30)
        try: os.unlink(wav)
        except: pass
        if os.path.exists(out_path):
            return out_path
    return None

def get_voice_options():
    return list(VOICES.keys())
