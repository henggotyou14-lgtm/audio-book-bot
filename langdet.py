"""
Language detection for @HengAudioBKBot.
"""
import re
from pathlib import Path

CHARSETS = {
    'zh': (0x4E00, 0x9FFF, 0x3400, 0x4DBF, 0x20000, 0x2A6DF),
    'ja': (0x3040, 0x309F, 0x30A0, 0x30FF),
    'ko': (0xAC00, 0xD7AF, 0x1100, 0x11FF),
    'th': (0x0E00, 0x0E7F),
    'ar': (0x0600, 0x06FF),
    'ru': (0x0400, 0x04FF),
    'vi': (0x01A0, 0x01B0, 0x1EA0, 0x1EF9),
}

def detect_language(text: str) -> str:
    if not text:
        return 'en'
    text = text[:2000]
    scores = {}
    for lang, ranges in CHARSETS.items():
        count = 0
        for ch in text:
            cp = ord(ch)
            for i in range(0, len(ranges), 2):
                if ranges[i] <= cp <= ranges[i+1]:
                    count += 1
                    break
        scores[lang] = count / max(len(text), 1)
    if scores:
        best = max(scores, key=scores.get)
        if scores[best] > 0.05:
            return best
    # Simple English/Latin detection
    alpha = len(re.findall(r'[a-zA-Z]', text))
    if alpha > len(text) * 0.3:
        return 'en'
    return 'en'
