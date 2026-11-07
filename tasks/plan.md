# Implementation Plan: Job CV Engine — Phase 1

## Overview
Build the Phase 1 backend described in [../SPEC.md](../SPEC.md): a Python package, a FastAPI API and a CLI. The engine searches LinkedIn through Apify, scores jobs against a parsed CV, tailors the CV with an edit→review loop and renders EN/AR PDFs. The task list is in [todo.md](todo.md).

## Architecture decisions
- **Build order is fixed by the brief.** Foundation modules first, then the LLM steps, then PDF, then API/CLI. Each module is independent and tested before the next starts.
- **Plain code orchestrates. CrewAI only runs the 4 LLM steps.** Each step is a function `run_<step>(input_model) -> (output_model, Usage)`. The agents get no tools.
- **`JobSource` protocol.** `search(query, limit, since=None) -> SourceResult(jobs, cost)`. The bebity mapper is the only code that knows the Actor's fields.
- **Two SQLite files.** `jobs_cache.db` holds public data. `user.db` holds CVs, runs and scores. They are never joined.
- **Cost meter is passed into every billable call.** It is checked before each call and records the usage after it.
- **Worker:** a `ThreadPoolExecutor` inside the API process. Run state lives in `user.db`, so `GET` endpoints read only from the DB.
- **Live tests** are marked `@pytest.mark.live` and skipped by default. The one Apify recording is done by an explicit script, `scripts/record_apify_fixture.py`, never by tests.

## Phase overview

| Phase | Tasks | Checkpoint |
|---|---|---|
| 1 Foundation | T1 scaffold+config, T2 schemas | offline tests green |
| 2 Jobs | T3 resolver+source (mocked), T4 record 5-job fixture, T5 dedupe, T6 cache | **report to user** |
| 3 Cost | T7 cost meter | offline tests green |
| 4 CV | T8 PDF text + language, T9 OCR fallback, T10 CrewAI base + parser | **report to user** |
| 5 Matching | T11 scorer + ranking | live: teacher vs QA scores low |
| 6 Tailoring | T12 editor, T13 reviewer, T14 loop | **live fidelity suite, report to user** |
| 7 PDF | T15 template EN, T16 AR RTL | **user checks Arabic PDF visually** |
| 8 Delivery | T17 pipeline + store/TTL, T18 API, T19 CLI, T20 README + e2e | **final report** |

## Risks and mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Real bebity output differs from its README (field names, date formats, remote flag) | High | T4 records real output early. The mapper is written against the recording. |
| CrewAI's structured output or usage reporting doesn't behave as documented in 1.15 | High | T10 starts with a tiny live probe (1 call) before writing the 4 agents. If usage isn't exposed per call, the usage is read from the OpenAI response. |
| The editor still hints at missing skills | High | Banned-term string checks plus the reviewer; the fidelity suite is a gate. |
| Arabic text extracted from PDFs comes out in reversed or visual order | Med | Test with a real Arabic PDF in T8. If extraction is broken, fall back to OCR for Arabic. |
| Tesseract install / Arabic language data missing | Med | T9 checks for the binary and `ara` data and fails with a clear message. |
| The incremental refresh window (24h) is larger than the TTL (4h), so refreshes overlap | Low | Dedupe merges the overlap. The extra cost is a few cents and is visible in the cost meter. |
| Python 3.14 is the default interpreter | Low | `.python-version` = 3.13 and `uv` pins it. |

## Parallelization
Not used. The stages build on each other, and you want a report at each stage.
