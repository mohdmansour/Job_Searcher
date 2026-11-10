# Spec: Website (Candor front end)

**Status:** APPROVED 2026-11-08. **Backend spec:** [SPEC.md](SPEC.md).

## Objective

Turn the V0 prototype (`mohdmansour/ai-job-search-prototype`, brand name "Candor") into the
website for this project. The user uploads a CV, searches jobs, sees them ranked by match, picks
jobs and downloads tailored PDFs, on a phone or a computer, in English or Arabic.

The visual design stays. What changes is the data behind it: every screen in the main flow uses
the real backend, and the fake jobs, fake CV and timers are removed.

**Not in this stage:** real accounts, real payments, hosting or going public.

## Assumptions

1. The site lives in a new `web/` folder in this repository. The backend stays where it is.
2. It runs on this computer for now, and can be opened on a phone over the same Wi-Fi for testing.
3. npm is used, because pnpm isn't installed and installing system software needs your approval.
4. Where the design and the backend disagree, the design changes, except for the backend
   additions listed below.

## What is real and what stays demo

| Area | State | Details |
|---|---|---|
| CV upload, replace, remove | **Real** | `POST /cv`, `DELETE /cv/{id}` |
| Job search | **Real** | `POST /search`, polling `GET /runs/{id}` |
| Results, match details | **Real** | Ranked by the backend's score |
| Tailoring, progress, PDF download | **Real** | `POST /tailor`, polling `GET /tailor/{id}`, `GET /files/...` |
| Delete my data | **Real** | `DELETE /cv/{id}` |
| Language switch, right-to-left layout | **Real** | Kept from the design |
| Landing page | **Real copy** | Claims corrected to match what the product does |
| Privacy, terms | **Draft copy** | Facts corrected, still marked as a draft, not legal advice |
| Sign in, sign up, profile | **Demo** | Kept, marked "Demo". Nothing is sent or stored |
| Credits, history, pricing, buy buttons | **Demo** | Kept, marked "Demo". No money moves |

Demo credits **never block a real search or tailoring run**.

## Changes needed to fit the backend

**Search form**
- All 27 backend countries, with Arabic names (the design has 6). Values sent match the backend's list exactly.
- Cities: type any city and add it as a chip, up to 10, with the design's chips kept as suggestions. Suggestions send the English name.
- Job titles: up to 2 more titles can be added to one search, and the requested results are shared across them (added 2026-11-09).
- Remote: the label becomes "Remote jobs only", because that is what the backend does (the design says "Include remote jobs").
- PDF limit: 10 MB (the design says 5 MB).
- Result count stays 10, 25 or 50.
- Cost panel: a real estimated price from the backend, shown next to the demo credits.

**Results**
- Match details show the backend's `reasons`, `matched_skills` and `gaps`. The design's quoted CV evidence and required/preferred labels are removed, because the backend doesn't produce them.
- The job description is shown as one text block in its own direction. The structured sections and the applicant count are removed (no such data).
- Job type shows only "Remote" when true. The backend can't tell on-site from hybrid.
- Posted date is hidden when unknown.
- Added: "last updated" time with a refresh button (`force_refresh`, a paid action with a confirmation).
- Added: jobs that couldn't be scored appear last with a clear message.
- The "View on LinkedIn" button uses the job's real link.

**Selection and tailoring**
- Confirmation dialog: adds the optional "extra information" box (`user_extra_info`).
- If the estimate is over the cost cap (about 6 jobs at the $1 cap), the dialog asks the user to pick fewer jobs.
- Progress per job: waiting, working, ready. The design's separate "tailoring" and "checking" steps merge, because the backend reports only when a job finishes.
- Ready job: PDF download and the real change log (original, adapted, why it is faithful).
- Warning state: if a job finished review with problems left, the PDF is still offered and the remaining problems are listed so the user can check them.
- No score appears after tailoring, as the original brief requires.
- All end states are handled: `failed`, `stopped_cost_cap`, expired (404), network loss. "Retry" starts a new run for that job.

**Removed from the prototype**
- Fake data (`lib/data.ts` jobs and candidate), `lib/pdf.ts`, timers, "Use the sample CV", "Load demo results".
- `@vercel/analytics`, so the site sends no data to third parties.
- `ignoreBuildErrors`, so type errors stop the build.
- Unused packages (`cn`, `jspdf`).

**Copy that must change because it is untrue**
- "Stays in your account until you delete": files are deleted automatically after 24 hours.
- "If it can't be traced, it doesn't ship": a PDF can ship with a warning after 3 review rounds.
- "Fictional demo product. All companies, people, and jobs are made up": the jobs are now real.
- The privacy page must say that CV data is processed by OpenAI.

## Backend additions

Small and additive. Existing endpoints don't change.

