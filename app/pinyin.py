from __future__ import annotations

import re
import unicodedata
from collections.abc import Collection

OPEN, CLOSE = "\ue000", "\ue001"
_TONES = {"\u0304": 1, "\u0301": 2, "\u030c": 3, "\u0300": 4}
_CONTOURS = {1: "⁵⁵", 2: "³⁵", 3: "²¹⁴", 4: "⁵¹", 5: ""}


def _syllable(value: str) -> tuple[str, int, bool]:
    value = unicodedata.normalize("NFD", value.lower().replace("u:", "ü").replace("v", "ü"))
    # An attached r is a suffix, except in the independent syllable er/ér/ěr/èr.
    unmarked = "".join(c for c in value if c not in _TONES)
    erhua = value.endswith("r") and unmarked != "er"
    if erhua:
        value = value[:-1]
    number = None
    if value and value[-1] in "012345":
        number = int(value[-1]) or 5
        value = value[:-1]
    marks = [c for c in value if c in _TONES]
    if len(marks) > 1 or (marks and number is not None):
        raise ValueError("use one tone mark or one trailing tone number per pinyin syllable")
    tone = _TONES[marks[0]] if marks else (number if number is not None else 5)
    plain = unicodedata.normalize("NFC", "".join(c for c in value if c not in _TONES))
    if not re.fullmatch(r"[a-züê]+", plain):
        raise ValueError(f"invalid pinyin syllable: {value!r}")
    return plain, tone, erhua


def _erhua(phones: str) -> str:
    """Broad Mandarin rhotic finals, expressed with ZONOS3 inventory symbols.

    Use a nonsyllabic rhotic offglide (ɚ̯), rather than an extra er syllable.
    Dental codas/front offglides disappear; velar nasals leave nasalization.
    This is a deterministic broad transcription, not a regional accent model.
    """
    endings = {
        "aŋ": "ãɚ̯̃", "əŋ": "ə̃ɚ̯̃", "iŋ": "ĩɚ̯̃", "ʊŋ": "ʊ̃ɚ̯̃",
        "an": "aɚ̯", "ɛn": "aɚ̯", "ən": "ɚ", "in": "jɚ", "yn": "ɥɚ",
        "ai̯": "aɚ̯", "ei̯": "ɚ", "au̯": "au̯ɚ̯", "ou̯": "ou̯ɚ̯",
        "ɻ̩": "ɚ", "ɹ̩": "ɚ", "ʐ̩": "ɚ", "z̩": "ɚ",
        "a": "aɚ̯", "e": "ɚ", "ɛ": "ɚ", "ə": "ɚ", "ɤ": "ɚ",
        "o": "oɚ̯", "ɔ": "ɔɚ̯", "u": "uɚ̯", "i": "jɚ", "y": "ɥɚ",
    }
    for ending in sorted(endings, key=len, reverse=True):
        if phones.endswith(ending):
            return phones[:-len(ending)] + endings[ending]
    raise ValueError("erhua suffix is not supported for this syllable")


def _group(value: str, symbols: Collection[str]) -> str:
    from pinyin_to_ipa import pinyin_to_ipa

    words = value.split()
    if not words:
        raise ValueError("pinyin brackets must contain at least one syllable")
    syllables = [_syllable(word) for word in words]
    tones = [tone for _, tone, _ in syllables]
    # A bracket explicitly defines one prosodic unit. No rule crosses its edge.
    # Use original tones, so every non-final 3 in a contiguous run becomes 2.
    surfaces = [2 if tone == 3 and i + 1 < len(tones) and tones[i + 1] == 3 else tone
                for i, tone in enumerate(tones)]
    output = []
    for (plain, _, erhua), tone in zip(syllables, surfaces):
        try:
            # Ask for a neutral transcription: append the ZONOS3-style tone
            # contour after the whole syllable, not inside its vowel/nasal.
            variants = pinyin_to_ipa(plain + "5")
            phones = "".join(next(iter(variants)))
        except (ValueError, StopIteration) as exc:
            raise ValueError(f"unsupported pinyin syllable: {plain!r}") from exc
        if erhua:
            phones = _erhua(phones)
        phones += _CONTOURS[tone]
        unknown = set(phones) - set(symbols)
        if unknown:
            raise ValueError(f"pinyin conversion produced unsupported model phonemes: {sorted(unknown)}")
        output.append(phones)
    return OPEN + "".join(output) + CLOSE


def convert_pinyin(text: str, *, enabled: bool, language: str,
                   symbols: Collection[str] | None = None) -> str:
    """Convert bracketed syllables only for enabled Mandarin requests."""
    if not enabled or language != "cmn" or not any(c in text for c in "[]"):
        return text
    if not symbols:
        raise ValueError("pinyin input requires a checkpoint with phoneme text rows enabled")
    parts: list[str] = []
    pos = 0
    while pos < len(text):
        char = text[pos]
        if char == OPEN:
            # Existing explicit IPA groups are passed through byte-for-byte.
            end = text.find(CLOSE, pos + 1)
            if end < 0:
                raise ValueError("unbalanced IPA group")
            parts.append(text[pos:end + 1])
            pos = end + 1
        elif char == "[":
            end = text.find("]", pos + 1)
            if end < 0 or "[" in text[pos + 1:end]:
                raise ValueError("unbalanced or nested pinyin brackets")
            parts.append(_group(text[pos + 1:end], symbols))
            pos = end + 1
        elif char == "]":
            raise ValueError("unbalanced pinyin brackets")
        else:
            parts.append(char)
            pos += 1
    return "".join(parts)
