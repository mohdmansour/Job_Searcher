# Website tasks

Spec: [SPEC-web.md](../SPEC-web.md). Plan: [web-plan.md](web-plan.md).

Every task also needs: `npm run build` passing, and `uv run pytest` if the backend changed.

## Phase A: Foundation

- [x] **W1: Bring the prototype into `web/` and clean it** (M)
  - Accept: copied without its git history; `@vercel/analytics`, `cn`, `jspdf` and `ignoreBuildErrors` removed; `web/node_modules` and build output git-ignored
  - Verify: `npm run build` passes with type checking; pages open and look like the prototype
  - Depends on: none
- [x] **W2: Set up test tools and a baseline mobile check** (M)
  - Accept: Vitest and Playwright run; browser tests cover 320, 360, 390, 768 and 1280 px in EN and AR
  - Verify: `npm test`, `npm run e2e`; the sideways-scroll test runs on every page and its failures are listed
  - Depends on: W1
- [x] **W3: Backend additions** (S)
  - Accept: `POST /estimate/search`, `POST /estimate/tailor`, `GET /cv/{id}`; estimates make no paid calls and include `price_to_user_usd`; existing endpoints unchanged
  - Verify: new offline tests written first; `uv run pytest`; `ruff check`
  - Depends on: none
  - Files: `src/jobcv/api/app.py`, `src/jobcv/cost/meter.py`, `tests/unit/`
- [x] **W4: API client and proxy** (M)
  - Accept: typed client for every endpoint; `/api/*` forwards to `BACKEND_URL`; backend errors map to named error types; polling helper stops at end states
  - Verify: unit tests; a slow (45 s) 10 MB upload through the proxy against a local stub succeeds
  - Depends on: W1, W2, W3
  - Files: `web/lib/api.ts`, `web/next.config.mjs`, `web/tests/`

### Checkpoint A
- [x] Build and tests pass; proxy proven with a slow large upload

## Phase B: The real flow, one step at a time

- [x] **W5: CV upload** (M)
  - Accept: upload shows real uploading and reading phases; 10 MB limit; replace and remove call the backend; a reload keeps the CV, or says it expired; every error has its message
  - Verify: browser tests (success, wrong type, too large, 503, expired) at phone and desktop sizes
  - Depends on: W4
  - Files: `web/components/search/cv-upload.tsx`, `web/lib/app-state.tsx`, `web/lib/i18n.ts`, `web/e2e/`
- [x] **W6: Search form fields** (M)
  - Accept: 27 countries in EN and AR; typed city chips (max 10) with suggestions; "Remote jobs only"; counts 10, 25, 50
  - Verify: contract test against the backend's `Country` list; browser test of the values sent
  - Depends on: W4
  - Files: `web/lib/countries.ts`, `web/components/search/search-form.tsx`, `web/lib/i18n.ts`, `tests/unit/`
- [x] **W7: Run a search** (M)
  - Accept: real estimated price appears before starting and updates with the form; start, wait, resume after reload; no-results, failed, over-cap and expired states
  - Verify: browser tests per state, including reload during a run
  - Depends on: W5, W6
  - Files: `web/components/search/search-form.tsx`, `web/lib/app-state.tsx`, `web/lib/i18n.ts`, `web/e2e/`
- [x] **W8: Results list and job detail** (M)
  - Accept: real jobs ranked; reasons, skills and gaps shown; description as one text block; real LinkedIn link; unknown date hidden; unscored jobs last with a message; only http(s) links are followed
  - Verify: browser tests with recorded-shape data, phone list-to-detail and back
  - Depends on: W7
  - Files: `web/components/results/{job-list,job-detail,match-breakdown,results-view}.tsx`, `web/e2e/`
- [x] **W9: Refresh and selection** (M)
  - Accept: "last updated" and a confirmed refresh; confirmation dialog shows the real estimate and the extra-information box; over-cap selection is refused with a clear message
  - Verify: browser tests; the extra information is sent and never stored in the browser
  - Depends on: W8
  - Files: `web/components/results/{confirm-dialog,results-view}.tsx`, `web/lib/app-state.tsx`, `web/lib/i18n.ts`
- [x] **W10: Tailoring progress and PDF download** (M)
  - Accept: per-job waiting, working, ready; real PDF download through the proxy; no score after tailoring; resumes after reload
  - Verify: browser test with partial results arriving one job at a time; downloaded file is the served PDF
  - Depends on: W9
  - Files: `web/components/generate/generate-view.tsx`, `web/lib/app-state.tsx`, `web/lib/i18n.ts`, `web/e2e/`
- [x] **W11: Change log, warnings and end states** (M)
  - Accept: real change log; warning state lists remaining problems and still offers the PDF; `failed`, `stopped_cost_cap` and expired handled, keeping finished PDFs; retry starts a new run
  - Verify: browser test per state
  - Depends on: W10
  - Files: `web/components/generate/generate-view.tsx`, `web/lib/i18n.ts`, `web/e2e/`

### Checkpoint B
- [x] Whole flow passes against the mocked API at phone and desktop sizes; you review it

## Phase C: Truthful and finished

- [x] **W12: Demo areas and removing fake data** (M)
  - Accept: sign-in, credits and pricing labelled "Demo" and never block real runs; fake jobs, person, sample CV, demo results and `lib/pdf.ts` deleted; Account page shows the real CV and real delete, which clears backend and browser
  - Verify: browser tests; a search of `web/` finds no prototype names (`Layla`, `Nimbus`, and so on)
  - Depends on: W11
  - Files: `web/lib/{data,pdf,app-state}.*`, `web/components/{pages,chrome}.tsx`, `web/e2e/`
- [x] **W13: Truthful copy in both languages** (M)
  - Accept: the four untrue claims in the spec are corrected; privacy page covers OpenAI and 24-hour deletion; legal pages still marked draft; every key exists in EN and AR
  - Verify: unit test comparing EN and AR keys; you read the changed text
  - Depends on: W12
  - Files: `web/lib/i18n.ts`, `web/components/landing/landing.tsx`, `web/tests/`
- [x] **W14: Mobile pass** (M)
  - Accept: all spec mobile requirements: no sideways scroll, 44 px controls, safe area, dialogs fit, polling resumes, mobile PDF fallback
  - Verify: browser tests at all sizes pass; phone-size screenshots reviewed
  - Depends on: W13
  - Files: `web/components/ui/button.tsx`, `web/components/chrome.tsx`, `web/components/results/`, `web/e2e/`
- [x] **W15: Arabic pass** (S)
  - Accept: every page reads right-to-left; mixed Arabic and English in jobs, skills and file names display correctly
  - Verify: screenshots of every page in Arabic at phone and desktop sizes reviewed
  - Depends on: W14

### Checkpoint C
- [x] No fake data remains, copy is truthful, mobile and Arabic pass; you review it

## Phase D: Proof

- [x] **W16: Real run and documentation** (S)
  - Accept: with your go-ahead, one real run through the website (max 5 jobs, about $0.05–0.20); README covers running the site and testing on a phone
  - Verify: the real PDF opens correctly; you try the site on your own phone
  - Depends on: W15

### Checkpoint D
- [x] All spec success criteria met
