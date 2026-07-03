"""Mode selection and the auth gate. Never touches real Supabase."""

import base64

import pytest
from fastapi.testclient import TestClient

from app import auth, db, main, storage
from app.config import Settings
from app.main import app
from app.seed_data import SEED_PRODUCTS

client = TestClient(app)

PARAMETRIC_ID = SEED_PRODUCTS[0]["id"]  # work table


@pytest.fixture(autouse=True)
def isolated_storage(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "MODELS_DIR", tmp_path)
    main.JOBS.clear()
    yield
    main.JOBS.clear()


# --- mode selection ---


def test_mode_local_with_empty_settings():
    assert db.resolve_mode(Settings()) == "local"


def test_mode_supabase_with_url_and_service_key():
    settings = Settings(
        supabase_url="https://example.supabase.co", supabase_service_key="key"
    )
    assert db.resolve_mode(settings) == "supabase"


def test_mode_local_when_service_key_missing():
    assert db.resolve_mode(Settings(supabase_url="https://example.supabase.co")) == "local"


def test_health_reports_mode():
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "mode": "local"}


# --- auth gate ---


def test_generate_needs_no_login_in_local_mode():
    assert db.MODE == "local"
    resp = client.post(f"/products/{PARAMETRIC_ID}/generate")
    assert resp.status_code == 200
    assert 'hx-trigger="every 2s"' in resp.text


def test_generate_requires_login_in_supabase_mode(monkeypatch):
    monkeypatch.setattr(db, "MODE", "supabase")
    resp = client.post(
        f"/products/{PARAMETRIC_ID}/generate", headers={"HX-Request": "true"}
    )
    assert resp.status_code == 401
    assert resp.headers["HX-Redirect"] == "/login"


def test_generate_redirects_browser_posts_in_supabase_mode(monkeypatch):
    monkeypatch.setattr(db, "MODE", "supabase")
    resp = client.post(f"/products/{PARAMETRIC_ID}/generate", follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/login"


def test_generate_allows_valid_session_in_supabase_mode(monkeypatch):
    monkeypatch.setattr(db, "MODE", "supabase")
    with TestClient(app) as session_client:
        session_client.cookies.set(
            auth.COOKIE_NAME, auth.create_session_token("demo@example.com")
        )
        resp = session_client.post(f"/products/{PARAMETRIC_ID}/generate")
    assert resp.status_code == 200
    assert 'hx-trigger="every 2s"' in resp.text


def test_login_page_is_mobile_friendly():
    resp = client.get("/login")
    assert resp.status_code == 200
    assert 'action="/login"' in resp.text
    assert "min-h-[44px]" in resp.text


def test_logout_clears_session_cookie():
    with TestClient(app) as session_client:
        session_client.cookies.set(
            auth.COOKIE_NAME, auth.create_session_token("demo@example.com")
        )
        resp = session_client.get("/logout", follow_redirects=False)
    assert resp.status_code == 303
    set_cookie = resp.headers["set-cookie"]
    assert set_cookie.startswith(f'{auth.COOKIE_NAME}=""')
    assert "Max-Age=0" in set_cookie


# --- session tokens ---


def test_session_token_roundtrip():
    token = auth.create_session_token("demo@example.com")
    assert auth.verify_session_token(token) == "demo@example.com"


def test_session_token_rejects_garbage():
    assert auth.verify_session_token(None) is None
    assert auth.verify_session_token("") is None
    assert auth.verify_session_token("not-base64!!") is None


def test_session_token_rejects_forged_signature():
    forged = base64.urlsafe_b64encode(b"evil@example.com:deadbeef").decode()
    assert auth.verify_session_token(forged) is None
