from pathlib import Path

import pypdfium2 as pdfium
import pytest

from jobcv.config import Settings
from jobcv.cv.ingest import ocr_pdf, pdf_text_layer
from jobcv.pdf.render import pdf_filename, render_html, render_pdf
from jobcv.schemas import CV, Contact, Education, Experience, LanguageSkill

ROOT = Path(__file__).parents[2]

EN = CV(
    language="en",
    contact=Contact(name="Sarah Thompson", email="sarah@example.com", phone="+44 7700 900123",
                    location="Manchester, United Kingdom"),
    summary="Primary school teacher with 7 years of experience.",
    experience=[Experience(title="Primary School Teacher", employer="Oakfield Primary School",
                           location="Manchester", start="Sep 2019", end="Present",
                           bullets=["Marked weekly work for 28 pupils."])],
    education=[Education(degree="PGCE Primary Education", institution="University of Manchester",
                         start="2018", end="2019")],
    skills=["Report writing", "Microsoft Excel"],
    languages=[LanguageSkill(language="English", level="native")],
)

AR = CV(
    language="ar",
    contact=Contact(name="أحمد خالد المصري", email="ahmad@example.com", phone="+962 7 9000 0000",
                    location="عمّان، الأردن"),
    summary="محاسب بخبرة خمس سنوات في إعداد القيود اليومية والتسويات البنكية.",
    experience=[Experience(title="محاسب", employer="شركة النور للتجارة", location="عمّان",
                           start="2021", end="حتى الآن",
                           bullets=["إجراء التسويات البنكية الشهرية لثلاثة حسابات بنكية."])],
    education=[Education(degree="بكالوريوس محاسبة", institution="الجامعة الأردنية",
                         start="2015", end="2019")],
    skills=["Microsoft Excel", "التسويات البنكية"],
    languages=[LanguageSkill(language="العربية", level="اللغة الأم")],
)


def test_english_html_is_ltr_with_english_headings():
    html = render_html(EN)
    assert '<html lang="en" dir="ltr">' in html
    assert "Experience" in html and "Sarah Thompson" in html


def test_arabic_html_is_rtl_with_arabic_headings_and_font():
    html = render_html(AR)
    assert '<html lang="ar" dir="rtl">' in html
    assert "الخبرة العملية" in html and '"NotoNaskhArabic", "NotoSans"' in html
    assert "data:font/ttf;base64," in html  # fonts inlined, no system-font fallback
    assert '<bdi dir="ltr">ahmad@example.com</bdi>' in html  # LTR runs isolated inside RTL
    assert "شركة النور للتجارة، عمّان" in html  # Arabic comma, not ","


def test_html_escapes_cv_content():
    cv = EN.model_copy(update={"summary": "<script>alert(1)</script>"})
    assert "<script>alert(1)</script>" not in render_html(cv)


def test_empty_sections_are_left_out():
    html = render_html(CV(language="en", summary="x"))
    assert "Certifications" not in html and "Experience" not in html


def test_filename_from_job_title_and_company():
    assert pdf_filename("QA Engineer", "Acme / LLC") == "CV - QA Engineer - Acme LLC.pdf"
    assert pdf_filename("محاسب", "شركة النور") == "CV - محاسب - شركة النور.pdf"
    assert pdf_filename('a:b*c?"<>|', "x" * 300).endswith(".pdf")
    assert len(pdf_filename("t", "x" * 300)) <= 120


def embedded_fonts(pdf: Path) -> set[str]:
    import ctypes

    from pypdfium2 import raw

    names = set()
    doc = pdfium.PdfDocument(str(pdf))
    for page in doc:
        for obj in page.get_objects(filter=[raw.FPDF_PAGEOBJ_TEXT]):
            font = raw.FPDFTextObj_GetFont(obj.raw)
            n = raw.FPDFFont_GetBaseFontName(font, None, 0)
            buf = ctypes.create_string_buffer(n)
            raw.FPDFFont_GetBaseFontName(font, buf, n)
            names.add(buf.value.decode())
    return names


def test_english_pdf_is_single_column_text_pdf(tmp_path):
    out = render_pdf(EN, tmp_path / "en.pdf")
    assert all("NotoSans" in f for f in embedded_fonts(out)), embedded_fonts(out)
    text = pdf_text_layer(out.read_bytes())
    assert "Sarah Thompson" in text and "Oakfield Primary School" in text
    assert len(pdfium.PdfDocument(str(out))) == 1


@pytest.mark.slow
def test_arabic_pdf_embeds_arabic_font_and_is_correctly_shaped(tmp_path):
    out = render_pdf(AR, tmp_path / "ar.pdf")
    assert "NotoNaskhArabic" in " ".join(embedded_fonts(out))
    # OCR only reads connected, right-to-left Arabic correctly: a shaping/RTL bug fails here.
    s = Settings(_env_file=None, data_dir=tmp_path, tessdata_dir=ROOT / "tessdata")
    text = ocr_pdf(out.read_bytes(), s)
    for word in ["محاسب", "التسويات", "البنكية", "الخبرة", "العملية"]:
        assert word in text, word
