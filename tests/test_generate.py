import pytest
from fastapi.testclient import TestClient

from app import main, storage
from app.main import app
from app.seed_data import SEED_PRODUCTS

client = TestClient(app)

PARAMETRIC_ID = SEED_PRODUCTS[0]["id"]  # work table
AI_ID = SEED_PRODUCTS[3]["id"]  # planetary mixer


@pytest.fixture(autouse=True)
def isolated_storage(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "MODELS_DIR", tmp_path)
    main.JOBS.clear()
    yield
    main.JOBS.clear()


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


def test_generate_ai_category_is_unavailable():
    resp = client.post(f"/products/{AI_ID}/generate")
    assert resp.status_code == 200
    assert "Phase 3" in resp.text
    assert not (storage.MODELS_DIR / f"{AI_ID}.glb").exists()


def test_detail_page_shows_generated_model_when_present():
    client.post(f"/products/{PARAMETRIC_ID}/generate")
    page = client.get(f"/products/{PARAMETRIC_ID}")
    assert f"{PARAMETRIC_ID}.glb" in page.text
    assert "Sample model" not in page.text
