# Spec: AI Job Search + CV Tailoring Engine — Phase 1

Status: **APPROVED 2026-11-08** (open questions resolved with the recommended answers: Tesseract OCR; cap $1.00/run; MARKUP 3.0; proposed country list; remote = remote jobs listed in the chosen country)
Source of truth for requirements: the Phase 1 brief. This spec turns the brief into testable criteria and records the decisions taken so far. Anything not listed here is out of scope.

## Objective

A backend engine that a website will later sit on top of. Phase 1 has no website. It is delivered as a Python package, a FastAPI service and a CLI.

User flow:
1. Upload a master CV as a PDF (English or Arabic). The engine parses it into structured JSON.
2. Search LinkedIn jobs through Apify with a title, ONE country, optional cities, an optional remote flag and a maximum result count.
3. Score every job against the CV once, before any editing, and rank the jobs by score.
4. The user picks jobs. For each picked job the engine tailors the CV without inventing anything, runs a fidelity review (at most 3 edit/review rounds) and renders a PDF.

**Out of scope:** website/UI, payments, accounts, LinkedIn posts, Bayt, Facebook, Phase 2, and any match score after editing.

## Capability map (fixed by the brief; module ids are stable)

| Module id | Responsibility | Depends on |
|---|---|---|
| `config` | Settings from `.env` and config: models, prices, TTLs, caps, MARKUP, Actor ID | — |
| `schemas` | Pydantic models: Job, CV, MatchResult, EditResult, ReviewResult, Run, Cost | — |
| `sources` | `JobSource` interface, Location Resolver, LinkedIn/Apify source | config, schemas |
| `jobs` | Dedupe (exact + fuzzy) and the jobs-only cache | schemas |
| `cost` | Estimate, hard cap, actual cost, `price_to_user` | config |
| `cv` | PDF→text, OCR fallback, language detection, temporary CV store with TTL | config, schemas |
| `agents` | CrewAI LLM steps: parser, scorer, editor, reviewer (JSON in, JSON out, no tools) | config, schemas, cost |
| `pipeline` | Plain-code orchestration: search run, tailor run, edit/review loop | everything above |
| `pdf` | HTML template → PDF, EN LTR and AR RTL | schemas |
| `api` / `cli` | FastAPI + background worker; CLI for the same flow | pipeline |

Build order: config → schemas → sources → jobs → cost → cv → scorer → editor/reviewer → pdf → api/cli → test suite completion. Each stage gets its tests, a test run and a report.

## Tech stack

| Concern | Choice | Why |
|---|---|---|
| Python | **3.13** via `uv` | CrewAI 1.15 requires <3.14; the machine default is 3.14 |
| LLM steps | `crewai` 1.15.x; one `Agent` per step, structured output via Pydantic | Required by the brief; agents get no tools |
| LLM provider | OpenAI only, key from `OPENAI_API_KEY` | Brief |
| Models | strong = `gpt-5.4` (parser, editor, reviewer); cheap = `gpt-5.4-mini` (scorer) | Chosen by user from the account's model list |
| Model prices (config, editable) | gpt-5.4 in $2.50 / cached $0.25 / out $15.00 per 1M; gpt-5.4-mini in $0.75 / cached $0.075 / out $4.50 per 1M | OpenAI pricing page, read 2026-11-08 |
| Job source | Apify `bebity/linkedin-jobs-scraper`, called by plain code via `apify-client` | Native multi-city, remote, date filter and description |
| Apify price (config) | $0.0015 per job + $0.00005 per run start (FREE tier) | Actor pricing, read 2026-11-08 |
| API | FastAPI + uvicorn | Brief |
| Background work | In-process worker (thread pool) + SQLite job table; no Redis/Celery | "Lightweight, no heavy infra" |
| Storage | SQLite (`data/app.db`) with **two separate databases**: `jobs_cache.db` (public jobs) and `user.db` (CVs, runs, scores); files in `data/user/` | Keeps cached jobs separate from personal data |
| PDF text | `pypdfium2` (Apache/BSD) | Avoids AGPL PyMuPDF in a commercial product |
| OCR | Tesseract (`eng+ara`) via `pytesseract`, pages rendered with `pypdfium2` | See Open Question 1 |
| HTML → PDF | **Playwright + Chromium** | Correct Arabic shaping and RTL out of the box, works on Windows (WeasyPrint needs GTK on Windows) |
| Fonts | Noto Sans + Noto Naskh Arabic (OFL), bundled in the repo | Proper Arabic glyphs, licence allows embedding |
| Templates | Jinja2 | |
| Tests | pytest, pytest-asyncio, respx/mocks; recorded Apify fixture | |
| Lint | ruff | |

