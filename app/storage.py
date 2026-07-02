"""Model file storage, local for now.

All persistence goes through these three functions. Switching to Supabase
Storage later means changing only this module.
"""

from pathlib import Path

from app.schemas import SpecResult

MODELS_DIR = Path(__file__).resolve().parent / "static" / "models"


def save_model(product_id: str, glb_bytes: bytes, spec: SpecResult) -> str:
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    (MODELS_DIR / f"{product_id}.glb").write_bytes(glb_bytes)
    (MODELS_DIR / f"{product_id}.spec.json").write_text(
        spec.model_dump_json(indent=2), encoding="utf-8"
    )
    return get_model_url(product_id) or ""


def load_cached_spec(product_id: str) -> SpecResult | None:
    path = MODELS_DIR / f"{product_id}.spec.json"
    if not path.is_file():
        return None
    try:
        return SpecResult.model_validate_json(path.read_text(encoding="utf-8"))
    except ValueError:
        return None


def get_model_url(product_id: str) -> str | None:
    """Public URL for the product's GLB, cache-busted by mtime."""
    path = MODELS_DIR / f"{product_id}.glb"
    if not path.is_file():
        return None
    return f"/static/models/{product_id}.glb?v={int(path.stat().st_mtime)}"
