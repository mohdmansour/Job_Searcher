"""Identity checks, run against Clerk's real verification code with locally made keys.
Each case is a way someone might try to get in."""

from datetime import UTC, datetime, timedelta

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from jobcv.api.app import create_app
from jobcv.api.auth import clerk_verifier
from jobcv.config import Settings
from jobcv.pipeline.engine import Engine
from tests.unit.test_engine import FixtureSource, fake_llm, fake_render

ORIGIN = "http://localhost:3000"


def new_key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


KEY = new_key()
OTHER_KEY = new_key()
PUBLIC_PEM = KEY.public_key().public_bytes(
    serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode()


def token(key=KEY, alg="RS256", **claims) -> str:
    now = datetime.now(UTC)
    payload = {"sub": "user_a", "azp": ORIGIN, "iat": now, "nbf": now - timedelta(seconds=5),
               "exp": now + timedelta(minutes=5), "sid": "sess_1", **claims}
    return jwt.encode({k: v for k, v in payload.items() if v is not None}, key, algorithm=alg)


@pytest.fixture
def client(tmp_path):
    s = Settings(_env_file=None, data_dir=tmp_path, clerk_jwt_key=PUBLIC_PEM,
                 allowed_origins=[ORIGIN])
    engine = Engine(s, source=FixtureSource(), llm=fake_llm, renderer=fake_render, synchronous=True)
    with TestClient(create_app(engine, verifier=clerk_verifier(s))) as c:
        yield c


def bearer(t: str) -> dict:
    return {"Authorization": f"Bearer {t}"}


def test_a_valid_token_identifies_the_user(client):
    r = client.get("/me", headers=bearer(token()))
    assert r.status_code == 200 and r.json()["user_id"] == "user_a"


def test_the_session_cookie_also_works(client):
    client.cookies.set("__session", token())
    assert client.get("/me").status_code == 200


def test_the_cookie_alone_cannot_change_anything(client):
    client.cookies.set("__session", token())
    assert client.post("/estimate/tailor", json={"n_jobs": 1}).status_code == 401


def test_no_token_is_refused(client):
    assert client.get("/me").status_code == 401


def test_garbage_is_refused(client):
    assert client.get("/me", headers=bearer("not-a-token")).status_code == 401


def test_expired_token_is_refused(client):
    t = token(exp=datetime.now(UTC) - timedelta(minutes=5))
    assert client.get("/me", headers=bearer(t)).status_code == 401


def test_token_not_valid_yet_is_refused(client):
    t = token(nbf=datetime.now(UTC) + timedelta(minutes=5))
    assert client.get("/me", headers=bearer(t)).status_code == 401


def test_token_signed_by_someone_else_is_refused(client):
    assert client.get("/me", headers=bearer(token(key=OTHER_KEY))).status_code == 401


def test_unsigned_token_is_refused(client):
    assert client.get("/me", headers=bearer(token(key="", alg="none"))).status_code == 401


def test_token_for_another_site_is_refused(client):
    assert client.get("/me", headers=bearer(token(azp="https://evil.example"))).status_code == 401


def test_a_user_id_sent_by_the_browser_is_ignored(client):
    r = client.get("/me", headers={**bearer(token()), "X-User-Id": "user_b"}, params={"user_id": "user_b"})
    assert r.json()["user_id"] == "user_a"


def test_token_with_no_user_is_refused(client):
    assert client.get("/me", headers=bearer(token(sub=None))).status_code == 401


def test_a_verifier_failure_is_not_treated_as_signed_in(tmp_path):
    def broken(request):
        raise RuntimeError("clerk is unreachable")

    s = Settings(_env_file=None, data_dir=tmp_path)
    engine = Engine(s, source=FixtureSource(), llm=fake_llm, renderer=fake_render, synchronous=True)
    with TestClient(create_app(engine, verifier=broken), raise_server_exceptions=False) as c:
        assert c.get("/me", headers=bearer(token())).status_code == 503


def test_without_any_clerk_key_everyone_is_refused(tmp_path):
    s = Settings(_env_file=None, data_dir=tmp_path)
    engine = Engine(s, source=FixtureSource(), llm=fake_llm, renderer=fake_render, synchronous=True)
    with TestClient(create_app(engine, verifier=clerk_verifier(s))) as c:
        assert c.get("/me", headers=bearer(token())).status_code == 401
