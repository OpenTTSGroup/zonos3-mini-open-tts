from __future__ import annotations

from collections.abc import Collection

from .pinyin import CLOSE, OPEN


def convert_ipa(text: str, *, enabled: bool, symbols: Collection[str] | None = None) -> str:
    """Replace {{IPA}} groups without normalizing their phonemes or tones."""
    if not enabled or ("{{" not in text and "}}" not in text):
        return text
    parts: list[str] = []
    pos = 0
    while pos < len(text):
        if text[pos] == OPEN:
            # Explicit Unicode groups belong to the upstream parser, unchanged.
            end = text.find(CLOSE, pos + 1)
            if end < 0:
                raise ValueError("unbalanced IPA group")
            parts.append(text[pos:end + 1])
            pos = end + 1
        elif text.startswith("{{", pos):
            end = text.find("}}", pos + 2)
            if end < 0:
                raise ValueError("unbalanced {{IPA}} group")
            phones = text[pos + 2:end]
            if not phones:
                raise ValueError("{{IPA}} group must not be empty")
            if any(c in phones for c in "{}" + OPEN + CLOSE):
                raise ValueError("nested IPA boundaries are not allowed")
            if not symbols:
                raise ValueError("IPA input requires a checkpoint with phoneme text rows enabled")
            unknown = set(phones) - set(symbols)
            if unknown:
                raise ValueError(f"IPA group contains unsupported model phonemes: {sorted(unknown)}")
            parts.append(OPEN + phones + CLOSE)
            pos = end + 2
        elif text.startswith("}}", pos):
            raise ValueError("unbalanced {{IPA}} group")
        else:
            parts.append(text[pos])
            pos += 1
    return "".join(parts)