| Endpoint | Why |
|---|---|
| `POST /estimate/search` | The design promises the cost **before** anything runs. Today `POST /search` starts right away |
| `POST /estimate/tailor` (`n_jobs`) | Same, for the confirmation dialog |
| `GET /cv/{id}` (language and extraction method only) | After a reload, shows whether the CV is still available or has expired |

Both estimates return the existing `Estimate` plus `price_to_user_usd`. They make no paid calls.

## Mobile requirements

- No sideways page scrolling at 320, 360, 390, 768 and 1280 px, in English and Arabic.
- Main buttons and form controls are at least 44 px tall on touch screens.
- CV file picker works on iPhone and Android (`accept` PDF).
- Bottom selection bar respects the phone's safe area and never covers content.
- Dialogs fit the screen and scroll inside.
- List and detail are separate views on phones, as in the design.
- Long waits survive the phone locking or switching apps: ids are kept in the browser and polling resumes on return.
- PDF download works on mobile, opening in a new tab where the browser can't save directly.

## Tech stack

Kept from the prototype: Next.js 16, React 19, TypeScript, Tailwind CSS 4, Base UI, lucide-react, IBM Plex fonts (bundled at build time).

**New, development only (needs your approval with this spec):** `vitest`, `@testing-library/react`, `@playwright/test`.

**Connection:** the browser calls `/api/*` on the website, and Next.js forwards to FastAPI (`BACKEND_URL`, default `http://127.0.0.1:8000`). The backend needs no public exposure, and no CORS setup. The proxy timeout is raised because `POST /cv` can take 10–40 seconds or more.

**Browser storage:** `cv_id`, run ids, the selected job ids, the file name and the language. No CV text, and no personal data in URLs.

## Commands

```bash
uv run fastapi dev                      # backend, http://127.0.0.1:8000
cd web && npm install
cd web && npm run dev                   # website, http://localhost:3000
cd web && npm run dev -- -H 0.0.0.0     # also reachable from a phone on the same Wi-Fi
cd web && npm run build
cd web && npm run lint
cd web && npm test                      # unit tests
cd web && npm run e2e                   # browser tests, mocked API, no paid calls
uv run pytest                           # backend tests
```

## Project structure

```
web/app/             Pages (kept from the design: site pages and app pages)
web/components/      Screens and UI parts
web/lib/api.ts       The only file that calls the backend, with typed responses
web/lib/countries.ts The 27 countries with Arabic names
web/lib/app-state.tsx State: real runs, plus demo credits and sign-in clearly separated
web/lib/i18n.ts      All English and Arabic text
web/tests/           Unit tests
web/e2e/             Browser tests (desktop and phone sizes)
```

## Code style

Follows the prototype's style. Components don't call `fetch`, and every visible string comes from `i18n.ts`.

```tsx
const run = await api.startSearch({ cv_id, title, country, cities, remote, max_results })
router.push(`/results`)   // the run id stays in app state, not in the URL
```

## Testing strategy

- **Unit (Vitest):** API client, error mapping, polling stop conditions, data-to-screen mapping.
- **Browser (Playwright, mocked API):** the whole flow and every end state, at phone and desktop sizes, in English and Arabic. Includes the sideways-scroll check.
- **Contract (pytest):** every backend `Country` value exists in `web/lib/countries.ts`. New endpoints get offline tests.
- **One real run through the website** at the end: at most 5 jobs, about $0.05–0.20. I'll ask before running it.
- **Visual check:** screenshots at phone and desktop sizes, then you review on your own phone.

## Boundaries

- **Always:** keep the design's look; give English and Arabic every string; label demo areas "Demo"; run tests and the build at each step.
- **Ask first:** new dependencies beyond this spec; changing existing backend endpoints; any real Apify or OpenAI call; going public or deploying; committing or pushing.
- **Never:** let the site call OpenAI or Apify directly; put secrets in `web/`; log or store CV text in the browser; send data to analytics or other third parties; let the UI imply demo credits or sign-in are real; claim something works without running it.

## Success criteria

1. A real CV can go from upload to a downloaded tailored PDF through the website, on phone and desktop sizes.
2. No fake job, person or result can appear in the main flow.
3. The estimated price appears before any paid action.
4. Every backend status and error shows a clear message in both languages.
5. Mobile requirements above pass in automated tests, and on your own phone.
6. Arabic reads right-to-left on all pages, with no broken mixed text.
7. Deleting data removes it from the backend and the browser.
8. `npm run build` passes with type checking on, and all tests pass.

## Before this can go public (later stage)

Without accounts, anyone with the link could spend your OpenAI and Apify money. Real login, usage limits, final legal text and hosting all have to come first.

## Open questions

1. Is the name **Candor** final? The spec assumes yes.
2. Showing the estimated price in USD next to the demo credits: is that what you want while credits are demo?
