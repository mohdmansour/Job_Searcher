import re
from pathlib import Path

import pytest

from jobcv.config import Settings
from jobcv.cv.ingest import (
    OcrUnavailable,
    arabic_looks_reversed,
    clean_ocr_latin,
    extract_cv_text,
    pdf_text_layer,
)
from jobcv.text import detect_language

FX = Path(__file__).parents[1] / "fixtures"
ROOT = Path(__file__).parents[2]


@pytest.fixture
def s(tmp_path):
    return Settings(_env_file=None, data_dir=tmp_path, tessdata_dir=ROOT / "tessdata")


def test_language_detection():
    assert detect_language("Primary school teacher with 7 years") == "en"
    assert detect_language("محاسب بخبرة خمس سنوات في Excel") == "ar"
    assert detect_language("") == "en"


def test_reversed_arabic_is_detected():
    good = "إعداد القيود اليومية والتسويات البنكية والتقارير المالية الشهرية في الشركة"
    bad = "إعداد القيود ةيمويلا والتسويات ةيكنبلا ريراقتلاو ةيلاملا ةيرهشلا يف ةكرشلا"
    assert arabic_looks_reversed(good) is False
    assert arabic_looks_reversed(bad) is True


def test_english_text_pdf_uses_text_layer(s):
    r = extract_cv_text((FX / "cv_teacher_en.pdf").read_bytes(), s)
    assert r.method == "text" and r.language == "en"
    assert "Oakfield Primary School" in r.text


def test_scan_pdf_has_no_text_layer():
    assert pdf_text_layer((FX / "cv_teacher_scan.pdf").read_bytes()).strip() == ""


def test_scan_pdf_falls_back_to_ocr(s):
    r = extract_cv_text((FX / "cv_teacher_scan.pdf").read_bytes(), s)
    assert r.method == "ocr" and r.language == "en"
    assert "Oakfield" in r.text and "assessment" in r.text.lower()


def test_garbled_arabic_text_layer_falls_back_to_ocr(s):
    r = extract_cv_text((FX / "cv_accountant_ar.pdf").read_bytes(), s)
    assert r.language == "ar" and r.method == "ocr"
    assert not arabic_looks_reversed(r.text)
    for word in ["محاسب", "التسويات", "البنكية", "الأردنية"]:
        assert word in r.text, word


def test_missing_tesseract_gives_clear_error(tmp_path):
    s = Settings(_env_file=None, data_dir=tmp_path, tesseract_cmd=str(tmp_path / "nope.exe"))
    with pytest.raises(OcrUnavailable, match="Tesseract"):
        extract_cv_text((FX / "cv_teacher_scan.pdf").read_bytes(), s)


def test_not_a_pdf_is_rejected(s):
    with pytest.raises(ValueError, match="PDF"):
        extract_cv_text(b"hello", s)


# ---- OCR Latin noise cleanup (seen live: "Microsoft Excel" -> "Excel :1/]110:0501") ----
# as the real broken layer stores it: Arabic reversed, and Latin word order reversed in RTL lines
LAYER = "دمحأ · ahmad.masri@example.com · +962 7 9000 0000\nExcel Microsoft؛ ةيلاملا\n(2021 – 2019)"


def test_garbled_latin_is_replaced_by_the_real_phrase():
    out = clean_ocr_latin("\u200eExcel\u200f :1/]110:0501؛ إعداد التقارير المالية", LAYER)
    assert "Microsoft Excel" in out and ":1/]110" not in out
    assert "إعداد التقارير المالية" in out


def test_latin_noise_with_no_match_is_dropped():
    out = clean_ocr_latin("\u200e(lie ٠ ahmad.masri@example.com ٠ +962 7 9000 0000\u200f الأردن", LAYER)
    assert "lie" not in out
    assert "ahmad.masri@example.com" in out and "+962 7 9000 0000" in out and "الأردن" in out


def test_real_latin_and_years_are_kept():
    line = "مؤسسة الأمل، الزرقاء (2019 – 2021)"
    assert clean_ocr_latin(line, LAYER) == line


def test_bullet_read_as_arabic_zero_becomes_a_bullet():
    out = clean_ocr_latin("\u200e٠\u200f إجراء التسويات البنكية\nه إعداد القيود", LAYER)
    assert out.splitlines() == ["- إجراء التسويات البنكية", "- إعداد القيود"]
    assert "٠" not in out


def test_arabic_fixture_skills_come_out_clean(s):
    r = extract_cv_text((FX / "cv_accountant_ar.pdf").read_bytes(), s)
    assert "Microsoft Excel" in r.text
    assert not re.search(r"[:\]/]{1}\d{2,}", r.text), r.text
