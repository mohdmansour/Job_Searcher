# Job CV Engine — Phase 1

Backend core for an AI job search + CV tailoring product. A Python package, a FastAPI API and
a CLI. No website, accounts or payments yet. Requirements are in [SPEC.md](SPEC.md) and the
build plan is in [tasks/](tasks/).

**Flow:**
1. Upload a CV (PDF, English or Arabic). The engine extracts the text, using OCR if needed, and parses it into JSON.
2. Search LinkedIn jobs through Apify for one country, optional cities, and an optional remote filter.
3. Every job is scored against the CV once, before any editing, and the jobs are ranked.
4. You pick jobs. For each one the engine tailors the CV without inventing anything, runs a fact-check review (at most 3 rounds), and renders a PDF.

## Setup (Windows; Linux works the same with apt packages)

```bash
uv sync                                   # Python 3.13 is pinned (CrewAI needs < 3.14)
uv run playwright install chromium        # PDF rendering
winget install --id UB-Mannheim.TesseractOCR -e   # OCR (Linux: apt install tesseract-ocr)
mkdir tessdata && for l in eng ara osd; do curl -sfL -o tessdata/$l.traineddata \
  https://github.com/tesseract-ocr/tessdata_best/raw/main/$l.traineddata; done
cp .env.example .env                      # then fill APIFY_TOKEN and OPENAI_API_KEY
```

## Run

```bash
uv run fastapi dev                        # API at http://127.0.0.1:8000, docs at /docs
uv run jobcv --help                       # CLI
uv run jobcv run-all CV.pdf --title "QA Engineer" --country "United Arab Emirates" --max 5 --pick 1
```

### API

| Method | Path | What it does |
|---|---|---|
| POST | `/cv` (multipart `file`) | Upload a PDF. Returns `cv_id`, `language`, and `extraction` (`text`/`ocr`) |
| POST | `/search` | `{cv_id, title, country, cities[], remote, max_results, force_refresh}` → `{run_id, status, estimate}` |
| GET | `/runs/{id}` | Status, jobs ranked by score (score, reasons, matched_skills, gaps), `last_updated`, cost |
| POST | `/tailor` | `{run_id, job_ids[], user_extra_info}` → `{run_id, status, estimate}` |
| GET | `/tailor/{id}` | Status and, per job: `pdf_url`, review status, warning, remaining violations, change log |
| GET | `/files/{tailor_id}/{name}` | PDF download |
| DELETE | `/cv/{id}` | Deletes the CV with all its runs and PDFs right away |

Runs execute in background threads, so poll the `GET` endpoints. Run status values are `queued`, `running`, `done`, `failed` and `stopped_cost_cap`.

## Configuration

Settings come from `.env` or environment variables with the `JOBCV_` prefix. Secrets use their usual names. Everything is defined in [src/jobcv/config.py](src/jobcv/config.py).

| Setting | Default | Meaning |
|---|---|---|
| `OPENAI_API_KEY`, `APIFY_TOKEN` | — | Secrets. Only in `.env`, never in code |
| `JOBCV_STRONG_MODEL` | `gpt-5.4` | CV Parser, CV Editor, CV Reviewer |
| `JOBCV_CHEAP_MODEL` | `gpt-5.4-mini` | Match Scorer |
| `JOBCV_MODEL_PRICES` | gpt-5.4 / gpt-5.4-mini prices | JSON: `{"model": {"input_per_1m":…, "cached_input_per_1m":…, "output_per_1m":…}}` |
| `JOBCV_TOKEN_ESTIMATES` | measured ×2 | Tokens per call, used only for pre-run estimates |
| `JOBCV_MAX_REVIEW_ATTEMPTS` | `3` | Maximum edit→review rounds per job |
| `JOBCV_APIFY_ACTOR_ID` | `bebity/linkedin-jobs-scraper` | LinkedIn jobs Actor |
| `JOBCV_APIFY_PRICE_PER_JOB_USD` | `0.0015` | Actor price per job (FREE tier) |
| `JOBCV_APIFY_PRICE_PER_START_USD` | `0.00005` | Charged once per GB of run memory |
| `JOBCV_JOB_CACHE_TTL_HOURS` | `4` | After this, a search does an incremental refresh |
| `JOBCV_JOB_MAX_AGE_DAYS` | `30` | Older postings are ignored |
| `JOBCV_MAX_COST_PER_RUN_USD` | `1.0` | Hard cap per run, checked before every billable call |
| `JOBCV_MARKUP` | `3.0` | `price_to_user = actual_cost × MARKUP` (both are stored) |
| `JOBCV_CV_TTL_HOURS` | `24` | CVs, runs and PDFs are deleted automatically after this |
| `JOBCV_OCR_MIN_CHARS` | `200` | Less extracted text than this means the PDF is treated as a scan and OCR'd |
| `JOBCV_TESSERACT_CMD`, `JOBCV_TESSDATA_DIR` | Windows path, `tessdata` | OCR binary and language data |
| `JOBCV_DATA_DIR` | `data` | `jobs_cache.db` (public jobs), `user.db` + `user/` (personal data) |

