"""Create fictional test CV PDFs in tests/fixtures/ (no real person's data).

uv run python scripts/make_cv_fixtures.py
- cv_teacher_en.pdf : text PDF, primary school teacher (used by the QA fidelity test)
- cv_accountant_ar.pdf : text PDF in Arabic (RTL)
- cv_teacher_scan.pdf : the English CV rasterized to images only (OCR fallback test)
"""

from pathlib import Path

import pypdfium2 as pdfium
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "tests" / "fixtures"
FONTS = ROOT / "src" / "jobcv" / "pdf" / "fonts"

TEACHER_EN = """
<h1>Sarah Thompson</h1>
<p>sarah.thompson@example.com · +44 7700 900123 · Manchester, United Kingdom</p>
<h2>Summary</h2>
<p>Primary school teacher with 7 years of experience teaching Year 3 and Year 4 pupils.
Careful marker of pupils' work, writer of assessment criteria, and author of termly progress reports.</p>
<h2>Experience</h2>
<h3>Primary School Teacher — Oakfield Primary School, Manchester (Sep 2019 – Present)</h3>
<ul>
<li>Marked and graded weekly maths and English work for a class of 28 pupils, identifying recurring errors.</li>
<li>Wrote assessment criteria (rubrics) for end-of-term writing tasks, following National Curriculum standards.</li>
<li>Prepared termly written progress reports for parents and the head teacher.</li>
<li>Helped organise the school's annual Ofsted inspection evidence folders.</li>
<li>Used Microsoft Excel to track pupil assessment scores across the year.</li>
</ul>
<h3>Teaching Assistant — Riverside Primary School, Salford (Sep 2017 – Jul 2019)</h3>
<ul>
<li>Supported the class teacher with reading groups of 6 pupils.</li>
<li>Checked pupils' homework against answer sheets and reported mistakes to the teacher.</li>
</ul>
<h2>Education</h2>
<p>PGCE Primary Education — University of Manchester (2018 – 2019)</p>
<p>BA (Hons) English Literature — University of Leeds (2014 – 2017)</p>
<h2>Skills</h2>
<p>Lesson planning; marking and feedback; assessment design; report writing; Microsoft Word; Microsoft Excel; Google Classroom</p>
<h2>Languages</h2>
<p>English (native); French (intermediate)</p>
"""

ACCOUNTANT_AR = """
<h1>أحمد خالد المصري</h1>
<p>ahmad.masri@example.com · ‎+962 7 9000 0000 · عمّان، الأردن</p>
<h2>الملخص</h2>
<p>محاسب بخبرة خمس سنوات في إعداد القيود اليومية والتسويات البنكية والتقارير المالية الشهرية.</p>
<h2>الخبرة العملية</h2>
<h3>محاسب — شركة النور للتجارة، عمّان (2021 – حتى الآن)</h3>
<ul>
<li>إعداد القيود اليومية وترحيلها في نظام المحاسبة.</li>
<li>إجراء التسويات البنكية الشهرية لثلاثة حسابات بنكية.</li>
<li>المساعدة في تجهيز ملفات التدقيق الخارجي السنوي.</li>
</ul>
<h3>محاسب مبتدئ — مؤسسة الأمل، الزرقاء (2019 – 2021)</h3>
<ul>
<li>إدخال فواتير الموردين ومطابقتها مع أوامر الشراء.</li>
</ul>
<h2>التعليم</h2>
<p>بكالوريوس محاسبة — الجامعة الأردنية (2015 – 2019)</p>
<h2>المهارات</h2>
<p>Microsoft Excel؛ إعداد التقارير المالية؛ التسويات البنكية</p>
<h2>اللغات</h2>
<p>العربية (اللغة الأم)؛ الإنجليزية (جيد)</p>
"""


def page(body: str, lang: str) -> str:
    rtl = lang == "ar"
    return f"""<!doctype html><html lang="{lang}" dir="{'rtl' if rtl else 'ltr'}"><head><meta charset="utf-8">
<style>
@font-face {{ font-family: Body; src: url('{(FONTS / ('NotoNaskhArabic-Regular.ttf' if rtl else 'NotoSans-Regular.ttf')).as_uri()}'); }}
@font-face {{ font-family: Latin; src: url('{(FONTS / 'NotoSans-Regular.ttf').as_uri()}'); }}
body {{ font-family: Body, Latin; font-size: 11pt; margin: 2cm; }}
h1 {{ font-size: 18pt; }} h2 {{ font-size: 13pt; border-bottom: 1px solid #999; }} h3 {{ font-size: 11pt; }}
</style></head><body>{body}</body></html>"""


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        pg = browser.new_page()
        for name, body, lang in [("cv_teacher_en.pdf", TEACHER_EN, "en"),
                                 ("cv_accountant_ar.pdf", ACCOUNTANT_AR, "ar")]:
            pg.set_content(page(body, lang), wait_until="load")
            pg.pdf(path=str(OUT / name), format="A4")
        browser.close()

    # scan: rasterize every page; the result has no text layer at all
    src = pdfium.PdfDocument(str(OUT / "cv_teacher_en.pdf"))
    images = [src[i].render(scale=2.5).to_pil().convert("RGB") for i in range(len(src))]
    images[0].save(OUT / "cv_teacher_scan.pdf", save_all=True, append_images=images[1:], resolution=180)
    print("written:", sorted(f.name for f in OUT.glob("cv_*.pdf")))


if __name__ == "__main__":
    main()
