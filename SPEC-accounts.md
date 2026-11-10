# Spec: Accounts (Clerk sign-in, ownership, free allowance)

**Status:** APPROVED 2026-11-10, with the recommended answers to the open questions: 10 free results, keep email sign-up, "paid plans are coming soon", $5 daily budget. **Related:** [SPEC.md](SPEC.md) (backend), [SPEC-web.md](SPEC-web.md) (website).

## Objective

Make the site safe to open to the public by requiring sign-in before any paid or personal step, tying every CV and run to its owner, and limiting what each account can spend.

**User flow:** a visitor reads the landing, pricing, FAQ, privacy and terms pages freely. "Upload your CV" leads to sign-up with Google, Facebook or email, then straight back to the upload. Each verified account gets one free search and one free tailored CV.

**Not in this stage:** payments, hosting or a production launch, Apple sign-in, organizations.

## Assumptions

1. Clerk's Hobby plan, with Google, Facebook and email sign-up. Apple is off.
2. No payments yet, so everyone is on the free allowance except the owner accounts listed in config.
3. The browser keeps talking to `/api/*` on the website, and the backend stays private.
4. Clerk stores names and emails. The backend stores only Clerk's user id, never a name or email.

## Threat model

| Boundary | Main threats | Control |
|---|---|---|
| Browser to website | Using the app without an account | Clerk session; every app page calls `auth.protect()` |
| Website to backend | Forged or expired identity; another user's token | Backend verifies the token itself: signature, expiry, not-before, authorized party |
| Any id in a URL | Reading someone else's CV, run or PDF | Every query is filtered by owner; other people's records answer 404 |
| Free allowance | Many accounts, repeated uploads, parallel requests | Atomic counters, upload limit, one active run per user, global daily budget |
| Sign-out on a shared computer | Next person sees earlier ids | Browser session data is stored per user and cleared on sign-out |

**Assets:** CVs, generated PDFs, your OpenAI and Apify credit, Clerk's secret key.

## How identity flows

```
Browser --(Authorization: Bearer <Clerk session token>)--> Next.js /api/* --> FastAPI
                                                                              verifies token
                                                                              user_id = token "sub"
```

- `web/lib/api.ts` attaches a fresh token from Clerk's `getToken()` to every request, including the upload.
- PDF links can't carry a header, so they rely on Clerk's `__session` cookie, which the proxy forwards. The click refreshes the token first, so a page left open still downloads.
- The backend accepts either source and has one dependency, `CurrentUser`, used by every route.
- Allowed origins are configured (`JOBCV_ALLOWED_ORIGINS`), and the token's `azp` claim must match.

## Backend changes

**Existing endpoints:** same paths and bodies. All now require sign-in.

| Status | Meaning | Website message |
|---|---|---|
| 401 | Not signed in, or token invalid | Goes to sign-in, then back |
| 403 with `{"detail": {"code": "allowance_used"}}` | Free allowance used | Explains it, no retry |
| 404 | Missing, expired, or belongs to someone else | Existing "expired" message |
| 429 with `{"detail": {"code": "rate_limited" or "daily_budget"}}` | Limit reached | Asks them to try later |

**New endpoint:** `GET /me` returns `{free_searches_left, free_tailors_left, unlimited}`.

**Ownership:** `cvs` and `runs` get a `user_id` column. Every store read, delete and file lookup takes the owner. A user has one active CV: a new upload deletes the previous one on the server.

**Allowance store:** a third database, `data/accounts.db`, kept apart from CVs and the job cache. It holds only `user_id` and counters.

| Rule | Default | Setting |
|---|---|---|
| Free searches per account | 1 | `JOBCV_FREE_SEARCHES` |
| Free tailored CVs per account | 1 | `JOBCV_FREE_TAILORS` |
| Largest free search | 10 results | `JOBCV_FREE_MAX_RESULTS` |
| CV uploads per account per day | 3 (each costs about $0.01) | `JOBCV_DAILY_CV_UPLOADS` |
| Active runs per user | 1 | fixed |
| Total free spending per day, all users | $5, then free use pauses | `JOBCV_DAILY_FREE_BUDGET_USD` |
| Accounts with no limits (you) | none | `JOBCV_UNLIMITED_USER_IDS` |

- Claims are one atomic SQL update (`... where used < limit`), so parallel requests can't both win.
- A claim is refunded if a search finds no jobs or fails, or if a tailoring run produces no PDF.
- "Delete my data" removes CVs, runs and PDFs. It does not reset the allowance, otherwise it would give unlimited free use. The privacy page will say so.

**Verification:** Clerk's official Python SDK (`clerk-backend-api`). If it can't do this cleanly on our setup, PyJWT with Clerk's published keys, following Clerk's manual verification guide. Never decoding without verifying the signature.

