# Implementation Plan: Accounts

Spec: [SPEC-accounts.md](../SPEC-accounts.md). Task list: [accounts-todo.md](accounts-todo.md).

## Overview

Add Clerk sign-in, make the backend verify every caller, tie all CVs and runs to their owner, then add the free allowance and limits. The riskiest connections are proven first, against real Clerk, before anything is built on them.

## Architecture decisions

- **The backend verifies identity itself.** The website's check only decides what to show. Authorization lives in the backend, so a direct API call can't skip it.
- **Ownership is enforced in the store,** by passing the owner into every read and delete. A route that forgets a check then fails closed.
- **Allowance counters live in `accounts.db`.** They outlive the 24-hour CV data and hold no name or email.
- **Claims are one atomic SQL update,** refunded if a run produces nothing.
- **Verifier is injected** into `create_app`, so offline tests need no real Clerk and the app needs no bypass flag.
- **Limits use the database, not memory,** since one process serves now and that will change.

## Order

```
A1 Clerk in site ─ A2 backend verifier ─ A3 real token end to end ─┐
                                                                   ├─ A4 store owner ─ A5 routes owner ─ A6 PDF access
A7 allowance ─ A8 limits ─ A9 usage in the site ─ A10 sign-in pages ─ A11 remove demo
─ A12 Arabic + mobile ─ A13 privacy + headers ─ A14 browser tests + real run
```

## Risks and mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Adding `proxy.ts` breaks slow 10 MB uploads | High | Re-run the slow upload test in A1, before anything else |
| Clerk's Python SDK doesn't fit | Med | Proven in A2 against a real token; PyJWT fallback is already in the spec |
| Clerk's short-lived tokens expire during long polling or on phones | High | A fresh token per request; A3 tests a page left open past expiry |
| Clerk's scripts are blocked by the security policy | Med | Production build tested in A1 and A13 |
| Arabic sign-in screens lack right-to-left layout | Med | Tested in A12; reported to you before any workaround |
| Browser tests can't sign in without real accounts | Med | `@clerk/testing` with test accounts in A14 |
| Existing data has no owner | Low | It's temporary data; ownerless rows become unreachable and expire within 24 hours |
| A bug lets users pass the allowance | High | Parallel-claim tests written first in A7; the daily budget is a backstop |

## Checkpoints

- **A (after A3):** you sign in with a real account, and the backend knows who you are.
- **B (after A6):** one user can't touch another's data.
- **C (after A9):** the allowance and limits work.
- **D (after A14):** all spec success criteria met.
