"""CV PDF -> plain text (+ language). Text layer first, OCR when the text layer is unusable.

Unusable = almost no text (a scan), or Arabic stored in visual order. Many PDF writers store
Arabic glyph runs reversed, so extractors return words backwards (e.g. 'ةيمويلا' for 'اليومية').
The Reviewer checks facts against this raw text, so we OCR instead of trusting broken text.

Never logs CV content.
"""

import os
import re
from dataclasses import dataclass
from typing import Literal

import pypdfium2 as pdfium

from jobcv.config import Settings
from jobcv.text import detect_language


class OcrUnavailable(RuntimeError):
    pass


@dataclass
class ExtractedText:
    text: str
    language: Literal["en", "ar"]
    method: Literal["text", "ocr"]
    pages: int


_AR_WORD = re.compile(r"[ء-يٱ-ۓ]{3,}")


def arabic_looks_reversed(text: str, threshold: float = 0.15) -> bool:
    """Reversed Arabic words show up as words starting with 'ة' (never valid) or ending with
    'لا' (a reversed 'ال' prefix). Compare against the correct-order signals."""
    words = _AR_WORD.findall(text)
    if len(words) < 5:
        return False
    reversed_ = sum(1 for w in words if w.startswith("ة") or (w.endswith("لا") and len(w) > 4))
    return reversed_ / len(words) > threshold


def _open(pdf: bytes) -> pdfium.PdfDocument:
    if not pdf.startswith(b"%PDF"):
        raise ValueError("file is not a PDF")
    return pdfium.PdfDocument(pdf)


def pdf_text_layer(pdf: bytes) -> str:
    doc = _open(pdf)
    try:
        return "\n".join(doc[i].get_textpage().get_text_range() for i in range(len(doc)))
    finally:
        doc.close()


def ocr_pdf(pdf: bytes, s: Settings) -> str:
    import pytesseract

    pytesseract.pytesseract.tesseract_cmd = s.tesseract_cmd
    tessdata = s.tessdata_dir.resolve()
    if not (tessdata / "ara.traineddata").exists():
        raise OcrUnavailable(f"Tesseract language data missing in {tessdata} (need eng + ara)")
    # --tessdata-dir with a quoted path breaks on Windows; the env var works everywhere.
    os.environ["TESSDATA_PREFIX"] = str(tessdata)
    config = "--psm 4"
    doc = _open(pdf)
    try:
        pages = []
        for i in range(len(doc)):
            image = doc[i].render(scale=300 / 72).to_pil()  # ~300 dpi
            try:
                pages.append(pytesseract.image_to_string(image, lang="ara+eng", config=config))
            except (pytesseract.TesseractNotFoundError, FileNotFoundError) as e:
                raise OcrUnavailable(f"Tesseract not found at {s.tesseract_cmd}") from e
        return "\n".join(pages)
    finally:
        doc.close()


_AR_CHARS = "\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF"
_LAT_TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9@._%+\-]*[A-Za-z0-9]|[A-Za-z0-9]")
_LAT_PHRASE = re.compile(r"[A-Za-z][A-Za-z0-9@._%+\-]*(?: [A-Za-z][A-Za-z0-9@._%+\-]*)*")
_FOREIGN_RUN = re.compile(rf"[^\s{_AR_CHARS}]+(?:[ \t]+[^\s{_AR_CHARS}]+)*")
_BIDI_MARKS = re.compile("[\u200e\u200f\u202a-\u202e\u2066-\u2069]")
# OCR reads a bullet "•" as Arabic zero, "ه", "®", "*" or "o"
_BULLET = re.compile(r"^\s*[\u0660\u2022*\u00aeo\u0647\u00b7]\s+")


def clean_ocr_latin(ocr: str, text_layer: str) -> str:
    """Repair Latin text that OCR garbled inside Arabic lines (seen live: "Microsoft Excel"
    -> "Excel :1/]110:0501"). When the PDF has a text layer, every real Latin word is in it,
    spelled correctly (only the Arabic there is scrambled). So a Latin run in the OCR output
    with words missing from the text layer is noise: replace it with the text-layer phrase
    that shares a real word, or drop it. Also turns OCR'd bullet glyphs into "- " so they can
    never be read as the digit 0. Without a text layer (a true scan) Latin is left as OCR'd."""
    vocab = {t.lower() for t in _LAT_TOKEN.findall(text_layer)}
    phrases = []
    for layer_line in text_layer.splitlines():
        rtl_line = detect_language(layer_line) == "ar"
        for phrase in _LAT_PHRASE.findall(layer_line):
            # this path only runs for layers that store Arabic in visual order; there the
            # words of a Latin phrase inside an Arabic line come out reversed too
            # (seen: "Excel Microsoft" for "Microsoft Excel")
            phrases.append(" ".join(reversed(phrase.split())) if rtl_line else phrase)

    def fix_run(m: re.Match) -> str:
        run = m.group(0)
        tokens = _LAT_TOKEN.findall(run)
        if not tokens or not vocab or all(t.lower() in vocab for t in tokens):
            return run
        known = [t.lower() for t in tokens if t.lower() in vocab and t.isalpha() and len(t) >= 3]
        for word in known:
            matches = [p for p in phrases if word in p.lower().split()]
            if matches:
                return max(matches, key=len)
        return " ".join(t for t in tokens if t.lower() in vocab)  # drop only the noise

    lines = []
    for line in _BIDI_MARKS.sub("", ocr).splitlines():
        line = _BULLET.sub("- ", line)
        line = _FOREIGN_RUN.sub(fix_run, line)  # before the next step: "\u0660" splits the runs
        line = re.sub(r"\s\u0660\s", " \u00b7 ", line)  # Arabic zero used as a separator dot
        lines.append(re.sub(r"[ \t]{2,}", " ", line).strip())
    return "\n".join(lines)


def extract_cv_text(pdf: bytes, s: Settings) -> ExtractedText:
    text = pdf_text_layer(pdf)
    pages = len(_open(pdf))
    method: Literal["text", "ocr"] = "text"
    if len(text.strip()) < s.ocr_min_chars or (
        detect_language(text) == "ar" and arabic_looks_reversed(text)
    ):
        text, method = clean_ocr_latin(ocr_pdf(pdf, s), text), "ocr"
    text = re.sub(r"[ \t]+\n", "\n", text).strip()
    return ExtractedText(text=text, language=detect_language(text), method=method, pages=pages)
