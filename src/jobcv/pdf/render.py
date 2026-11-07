"""Structured CV -> single-column ATS-friendly PDF (HTML template rendered by Chromium).

Direction comes from the CV language: Arabic -> RTL with Noto Naskh Arabic; English -> LTR.
Chromium does Arabic shaping and the bidi algorithm; LTR runs (email, phone, Latin skills)
are wrapped in <bdi> so they do not scramble the RTL line.

Known limit (tested 2026-11-08): Arabic PDFs LOOK right (shaping + RTL verified by OCR), but
text extractors such as PDFium/pdfminer return their text layer split and reversed. Typst
output behaved the same, so it's a reader-side limitation, not this renderer. ATS systems
may read Arabic PDFs poorly; a DOCX/plain-text export would solve that (not in Phase 1).
"""

import base64
import re
from functools import cache
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from jobcv.schemas import CV

HERE = Path(__file__).parent
_env = Environment(loader=FileSystemLoader(HERE / "templates"),
                   autoescape=select_autoescape(["html", "j2"]))

HEADINGS = {
    "en": {"summary": "Summary", "experience": "Experience", "education": "Education",
           "skills": "Skills", "certifications": "Certifications", "languages": "Languages",
           "other": "Additional information", "sep": " · ", "comma": ", "},
    "ar": {"summary": "الملخص", "experience": "الخبرة العملية", "education": "التعليم",
           "skills": "المهارات", "certifications": "الشهادات", "languages": "اللغات",
           "other": "معلومات إضافية", "sep": "، ", "comma": "، "},
}

_LATIN_ONLY = re.compile(r"^[\x00-\x7F]+$")


def render_html(cv: CV) -> str:
    lang = "ar" if cv.language == "ar" else "en"
    c = cv.contact
    contact_items = [
        {"text": text, "ltr": bool(_LATIN_ONLY.match(text))}
        for text in [c.email, c.phone, c.location, *c.links] if text
    ]
    return _env.get_template("cv.html.j2").render(
        cv=cv, lang=lang, dir="rtl" if lang == "ar" else "ltr", t=HEADINGS[lang],
        contact_items=contact_items,
        # static (non-variable) fonts: Chromium turns variable fonts into Type 3 glyph
        # drawings, which ATS parsers read badly
        fonts={"latin": _font_uri("NotoSans-Regular.ttf"),
               "latin_bold": _font_uri("NotoSans-Bold.ttf"),
               "arabic": _font_uri("NotoNaskhArabic-Regular.ttf"),
               "arabic_bold": _font_uri("NotoNaskhArabic-Bold.ttf")},
    )


@cache
def _font_uri(name: str) -> str:
    """Fonts are inlined as data URIs: Chromium blocks file:// fonts in set_content pages and
    silently falls back to system fonts (seen: Segoe UI), which differ per server."""
    data = base64.b64encode((HERE / "fonts" / name).read_bytes()).decode()
    return f"data:font/ttf;base64,{data}"


def render_pdf(cv: CV, out_path: Path) -> Path:
    """Blocking (sync Playwright). Call it from a worker thread, not inside an event loop."""
    from playwright.sync_api import sync_playwright

    out_path.parent.mkdir(parents=True, exist_ok=True)
    html = render_html(cv)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            page = browser.new_page()
            page.set_content(html, wait_until="load")
            page.evaluate("document.fonts.ready")
            page.pdf(path=str(out_path), format="A4", print_background=False,
                     prefer_css_page_size=True)
        finally:
            browser.close()
    return out_path


def pdf_filename(job_title: str, company: str, max_len: int = 120) -> str:
    def clean(s: str) -> str:
        s = re.sub(r'[<>:"/\\|?*\x00-\x1f]', " ", s)
        return re.sub(r"\s+", " ", s).strip(" .")

    stem = f"CV - {clean(job_title)} - {clean(company)}"
    return stem[: max_len - 4].rstrip(" .-") + ".pdf"
