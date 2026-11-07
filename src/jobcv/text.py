"""Small text helpers shared by several modules."""

import re
import unicodedata

_ARABIC = re.compile(r"[؀-ۿݐ-ݿࢠ-ࣿﭐ-﷿ﹰ-﻿]")
_LATIN = re.compile(r"[A-Za-z]")


def detect_language(text: str, arabic_ratio: float = 0.3) -> str:
    """'ar' if Arabic letters are more than `arabic_ratio` of all letters, else 'en'."""
    ar = len(_ARABIC.findall(text))
    la = len(_LATIN.findall(text))
    if ar + la == 0:
        return "en"
    return "ar" if ar / (ar + la) > arabic_ratio else "en"


_DIACRITICS = re.compile(r"[ً-ْٰـ]")  # Arabic harakat + tatweel


def normalize(text: str) -> str:
    """Lowercase, strip accents/Arabic diacritics/punctuation, collapse whitespace."""
    text = unicodedata.normalize("NFKC", text or "").casefold()
    text = _DIACRITICS.sub("", text)
    text = re.sub(r"[أإآ]", "ا", text).replace("ة", "ه").replace("ى", "ي")
    text = "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c))
    text = re.sub(r"[^\w\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()