**CLI:** keeps working locally as a fixed local owner, without sign-in.

## Website changes

- **`web/proxy.ts`** with bare `clerkMiddleware()`, the Next.js 16 file name. Protection is `await auth.protect()` on each app page, as Clerk now recommends.
- **Sign-in and sign-up:** replace the demo forms with Clerk's `<SignIn />` and `<SignUp />`, styled to match Candor.
- **Arabic:** `arSA` from `@clerk/localizations`, marked experimental by Clerk. Right-to-left layout gets tested. If it breaks, I'll report it before choosing a workaround.
- **Header:** real signed-in state and sign-out. The Account page shows the real name and email.
- **Credits:** the demo pill and balance go away, replaced by the real "1 free search, 1 free CV" count. The pricing page stays public and labelled illustrative until payments exist.
- **Price display:** customers see their allowance. Owner accounts still see the estimated cost in dollars for testing.
- **Free search:** the 25 and 50 result options are disabled for free accounts.
- **Browser storage:** per user, cleared on sign-out.
- **Security policy:** add only the hosts Clerk requires. Clerk's telemetry is turned off.
- **Privacy and terms:** name Clerk, describe the allowance counters.

## Dependencies (need your approval)

| Package | Where | Why |
|---|---|---|
| `@clerk/nextjs`, `@clerk/localizations` | Website | Sign-in and Arabic |
| `@clerk/ui` | Website, only if Clerk's docs require it for this setup | Styling |
| `@clerk/testing` | Website, development only | Browser tests with sign-in |
| `clerk-backend-api` | Backend | Verifying tokens |

## Commands

Same as before. New settings: `CLERK_SECRET_KEY` in the root `.env` for the backend, and `CLERK_TELEMETRY_DISABLED=1` for the website. The two Clerk keys are already planned for `web/.env.local`.

## Project structure

```
src/jobcv/api/auth.py    Token verification and the CurrentUser dependency
src/jobcv/accounts.py    Allowance counters, limits, daily budget
web/proxy.ts             Clerk middleware
web/app/(site)/sign-in/[[...sign-in]]/page.tsx, sign-up/[[...sign-up]]/page.tsx
```

## Code style

Same as the existing project. Identity comes from one place:

```python
@app.get("/runs/{run_id}")
def get_run(engine: EngineDep, user: CurrentUser, run_id: str) -> SearchRunOut:
    run = engine.get_search(run_id, owner=user.id)  # NotFound for anyone else's run
```

## Testing strategy

- **Backend (pytest, offline):** a fake verifier is injected. Abuse cases are written first: no token, expired token, wrong signature, wrong `azp`; user B reading, deleting or downloading user A's CV, run and PDF; two parallel claims of one allowance; refunds; upload limit; one active run; daily budget.
- **Website (Vitest, Playwright):** signed-out redirects; the journey back to upload after sign-up; 401, 403 and 429 messages; per-user storage; both languages at phone and desktop sizes.
- **Real sign-in:** you sign in with Google and Facebook yourself. I won't enter passwords.
- **Regression:** a 10 MB upload through the proxy again, because adding `proxy.ts` changes that path.

## Boundaries

- **Always:** verify the token on the backend; filter by owner in the store, not only in routes; keep names and emails out of our databases.
- **Ask first:** new dependencies beyond this spec; changing limits; real paid calls; hosting or production keys; committing or pushing.
- **Never:** trust a user id sent by the browser; decode a token without verifying it; put secret keys in `web/` code or in chat; store CVs or scores with the job cache; add an authentication bypass flag to the app.

## Success criteria

1. Signed out, nothing beyond public pages works: pages redirect, and every API route answers 401.
2. "Upload your CV" leads through sign-up and back to the upload.
3. Google, Facebook and email sign-in work, confirmed by you.
4. One user can't read, delete or download another user's data (automated test).
5. The allowance holds under parallel requests, and failed runs give it back.
6. The daily budget stops free use when reached.
7. Sign-in screens work at phone and desktop sizes in English and Arabic, or any Arabic limits are reported.
8. All tests and the production build pass, with the security policy on.

## Before going public (later stage)

Hosting, HTTPS, Clerk production keys, your own Google and Facebook credentials, a shared store if more than one server runs, final legal text, and removing a user's counters when their Clerk account is deleted.

## Open questions

1. **Free search size:** 10 results keeps the worst-case cost near $0.22 per free account. Is 10 right?
2. **Email sign-up:** keep it next to Google and Facebook? I recommend yes, though disposable emails make it the easiest route for abuse, and the daily budget is the backstop.
3. **After the free allowance:** with no payments yet, I'd show "You've used your free allowance. Paid plans are coming soon." Is that right?
4. **Daily budget:** is $5 a day a good ceiling while testing?
