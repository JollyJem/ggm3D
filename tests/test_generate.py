import pytest
from fastapi.testclient import TestClient

from app import db, main, storage
from app.main import app
from app.schemas import Product
from app.seed_data import SEED_PRODUCTS

client = TestClient(app)

PARAMETRIC_ID = SEED_PRODUCTS[0]["id"]  # work table

# The catalog is parametric-only since the ai products were retired, but the
# ai serving path in main.py is still live code; exercise it with a synthetic
# product injected at the db layer.
AI_PRODUCT = Product(
    id="00000000-0000-4000-8000-0000000000a1",
    name="Test planetary mixer",
    category="mixer",
    width_mm=520,
    depth_mm=430,
    height_mm=780,
)
AI_ID = AI_PRODUCT.id


@pytest.fixture(autouse=True)
def isolated_storage(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "MODELS_DIR", tmp_path)
    main.JOBS.clear()
    yield
    main.JOBS.clear()


@pytest.fixture
def ai_product(monkeypatch):
    real_get = db.get_product
    monkeypatch.setattr(
        db,
        "get_product",
        lambda pid: AI_PRODUCT if pid == AI_ID else real_get(pid),
    )
    return AI_PRODUCT


def test_generate_parametric_flow():
    resp = client.post(f"/products/{PARAMETRIC_ID}/generate")
    assert resp.status_code == 200
    assert 'hx-trigger="every 2s"' in resp.text  # polling status partial

    # TestClient runs the background task before returning, so the model
    # is ready by the time the first poll arrives.
    status = client.get(f"/products/{PARAMETRIC_ID}/model-status")
    assert status.status_code == 200
    assert "<model-viewer" in status.text
    assert f"{PARAMETRIC_ID}.glb" in status.text

    assert (storage.MODELS_DIR / f"{PARAMETRIC_ID}.glb").is_file()
    spec = storage.load_cached_spec(PARAMETRIC_ID)
    assert spec is not None
    assert spec.source == "fallback"  # no GEMINI_API_KEY in tests


def test_generate_reuses_cached_spec(monkeypatch):
    client.post(f"/products/{PARAMETRIC_ID}/generate")

    def boom(_product):
        raise AssertionError("cached spec must be reused, llm must not be called")

    monkeypatch.setattr(main.llm, "get_build_spec", boom)
    resp = client.post(f"/products/{PARAMETRIC_ID}/generate")
    assert resp.status_code == 200
    status = client.get(f"/products/{PARAMETRIC_ID}/model-status")
    assert "<model-viewer" in status.text


def test_resized_product_ignores_the_cached_spec(monkeypatch):
    """A spec outlives the row it was built from. Once the catalog is corrected,
    reusing it rebuilds the model at a size the product no longer has — and AR
    puts exactly that size in the room."""
    client.post(f"/products/{PARAMETRIC_ID}/generate")
    original_w = SEED_PRODUCTS[0]["width_mm"]
    assert storage.load_cached_spec(PARAMETRIC_ID).spec.width_mm == original_w

    resized = Product(**{**SEED_PRODUCTS[0], "width_mm": original_w + 400})
    monkeypatch.setattr(db, "get_product", lambda pid: resized)
    client.post(f"/products/{PARAMETRIC_ID}/generate")
    assert storage.load_cached_spec(PARAMETRIC_ID).spec.width_mm == original_w + 400


def test_only_one_build_is_claimed_per_product():
    assert main._claim_job(PARAMETRIC_ID) is True
    assert main._claim_job(PARAMETRIC_ID) is False  # a second tap, still running
    main._finish_job(PARAMETRIC_ID, {"status": "ready"})
    assert main._claim_job(PARAMETRIC_ID) is True  # finished, a rebuild may start


def test_second_tap_while_running_starts_no_second_build(monkeypatch):
    main.JOBS[PARAMETRIC_ID] = {"status": "running"}

    def boom(_product):
        raise AssertionError("a build is already running, another must not start")

    monkeypatch.setattr(main, "_run_generation", boom)
    resp = client.post(f"/products/{PARAMETRIC_ID}/generate")
    assert resp.status_code == 200
    assert 'hx-trigger="every 2s"' in resp.text  # still shows the spinner


def test_lost_build_stops_the_poll():
    """JOBS is in memory. After a restart the poll finds no job and no file;
    the honest answer ends the 2 s poll, which would otherwise keep firing for
    as long as the tab stays open."""
    resp = client.get(f"/products/{PARAMETRIC_ID}/model-status")
    assert resp.status_code == 200
    assert "Generation failed" in resp.text
    assert "interrupted" in resp.text
    assert "Retry" in resp.text
    assert 'hx-trigger="every 2s"' not in resp.text


def _install_ai_placeholder() -> None:
    from app.generator.placeholder import build_placeholder
    from app.schemas import SpecResult

    glb = build_placeholder(AI_PRODUCT).export(file_type="glb")
    storage.save_model(AI_PRODUCT.id, glb, SpecResult(source="placeholder"))


def test_generate_ai_product_served_from_cache(ai_product):
    _install_ai_placeholder()
    resp = client.post(f"/products/{AI_ID}/generate")
    assert resp.status_code == 200
    assert "<model-viewer" in resp.text
    assert f"{AI_ID}.glb" in resp.text
    spec = storage.load_cached_spec(AI_ID)
    assert spec is not None
    assert spec.source == "placeholder"


def test_ai_detail_page_shows_cached_model(ai_product):
    _install_ai_placeholder()
    page = client.get(f"/products/{AI_ID}")
    assert f"{AI_ID}.glb" in page.text
    assert "Model pending" not in page.text


def test_ai_product_pending_without_cache(ai_product):
    resp = client.post(f"/products/{AI_ID}/generate")
    assert resp.status_code == 200
    assert "Model pending" in resp.text
    page = client.get(f"/products/{AI_ID}")
    assert "Model pending" in page.text
    assert "Generate 3D model" not in page.text
    assert not (storage.MODELS_DIR / f"{AI_ID}.glb").exists()


def test_regenerate_clears_stale_usdz():
    client.post(f"/products/{PARAMETRIC_ID}/generate")
    storage.save_usdz(PARAMETRIC_ID, b"stale usdz bytes")
    status = client.get(f"/products/{PARAMETRIC_ID}/model-status")
    assert "ios-src" in status.text

    # a fresh GLB invalidates the converted USDZ; the viewer must fall
    # back to no ios-src rather than hand iPhones an outdated model
    client.post(f"/products/{PARAMETRIC_ID}/generate")
    assert storage.get_usdz_url(PARAMETRIC_ID) is None
    assert not (storage.MODELS_DIR / f"{PARAMETRIC_ID}.usdz").exists()
    status = client.get(f"/products/{PARAMETRIC_ID}/model-status")
    assert "<model-viewer" in status.text
    assert "ios-src" not in status.text


def test_detail_page_shows_generated_model_when_present():
    client.post(f"/products/{PARAMETRIC_ID}/generate")
    page = client.get(f"/products/{PARAMETRIC_ID}")
    assert f"{PARAMETRIC_ID}.glb" in page.text
    assert "Sample model" not in page.text
