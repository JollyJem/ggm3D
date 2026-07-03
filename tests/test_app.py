from fastapi.testclient import TestClient

from app.main import app
from app.seed_data import SEED_PRODUCTS

client = TestClient(app)


def test_health():
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "mode": "local"}


def test_catalog_lists_all_products():
    resp = client.get("/")
    assert resp.status_code == 200
    for product in SEED_PRODUCTS:
        assert product["name"] in resp.text


def test_product_detail_has_viewer_with_ar():
    resp = client.get(f"/products/{SEED_PRODUCTS[0]['id']}")
    assert resp.status_code == 200
    assert "<model-viewer" in resp.text
    assert 'ar-modes="scene-viewer webxr"' in resp.text
    # generated model when one exists, hand-placed sample otherwise
    assert 'src="/static/models/' in resp.text


def test_unknown_product_returns_404():
    resp = client.get("/products/no-such-id")
    assert resp.status_code == 404
