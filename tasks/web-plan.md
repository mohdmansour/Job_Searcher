# Implementation Plan: Website (Candor front end)

Spec: [SPEC-web.md](../SPEC-web.md). Task list: [web-todo.md](web-todo.md). Phase 1's `plan.md` and `todo.md` are finished and stay as they are.

## Overview

Bring the V0 prototype into `web/`, then replace its fake data with the real backend one user step at a time. Each step leaves the site working. Demo areas (sign-in, credits, pricing) stay and are labelled. Mobile is checked by automated tests from the start, not only at the end.

## Architecture decisions

- **`web/` in this repository.** One repository, so the website and the API change together.
- **Next.js forwards `/api/*` to FastAPI.** The browser talks to one address, the backend stays private, and no CORS is needed.
- **`web/lib/api.ts` is the only code that calls the backend.** Screens never call `fetch`, so the mocked tests and later login work fit in one place.
- **Upload uses XHR with a progress event.** `POST /cv` stays one blocking call, and the design's "uploading" and "reading" phases become real: reading starts when the bytes finish sending.
- **Run ids live in browser storage, not URLs.** They act as access tokens, and phones often reload background tabs.
- **Polling stops at an end state** (`done`, `failed`, `stopped_cost_cap`, 404), pauses while the tab is hidden, and resumes on return.
- **Real run state and demo state are separate** in `app-state.tsx`, so accounts can replace the demo part later without touching the main flow.
- **Tests mock the API at the browser level.** They make no paid calls and cover states that are hard to trigger for real.

## Task order

```
W1 import ─ W2 test tools ─┬─ W3 backend additions ─┐
                           └─ W4 API client + proxy ┴─ W5 upload ─ W6 form ─ W7 search run
                                                       ─ W8 results ─ W9 selection
                                                       ─ W10 tailoring ─ W11 end states
                                                       ─ W12 demo areas ─ W13 copy
                                                       ─ W14 mobile ─ W15 Arabic ─ W16 real run + docs
```

The riskiest connection work (W3, W4) comes first. W12 removes the fake data only after every screen has stopped using it.

## Risks and mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Next.js proxy cuts off the slow CV upload (default timeout is about 30 s) | High | Raise the timeout in W4 and prove it with a slow 10 MB test upload before building screens |
| V0 code has type errors hidden by `ignoreBuildErrors` | Med | Turn checking on in W1 and fix them first |
| Next.js 16 and Base UI are newer than my training data | Med | Read the versions' installed docs and types when something behaves differently, and verify with a build |
| Phones reload the page during long runs | High | Stored ids plus polling resume (W7, W10, W14) |
| Mixed Arabic and English text breaks visually | Med | Screenshots of real mixed content in W15 |
| Real runs cost money | Low | Mocked tests everywhere; one capped real run in W16, after asking |
| Someone mistakes demo areas for real ones | Med | "Demo" labels and a test for them in W12 |
| Automated mobile tests miss real-device issues | Med | You check on your own phone at the end |

## Checkpoints

- **A (after W4):** the site builds with type checking, the proxy handles a slow large upload.
- **B (after W11):** the whole flow works against the mocked API at phone and desktop sizes. You review it.
- **C (after W15):** no fake data remains, copy is truthful, mobile and Arabic pass. You review it.
- **D (after W16):** a real run succeeded through the website, and you've tried it on your phone.