## Tests

```bash
uv run pytest                              # offline: mocks + recorded Apify fixture (~40 s)
uv run pytest -m live -p no:warnings -s    # real OpenAI calls, a few cents
```

- **Fidelity suite** ([tests/live/test_fidelity_live.py](tests/live/test_fidelity_live.py)):
  - teacher → QA job: no invented QA tools or experience (22 banned terms, checked as plain strings);
  - corrupted CV: the reviewer fails it and lists each violation;
  - honest rewording: the reviewer passes it.
- **Arabic end to end** ([tests/live/test_arabic_e2e_live.py](tests/live/test_arabic_e2e_live.py)): runs through to an RTL PDF.
- **Never re-recorded automatically:** the Apify fixture ([scripts/record_apify_fixture.py](scripts/record_apify_fixture.py)) and the fictional CV PDFs ([scripts/make_cv_fixtures.py](scripts/make_cv_fixtures.py)).

## Add a new job source (Phase 2)

1. Create `src/jobcv/sources/<name>.py` with a class that has `name`, `estimate_cost(q, limit)` and `search(q, limit, recent_only=False) -> SourceResult`. See the `JobSource` protocol in [sources/base.py](src/jobcv/sources/base.py).
2. Map the provider's raw items to the unified `Job` schema inside that module, and only there. Use ids like `"<name>:<native id>"`. Drop personal data such as recruiter names.
3. Record one small real response into `tests/fixtures/` and test your mapper against it.
4. Pass the source to `JobSearchService` / `Engine`. Dedupe (exact id/URL plus fuzzy title+company+city), the cache, scoring and tailoring work unchanged. Fuzzy dedupe already merges the same posting found on different sources.

## Privacy (GDPR)

- **No CV text in logs.** Logs carry ids, counts and timings only; a test runs the whole flow at DEBUG level and checks this.
- **No CrewAI telemetry or tracing.** Both are switched off in code, and CrewAI's console output is silenced.
- **CV data goes only to OpenAI.** Contact details are not sent to the scorer, editor or reviewer.
- **Personal data is temporary.** CVs, runs, scores and PDFs live in `user.db` and `data/user/` and are deleted after `JOBCV_CV_TTL_HOURS` (by a sweeper thread in the API, or `jobcv sweep`). `DELETE /cv/{id}` deletes them immediately.
- **`user_extra_info` is never stored.** It's only used in memory during the tailoring run.
- **The job cache holds public job data only** (`jobs_cache.db`): no CVs, no scores.

## Known limits

- **Arabic PDFs look right, but their hidden text layer extracts reversed** in common readers (PDFium, pdfminer; Typst behaved the same). ATS systems may read Arabic CVs poorly. A DOCX or plain-text export would fix this; it isn't in Phase 1.
- **Arabic CV ingestion:** PDFs whose Arabic text layer is reversed are OCR'd, and the Latin parts are then repaired from the PDF's own text layer. Latin noise from OCR is replaced by the real phrase (`Excel :1/]110:0501` → `Microsoft Excel`) or dropped, and bullets that OCR reads as `٠` become `-`. What remains: an Arabic word that OCR misreads as Latin is dropped, not recovered (seen: the city in a header), and small Arabic OCR typos can remain. Scanned Arabic PDFs, which have no text layer, get plain OCR.
- **The Actor can't skip results it already returned.** When the cache holds fewer than N jobs, the engine fetches N again and dedupes the overlap, but only if no earlier fetch in the same TTL window already asked for N or more. If one did, the market simply has fewer jobs. Incremental refresh uses the Actor's smallest date window (24h), so refreshes overlap.
- **Timeouts:** each LLM call times out after 120 s, with 2 retries. A job whose scoring fails is kept, last, with its error type. Runs interrupted by a crash are marked `failed` on the next start.
- **No accounts.** The 128-bit run ids act as access tokens, so add auth before going public.
