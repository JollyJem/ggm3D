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


def test_catalog_shows_qr_code():
    resp = client.get("/")
    assert 'src="/static/img/qr.png"' in resp.text
    assert "Scan to open on your phone" in resp.text
    # desktop only: hidden below the sm breakpoint, phones are already here
    assert 'class="hidden sm:flex' in resp.text


def test_product_detail_has_viewer_with_ar():
    resp = client.get(f"/products/{SEED_PRODUCTS[0]['id']}")
    assert resp.status_code == 200
    assert "<model-viewer" in resp.text
    assert 'ar-modes="scene-viewer webxr quick-look"' in resp.text
    # generated model when one exists, hand-placed sample otherwise
    assert 'src="/static/models/' in resp.text


def test_product_detail_links_to_the_ggm_catalog_page():
    sink = next(p for p in SEED_PRODUCTS if p["category"] == "sink")
    resp = client.get(f"/products/{sink['id']}")
    assert f'href="{sink["product_url"]}"' in resp.text
    assert 'target="_blank"' in resp.text
    assert 'rel="noopener noreferrer"' in resp.text


def test_product_detail_omits_link_when_absent():
    table = next(p for p in SEED_PRODUCTS if p["category"] == "work_table")
    assert "product_url" not in table  # no public link recorded for this one
    resp = client.get(f"/products/{table['id']}")
    assert "View on ggmgastro.com" not in resp.text


def test_unknown_product_returns_404():
    resp = client.get("/products/no-such-id")
    assert resp.status_code == 404
