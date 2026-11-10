# Accounts tasks

Spec: [SPEC-accounts.md](../SPEC-accounts.md). Plan: [accounts-plan.md](accounts-plan.md).

Every task also needs passing tests for the area it changes, plus `npm run build` if the website changed.

## Phase A: Prove the connections

- [x] **A1: Add Clerk to the website** (M)
  - Accept: packages installed; `web/proxy.ts` with bare `clerkMiddleware()`; `ClerkProvider` in the layout; Clerk telemetry off; site otherwise unchanged
  - Verify: Clerk accepts the keys; slow 10 MB upload still succeeds through the proxy; production build works under the security policy
  - Files: `web/package.json`, `web/proxy.ts`, `web/app/layout.tsx`, `web/next.config.mjs`
- [x] **A2: Backend verifies Clerk tokens** (M)
  - Accept: `CurrentUser` dependency; checks signature, expiry, not-before and `azp`; verifier injectable for tests
  - Verify: abuse tests written first (no token, expired, wrong signature, wrong `azp`) fail, then pass
  - Files: `src/jobcv/api/auth.py`, `src/jobcv/config.py`, `pyproject.toml`, `tests/unit/`
- [x] **A3: Real sign-in reaches the backend** (M)
  - Accept: `api.ts` attaches a fresh token, including on upload; `GET /me` identifies the user; 401 goes to sign-in
  - Verify: you sign in; signed out gets 401; a page left open past token expiry still works
  - Depends on: A1, A2
  - Files: `web/lib/api.ts`, `web/lib/app-state.tsx`, `src/jobcv/api/app.py`

### Checkpoint A
- [x] You sign in with a real account, and the backend knows who you are

## Phase B: Everyone sees only their own data

- [x] **A4: Store records the owner** (S)
  - Accept: `user_id` on `cvs` and `runs`, added safely to existing databases; every read and delete takes the owner
  - Verify: store tests, including an existing database file being upgraded
  - Files: `src/jobcv/store.py`, `tests/unit/`
- [x] **A5: Engine and routes require the owner** (M)
  - Accept: all routes require sign-in; other users' records answer 404; one active CV per user; CLI uses a local owner
  - Verify: tests that user B can't read, delete or use user A's CV or runs
  - Depends on: A2, A4
  - Files: `src/jobcv/pipeline/engine.py`, `src/jobcv/api/app.py`, `src/jobcv/cli.py`, `tests/unit/`
- [x] **A6: PDF downloads are owner-only** (S)
  - Accept: cookie or token accepted for files; the click refreshes the token first
  - Verify: test that another user's PDF answers 404; real download works after a long wait
  - Depends on: A5
  - Files: `src/jobcv/api/app.py`, `web/components/generate/generate-view.tsx`

### Checkpoint B
- [x] One user can't touch another's data, confirmed by tests

## Phase C: Free allowance and limits

- [x] **A7: Allowance counters** (M)
  - Accept: `accounts.db`; atomic claims; refunds when no jobs are found or no PDF is produced; owner accounts unlimited
  - Verify: tests written first, including parallel claims; "Delete my data" doesn't reset the allowance
  - Files: `src/jobcv/accounts.py`, `src/jobcv/pipeline/engine.py`, `tests/unit/`
- [x] **A8: Abuse limits** (M)
  - Accept: 3 uploads a day; one active run; free search capped at 10 results; daily budget pauses free use; 403 and 429 with codes
  - Verify: a test for each limit
  - Depends on: A7
  - Files: `src/jobcv/accounts.py`, `src/jobcv/api/app.py`, `tests/unit/`
- [x] **A9: Show the allowance on the site** (M)
  - Accept: real free count replaces demo credits; 25 and 50 disabled for free accounts; clear messages for 403 and 429; owners still see dollar estimates
  - Verify: browser tests per state, in both languages
  - Depends on: A8
  - Files: `web/lib/api.ts`, `web/lib/app-state.tsx`, `web/components/chrome.tsx`, `web/components/search/search-form.tsx`, `web/lib/i18n.ts`

### Checkpoint C
- [x] The allowance and limits work end to end

## Phase D: The real sign-in experience

- [x] **A10: Sign-in and sign-up pages, protected pages** (M)
  - Accept: Clerk forms styled to match Candor; each app page calls `auth.protect()`; "Upload your CV" goes through sign-up and back
  - Verify: signed-out redirects; you complete the journey with Google, Facebook and email
  - Files: `web/app/(site)/sign-in/`, `web/app/(site)/sign-up/`, `web/app/(app)/`, `web/components/landing/landing.tsx`
- [x] **A11: Remove the demo account features** (M)
  - Accept: fake sign-in and demo credits deleted; header and Account page use the real user; browser data per user, cleared on sign-out; "Delete my data" works from any device (a backend route that doesn't need the CV id kept in the browser)
  - Verify: browser tests; no demo account code remains
  - Depends on: A9, A10
  - Files: `web/components/pages.tsx`, `web/components/chrome.tsx`, `web/lib/session.ts`, `web/lib/app-state.tsx`, `web/lib/i18n.ts`
- [x] **A12: Arabic and mobile** (S)
  - Accept: sign-in screens work in Arabic and at phone sizes, or the limits are reported to you
  - Verify: screenshots reviewed; layout tests at all sizes
  - Depends on: A10
- [x] **A13: Privacy text and security headers** (S)
  - Accept: privacy and terms name Clerk and the counters; security policy allows only Clerk's required hosts
  - Verify: no policy violations in the production build
  - Depends on: A11
  - Files: `web/lib/i18n.ts`, `web/next.config.mjs`
- [x] **A14: Browser tests, real run and docs** (M)
  - Accept: browser tests sign in with `@clerk/testing`; README updated
  - Verify: all tests and the build pass; with your go-ahead, one real run per account type; a dependency audit
  - Depends on: A12, A13

### Checkpoint D
- [x] All spec success criteria met

## Before hosting (from the independent review, safe while the backend is only on this computer)

- [ ] Add `CLERK_JWT_KEY` so tokens are checked without calling Clerk each time. Otherwise a flood of forged tokens can make Clerk's key lookup fail and sign real users out
- [ ] Keep the backend reachable only through the website, or limit request size in front of it: FastAPI reads a request body before it checks sign-in
- [ ] Run exactly one backend process per data folder: at startup it marks unfinished runs as interrupted
- [ ] Recheck the dependency audits (checked 2026-11-10). Python: `chromadb` 1.5.9 has 5 known problems with no fix yet. It comes with CrewAI, but our code never loads it, because we use no CrewAI memory or knowledge. Website: 6 low or moderate problems in the `shadcn` command-line tools. The site uses only one CSS file from that package
