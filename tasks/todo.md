# Tasks — Phase 1

Offline test command: `uv run pytest`. Live test command: `uv run pytest -m live` (small and paid).
Done = acceptance met, the tests were run, and their output was reported. Nothing is marked done without a run.

## Phase 1: Foundation
- [x] **T1 Scaffold + config** (S)
  - Acceptance: `uv` project on Python 3.13; `jobcv.config.Settings` loads `.env` and defaults (models, prices, TTL 4h, CV TTL 24h, cap $1, MARKUP 3, Actor ID, OCR threshold); `.env` is git-ignored.
  - Verify: `uv run pytest tests/unit/test_config.py`; `uv run python -c "import jobcv"`
  - Files: `pyproject.toml`, `.python-version`, `src/jobcv/config.py`, `tests/unit/test_config.py`
- [x] **T2 Schemas** (S)
  - Acceptance: Pydantic models for Job, SearchQuery/Country, CV, MatchResult, EditResult, ReviewResult/Violation, Usage, CostRecord, run status enums.
  - Verify: `uv run pytest tests/unit/test_schemas.py`
  - Files: `src/jobcv/schemas/*.py`, tests
- **Checkpoint:** offline tests green.

## Phase 2: Jobs
- [x] **T3 Location Resolver + LinkedIn source** (M) — deps T1, T2
  - Acceptance: Country enum + resolver → bebity input; `JobSource` protocol; Apify client wrapper and mapper to `Job`. Tested with a mocked client.
  - Verify: `uv run pytest tests/unit/test_location.py tests/unit/test_linkedin_source.py`
- [x] **T4 Record the real 5-job fixture** (XS) — deps T3. **The only live Apify call in development** (~$0.008).
  - Acceptance: `scripts/record_apify_fixture.py` saves raw output to `tests/fixtures/apify_bebity_5jobs.json`; the mapper is checked and fixed against the real output.
  - Verify: the script runs once; the mapper test runs against the fixture.
- [x] **T5 Dedupe** (S) — deps T2
  - Acceptance: exact (id/canonical URL) and fuzzy (title+company+city, EN/AR normalization); merges keep the newest data and the longest description.
  - Verify: `uv run pytest tests/unit/test_dedupe.py`
- [x] **T6 Jobs cache** (M) — deps T5
  - Acceptance: key normalization; TTL; `last_updated`; 30-day drop; top-N vs shortfall fetch; `force_refresh`; incremental refresh with `r86400` + merge; separate DB file.
  - Verify: `uv run pytest tests/unit/test_cache.py` (hit, miss, expiry, shortfall, incremental, force)
- **Checkpoint: report to user.**

## Phase 3: Cost
- [x] **T7 Cost meter** (M) — deps T1, T2
  - Acceptance: pre-run estimate; cap check before each billable call, raising `CostCapExceeded`; actual cost from usage + Apify charges; `price_to_user = actual × MARKUP` stored separately.
  - Verify: `uv run pytest tests/unit/test_cost.py` (including a run that stops at the cap)

## Phase 4: CV ingestion
- [x] **T8 PDF text + language detection** (S)
  - Acceptance: pypdfium2 extraction; `ar`/`en` detection; works on the EN and AR fixture PDFs.
  - Verify: `uv run pytest tests/unit/test_cv_ingest.py`
- [x] **T9 OCR fallback** (S) — needs Tesseract installed (approved)
  - Acceptance: a scan-only PDF triggers OCR (`eng+ara`); a clear error if Tesseract is missing.
  - Verify: `uv run pytest tests/unit/test_ocr.py`
- [x] **T10 CrewAI base + CV Parser** (M)
  - Acceptance: a shared `run_agent()` with structured output, one JSON retry and usage capture per call; the parser prompt forbids additions. One live probe confirms usage reporting.
  - Verify: offline test with a mocked LLM; `uv run pytest -m live tests/live/test_parser.py`
- **Checkpoint: report to user.**

## Phase 5: Matching
- [x] **T11 Match Scorer + ranking** (S) — cheap model
  - Acceptance: score, reasons, matched_skills and gaps; jobs ranked by score; a teacher CV against a QA job scores low with clear gaps.
  - Verify: offline ranking test; live test with 1 small call.

## Phase 6: Tailoring
- [x] **T12 CV Editor** (M) — the brief's hard rules verbatim; output in the CV's language; change log.
- [x] **T13 CV Reviewer** (S) — checks A–E; strict; JSON only.
- [x] **T14 Edit/review loop** (S) — max 3 attempts; feedback limited to the listed violations; warning flag + remaining violations at the end.
  - Verify (T12–T14): offline loop tests with mocked agents; **live fidelity suite**: teacher→QA (banned terms absent), corrupted CV FAILs with each violation listed, honest rewording PASSes.
- **Checkpoint: report to user.**

## Phase 7: PDF
- [x] **T15 HTML template + Playwright render (EN)** (S)
- [x] **T16 Arabic RTL** (S) — Noto Naskh Arabic bundled; `dir=rtl`.
  - Verify: `uv run pytest tests/unit/test_pdf.py` (the PDF exists, the extracted text contains Arabic words, the HTML has `dir="rtl"`); the user opens the sample AR PDF.

## Phase 8: Delivery
- [x] **T17 Pipeline + user store with TTL sweeper + delete** (M)
- [x] **T18 FastAPI endpoints + background worker** (M)
- [x] **T19 CLI** (S)
- [x] **T20 README + end-to-end live run (5 jobs, 1 EN and 1 AR tailoring) + log-privacy test** (S)
- **Final checkpoint:** all success criteria in SPEC.md met and reported with real outputs.
