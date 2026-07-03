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


def save_model(product_id: str, glb_bytes: bytes, spec: SpecResult) -> str:
    if db.MODE == "supabase" and db.get_client() is not None:
        return _save_supabase(product_id, glb_bytes, spec)
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    (MODELS_DIR / f"{product_id}.glb").write_bytes(glb_bytes)
    (MODELS_DIR / f"{product_id}.spec.json").write_text(
        spec.model_dump_json(indent=2), encoding="utf-8"
    )
    return get_model_url(product_id) or ""


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
            "spec_json": spec.model_dump(),
            "error": "",
            "updated_at": datetime.now(timezone.utc).isoformat(),
        },
        on_conflict="product_id",
    ).execute()
    return glb_url


def _fetch_model_row(product_id: str) -> dict | None:
    client = db.get_client()
    if client is None:
        return None
    try:
        rows = (
            client.table("models")
            .select("status, glb_url, spec_json")
            .eq("product_id", product_id)
            .execute()
            .data
        )
    except Exception:
        logger.exception("Supabase read failed, falling back to local files")
        return None
    return rows[0] if rows else None