## Key behaviour (testable)

**Location Resolver.** A `Country` enum (fixed list, starting with the countries the Actor recognises well: Gulf states, Levant, Egypt, Western Europe, UK, US, Canada). Free-text cities are validated as non-empty strings. Output is `locations=["<City>, <Country>", ...]`, or `["<Country>"]` when there are no cities, plus `workTypes=["Remote"]` when remote is set. There is no "worldwide" or region option.

**Unified Job schema.** `id, source, title, company, location, remote, description, url, posted_at, fetched_at, language`. Every source maps to this schema; nothing downstream reads raw Actor output.

**Dedupe.** Exact: same `id` or same canonical `url` (query string and trailing slash stripped). Fuzzy: same normalized `title|company|city` key (lowercase, punctuation and Arabic diacritics removed, whitespace collapsed, company suffixes like "LLC/Ltd/GmbH" removed). When jobs merge, keep the newest `fetched_at` and the longest description.

**Cache (jobs only).**
- Key: `normalize(title) + country + sorted(cities) + remote`.
- TTL defaults to 4 hours (configurable). Results return `last_updated`.
- Jobs of any age are shown (changed 2026-11-09 at the user's request: the 30-day limit hid real results). `JOBCV_JOB_MAX_AGE_DAYS` can set a limit.
- `force_refresh=True` bypasses the cache and goes through the cost meter.
- A stale cache entry triggers an **incremental refresh**: fetch with `publishedAt=r86400` (24 hours, the smallest window the Actor offers) and merge with dedupe.
- If the cache has at least N jobs, return the first N. If it has fewer, fetch the shortfall.
- The cache stores no CV data and no scores.

**Cost meter.**
- `estimate(run)` = Apify (jobs × per-job price + start fee) + LLM (estimated tokens × model price per agent call).
- The estimate is returned before the run starts.
- The hard cap per run (config) is checked before every billable call. A run that would exceed the cap stops with status `stopped_cost_cap`.
- Actual cost comes from OpenAI's reported token usage per agent and Apify's reported charges for the run.
- Stored separately: `actual_cost_usd` and `price_to_user_usd = actual × MARKUP`.

**CV ingestion.**
- Text is extracted from the PDF.
- If it yields fewer than ~200 characters across the document (configurable), the engine falls back to OCR.
- Language = `ar` if Arabic letters make up more than 30% of the letters, otherwise `en`.
- The parser returns the CV JSON: `contact, summary, experience[], education[], skills[], certifications[], languages[], other`.
- The raw text is stored next to the JSON.

**Agents.**
- All agents return validated Pydantic objects. Invalid JSON triggers one retry, then a run error.
- Scorer: `{score 0-100, reasons[], matched_skills[], gaps[]}`.
- Editor: `{tailored_cv, change_log[{original, adapted, why_faithful}]}`, written in the CV's language.
- Reviewer: `{status PASS|FAIL, violations[{adapted_text, problem A-E, explanation, suggested_fix}]}`.
- The editor and reviewer prompts carry the hard rules from the brief verbatim.

**Loop.** Edit → review. On FAIL, the editor gets `reviewer_feedback` and is told to fix only those items. At most 3 review attempts. After that the latest version is delivered with `warning=true` and the remaining violations.

**PDF.**
- One single-column template.
- `dir="rtl"`, `lang="ar"` and the Arabic font for Arabic CVs; `ltr` otherwise.
- The file is named `CV - <job title> - <company>.pdf` (sanitized).

**Privacy.**
- CV content never goes to logs. Logs carry ids, counts and timings only, and a test checks this.
- CVs, runs and outputs are deleted automatically after 24 hours (configurable) by a background sweeper. `DELETE /cv/{id}` deletes immediately, together with the CV's runs and PDFs.
- CV data goes only to OpenAI.

**API.**
- `POST /cv`
- `POST /search`: returns `{run_id, estimate}`
- `GET /runs/{id}`
- `POST /tailor`
- `GET /tailor/{id}`
- `GET /files/{name}`: PDF download
- `DELETE /cv/{id}`

The CLI runs the same flow: `jobcv cv add <pdf>`, `jobcv search ...`, `jobcv tailor ...`, `jobcv run-all ...`.

## Commands

```
uv sync                                   # install (Python 3.13)
uv run playwright install chromium        # one-time, for PDF rendering
uv run pytest                             # offline tests (mocks + fixtures)
uv run pytest -m live                     # small real-API tests (costs a few cents)
uv run ruff check . --fix
uv run fastapi dev src/jobcv/api/app.py   # dev server
uv run jobcv --help                       # CLI
```

## Project structure

```
src/jobcv/{config.py, schemas/, sources/, jobs/, cost/, cv/, agents/(prompts/), pipeline/, pdf/(templates/, fonts/), api/, cli.py}
tests/{unit/, fidelity/, live/, fixtures/(apify_bebity_5jobs.json, cv_teacher_en.pdf, cv_ar.pdf, cv_scan.pdf)}
data/   (runtime, git-ignored)    tasks/{plan.md, todo.md}    SPEC.md  README.md  .env  .env.example
```

## Code style

Typed Python, Pydantic v2 models at module boundaries, small pure functions, no global state except settings. ruff defaults with line length 100.

```python
def cache_key(q: SearchQuery) -> str:
    cities = ",".join(sorted(normalize(c) for c in q.cities))
    return f"{normalize(q.title)}|{q.country.value}|{cities}|{int(q.remote)}"
```

## Testing strategy

- **Unit (offline, run every stage):** resolver, dedupe, cache hit/miss/expiry/30-day drop/top-N/shortfall, cost estimate and cap stop, language detection, OCR fallback trigger, PDF EN and AR (RTL attribute and Arabic glyphs in the extracted PDF text), API routes with the pipeline mocked, a log-privacy check.
- **Fidelity (real LLM, small, `-m live`):**
  1. Teacher → QA job: the output contains none of Selenium, Jira, ISTQB, "test automation" or SQL, and the reviewer PASSes.
  2. A corrupted adapted CV (fake tool + fake number + "helped"→"led") is FAILed, with each injected violation listed.
  3. An honest rewording PASSes.
  4. An Arabic CV runs end to end to an RTL PDF.

  The forbidden-term checks are deterministic string checks, not LLM judgments.
- **Apify:** a single real call with a 5-job limit, recorded once to `tests/fixtures/` and replayed afterwards. No test loops Apify.

## Boundaries

- **Always:** run tests after each stage and report real output; keep secrets in `.env`; keep CV text out of logs; keep small limits for live calls.
- **Ask first:** new dependencies beyond this spec; any Apify call beyond the single 5-job fixture recording; installing system software (Tesseract); changing models or the Actor.
- **Never:** build UI or Phase 2; let agents call Apify or decide the workflow; store CVs or scores in the job cache; send CV data anywhere but OpenAI; claim something works without running it.

## Success criteria

1. `uv run pytest` passes offline with no network.
2. The live fidelity suite passes all 4 cases above.
3. One real end-to-end CLI run (5 jobs, 1 tailored CV in English and 1 in Arabic) completes under the cost cap and reports the estimate, the actual cost and `price_to_user`.
4. The Arabic PDF opens with correct RTL layout and connected Arabic letters, checked by the user visually.
5. The README covers running the engine, config options and adding a new `JobSource`.

## Open questions

1. **OCR engine.** Tesseract is not installed. Option A: install Tesseract with Arabic data (`winget install UB-Mannheim.TesseractOCR`); free and local. Option B: OCR scanned pages with OpenAI vision; no install, small cost per scan, and the data still only goes to OpenAI. **Recommended: A.**
2. **Cost cap default.** Proposed $1.00 per run, `MARKUP` = 3.0. Please confirm or give your numbers.
3. **Country list.** The proposed starting list is above. Do you want specific countries added or removed?
4. **Remote flag and country together.** "Remote only" is proposed to mean remote jobs listed for the chosen country, not worldwide remote. Is that correct?
