"""Arabic CV end to end with real models: PDF -> OCR -> parse -> tailor -> RTL PDF.
Run: uv run pytest -m live tests/live/test_arabic_e2e_live.py -s -p no:warnings"""

import re
from datetime import UTC, datetime
from pathlib import Path

import pytest

from jobcv.agents.parser import parse_cv
from jobcv.cost.meter import CostMeter
from jobcv.cv.ingest import extract_cv_text, ocr_pdf
from jobcv.pdf.render import pdf_filename, render_html, render_pdf
from jobcv.pipeline.tailor_loop import tailor_for_job
from jobcv.schemas import Job
from jobcv.text import detect_language

pytestmark = pytest.mark.live
FX = Path(__file__).parents[1] / "fixtures"
OUT = Path(__file__).parents[2] / "data" / "samples"

# English job description on purpose: output must still be Arabic (the CV's language)
JOB = Job(
    id="manual:ar-1", source="manual", title="Accountant", company="Gulf Trading Co",
    location="Amman, Jordan", remote=False, url="https://example.com/job/1",
    posted_at=None, fetched_at=datetime.now(UTC), language="en",
    description=("We are hiring an Accountant. Responsibilities: daily journal entries, monthly "
                 "bank reconciliations, supporting the external audit, accounts payable "
                 "(supplier invoices matched to purchase orders). Requirements: degree in "
                 "accounting, 3+ years experience, Excel, SAP or Oracle ERP, CPA preferred."),
)


def test_arabic_cv_end_to_end(settings):
    meter = CostMeter(settings)
    ex = extract_cv_text((FX / "cv_accountant_ar.pdf").read_bytes(), settings)
    assert ex.language == "ar"
    cv = parse_cv(ex.text, ex.language, settings, meter)
    out = tailor_for_job(cv, ex.text, JOB, settings, meter)
    t = out.tailored_cv
    r = meter.record()
    print(f"\nstatus={out.review_status} attempts={out.attempts} cost=${r.actual_cost_usd:.4f} "
          f"user_price=${r.price_to_user_usd:.4f}")
    print("SUMMARY:", t.summary)
    for v in out.remaining_violations:
        print("REMAINING:", v.problem, v.adapted_text, "|", v.explanation)

    # language: Arabic in, Arabic out, even with an English job description
    assert t.language == "ar" and detect_language(t.summary) == "ar"
    # nothing invented that the job asked for
    text = t.model_dump_json().lower()
    for term in ["sap", "oracle", "cpa", "erp"]:
        assert term not in text, term
    assert out.review_status == "PASS"
    # no OCR noise survives into the CV (seen before the fix: skill "Excel :1/]110:0501")
    assert "Microsoft Excel" in t.skills, t.skills
    assert not re.search(r"[:\]/]\d{2,}", t.model_dump_json()), t.skills

    OUT.mkdir(parents=True, exist_ok=True)
    pdf = render_pdf(t, OUT / pdf_filename(JOB.title, JOB.company).replace("CV", "CV-AR", 1))
    assert '<html lang="ar" dir="rtl">' in render_html(t)
    # OCR only reads shaped, right-to-left Arabic; it misreads some lines, so check several
    # words and require most of them (a broken layout reads none).
    ocr = ocr_pdf(pdf.read_bytes(), settings)
    words = ["محاسب", "التعليم", "المهارات", "الجامعة", "التسويات", "البنكية", "الملخص"]
    assert sum(w in ocr for w in words) >= 5, ocr
    print("PDF:", pdf)
