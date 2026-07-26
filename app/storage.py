"""Model file storage: Supabase Storage + models table, or local files.

All persistence goes through these three functions. In supabase mode the
GLB lives in the public "models" bucket and the spec in models.spec_json;
reads check Supabase first and fall back to the local files, so a Supabase
hiccup mid-demo never blanks a page. Local mode is file-only, as before.
"""

import logging
import time
from datetime import datetime, timezone
from pathlib import Path

from app import db
from app.schemas import SpecResult

logger = logging.getLogger(__name__)

MODELS_DIR = Path(__file__).resolve().parent / "static" / "models"
BUCKET = "models"

# A page load asks for the GLB and the USDZ, and the status partial polls both
# every 2 s while a build runs. That is the same one row every time, so holding
# it briefly turns a burst of Supabase round trips into one. Short enough that
# a model finishing still shows up on the next poll.
ROW_TTL_SECONDS = 1.5
_row_cache: dict[str, tuple[float, dict | None]] = {}


def save_model(product_id: str, glb_bytes: bytes, spec: SpecResult) -> str:
    try:
        if db.MODE == "supabase" and db.get_client() is not None:
            return _save_supabase(product_id, glb_bytes, spec)
        MODELS_DIR.mkdir(parents=True, exist_ok=True)
        (MODELS_DIR / f"{product_id}.glb").write_bytes(glb_bytes)
        (MODELS_DIR / f"{product_id}.spec.json").write_text(
            spec.model_dump_json(indent=2), encoding="utf-8"
        )
        # the old USDZ no longer matches the new GLB; drop it so the viewer
        # omits ios-src instead of sending iPhones an outdated model
        (MODELS_DIR / f"{product_id}.usdz").unlink(missing_ok=True)
        return get_model_url(product_id) or ""
    finally:
        _invalidate(product_id)


def load_cached_spec(product_id: str) -> SpecResult | None:
    if db.MODE == "supabase":
        row = _fetch_model_row(product_id)
        if row and row.get("spec_json"):
            try:
                return SpecResult.model_validate(row["spec_json"])
            except ValueError:
                logger.warning("invalid spec_json for product %s", product_id)
    path = MODELS_DIR / f"{product_id}.spec.json"
    if not path.is_file():
        return None
    try:
        return SpecResult.model_validate_json(path.read_text(encoding="utf-8"))
    except ValueError:
        return None


def get_model_url(product_id: str) -> str | None:
    """Public URL for the product's GLB, cache-busted, None when absent."""
    if db.MODE == "supabase":
        row = _fetch_model_row(product_id)
        if row and row.get("status") == "ready" and row.get("glb_url"):
            return row["glb_url"]
    path = MODELS_DIR / f"{product_id}.glb"
    if not path.is_file():
        return None
    return f"/static/models/{product_id}.glb?v={int(path.stat().st_mtime)}"


def get_usdz_url(product_id: str) -> str | None:
    """Public URL for the product's USDZ (iPhone Quick Look), None when absent."""
    if db.MODE == "supabase":
        row = _fetch_model_row(product_id)
        if row and row.get("status") == "ready" and row.get("usdz_url"):
            return row["usdz_url"]
    path = MODELS_DIR / f"{product_id}.usdz"
    if not path.is_file():
        return None
    return f"/static/models/{product_id}.usdz?v={int(path.stat().st_mtime)}"


def save_usdz(product_id: str, usdz_bytes: bytes) -> str:
    """Store a USDZ next to the product's GLB and record it in models.usdz_url."""
    try:
        if db.MODE == "supabase" and db.get_client() is not None:
            client = db.get_client()
            path = f"{product_id}.usdz"
            client.storage.from_(BUCKET).upload(
                path,
                usdz_bytes,
                file_options={"content-type": "model/vnd.usdz+zip", "upsert": "true"},
            )
            public_url = client.storage.from_(BUCKET).get_public_url(path).rstrip("?")
            usdz_url = f"{public_url}?v={int(time.time())}"
            client.table("models").update(
                {
                    "usdz_url": usdz_url,
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }
            ).eq("product_id", product_id).execute()
            return usdz_url
        MODELS_DIR.mkdir(parents=True, exist_ok=True)
        (MODELS_DIR / f"{product_id}.usdz").write_bytes(usdz_bytes)
        return get_usdz_url(product_id) or ""
    finally:
        _invalidate(product_id)


def _save_supabase(product_id: str, glb_bytes: bytes, spec: SpecResult) -> str:
    client = db.get_client()
    path = f"{product_id}.glb"
    client.storage.from_(BUCKET).upload(
        path,
        glb_bytes,
        file_options={"content-type": "model/gltf-binary", "upsert": "true"},
    )
    public_url = client.storage.from_(BUCKET).get_public_url(path).rstrip("?")
    glb_url = f"{public_url}?v={int(time.time())}"
    method = "ai" if spec.source in ("placeholder", "triposr") else "parametric"
    client.table("models").upsert(
        {
            "product_id": product_id,
            "method": method,
            "status": "ready",
            "glb_url": glb_url,
            # new GLB invalidates any previously converted USDZ;
            # scripts/convert_usdz.py repopulates it
            "usdz_url": "",
            "spec_json": spec.model_dump(),
            "error": "",
            "updated_at": datetime.now(timezone.utc).isoformat(),
        },
        on_conflict="product_id",
    ).execute()
    return glb_url


def _fetch_model_row(product_id: str) -> dict | None:
    cached = _row_cache.get(product_id)
    if cached is not None and time.monotonic() - cached[0] < ROW_TTL_SECONDS:
        return cached[1]
    client = db.get_client()
    if client is None:
        return None
    try:
        rows = (
            client.table("models")
            .select("status, glb_url, usdz_url, spec_json")
            .eq("product_id", product_id)
            .execute()
            .data
        )
    except Exception:
        logger.exception("Supabase read failed, falling back to local files")
        return None  # deliberately not cached: retry the next call
    row = rows[0] if rows else None
    _row_cache[product_id] = (time.monotonic(), row)
    return row


def _invalidate(product_id: str) -> None:
    """Drop the cached row so the just-written URL is visible immediately."""
    _row_cache.pop(product_id, None)
