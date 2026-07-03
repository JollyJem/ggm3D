"""Login via Supabase email/password, session as an HMAC-signed cookie.

The cookie is verified locally (no network per request), so the generate
gate keeps working even if Supabase hiccups mid-demo. Only used in
supabase mode; local mode has no auth gate.
"""

import base64
import hashlib
import hmac
import logging
import secrets

from app.config import get_settings

logger = logging.getLogger(__name__)

COOKIE_NAME = "session"
COOKIE_MAX_AGE = 60 * 60 * 24 * 7  # one week, outlives the interview

# local mode has no service key; random per-process secret keeps HMAC valid
_FALLBACK_SECRET = secrets.token_hex(32)


def _secret() -> bytes:
    return (get_settings().supabase_service_key or _FALLBACK_SECRET).encode()


def _sign(email: str) -> str:
    return hmac.new(_secret(), email.encode(), hashlib.sha256).hexdigest()


def create_session_token(email: str) -> str:
    return base64.urlsafe_b64encode(f"{email}:{_sign(email)}".encode()).decode()


def verify_session_token(token: str | None) -> str | None:
    """Email from a valid session token, None otherwise."""
    if not token:
        return None
    try:
        decoded = base64.urlsafe_b64decode(token.encode()).decode()
    except (ValueError, UnicodeDecodeError):
        return None
    email, _, signature = decoded.rpartition(":")
    if not email or not hmac.compare_digest(signature, _sign(email)):
        return None
    return email


def sign_in(email: str, password: str) -> str | None:
    """Check credentials against Supabase. Returns an error message or None."""
    settings = get_settings()
    if not (settings.supabase_url and settings.supabase_anon_key):
        return "Login is not configured (missing SUPABASE_ANON_KEY)."
    from supabase import create_client

    client = create_client(settings.supabase_url, settings.supabase_anon_key)
    try:
        client.auth.sign_in_with_password({"email": email, "password": password})
    except Exception:
        logger.exception("Supabase sign-in failed")
        return "Invalid email or password."
    return None
