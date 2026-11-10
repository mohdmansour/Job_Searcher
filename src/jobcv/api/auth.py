"""Who is calling? The backend decides this itself, from a token signed by Clerk.

The website's own sign-in check only decides what to show. Every API route depends on
`CurrentUser`, so a direct request can't skip it. Never logs tokens.
"""

import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Annotated

from clerk_backend_api.security import authenticate_request
from clerk_backend_api.security.types import AuthenticateRequestOptions
from fastapi import Depends, HTTPException, Request

from jobcv.config import Settings
from jobcv.store import LOCAL_OWNER

log = logging.getLogger(__name__)

Verifier = Callable[[Request], str | None]  # the user's id, or None if not signed in


@dataclass(frozen=True)
class User:
    id: str


def clerk_verifier(settings: Settings) -> Verifier:
    """Checks the signature, expiry, not-before and authorized party of a Clerk session token.
    Reads the `Authorization: Bearer` header, then the `__session` cookie. The cookie only
    counts for reading (it is what lets a plain download link work): a browser attaches it
    by itself, so it can't be proof that this user asked for a change."""
    secret = settings.clerk_secret_key.get_secret_value() if settings.clerk_secret_key else None
    if not secret and not settings.clerk_jwt_key:
        log.error("no Clerk key configured: every request will be refused")
        return lambda request: None
    options = AuthenticateRequestOptions(
        secret_key=secret, jwt_key=settings.clerk_jwt_key,
        authorized_parties=settings.allowed_origins, accepts_token=["session_token"])

    def verify(request: Request) -> str | None:
        if request.method != "GET" and "authorization" not in request.headers:
            return None
        state = authenticate_request(request, options)
        if not state.is_signed_in or not state.payload:
            return None
        return state.payload.get("sub") or None

    return verify


def current_user(request: Request) -> User:
    try:
        user_id = request.app.state.verifier(request)
    except Exception as e:
        log.error("sign-in check failed: %s", type(e).__name__)
        raise HTTPException(503, "sign-in check is unavailable") from e
    if not user_id or user_id == LOCAL_OWNER:
        raise HTTPException(401, "sign in required", headers={"WWW-Authenticate": "Bearer"})
    return User(user_id)


CurrentUser = Annotated[User, Depends(current_user)]
