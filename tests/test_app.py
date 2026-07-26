import re

from fastapi.testclient import TestClient

from app.main import app
from app.seed_data import SEED_PRODUCTS

client = TestClient(app)

PARAMETRIC_ID = SEED_PRODUCTS[0]["id"]


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
    assert "Product Link:" in resp.text
    assert 'target="_blank"' in resp.text
    assert 'rel="noopener noreferrer"' in resp.text
    # sits under the viewer, above the description
    body = resp.text
    assert body.index('id="model-area"') < body.index("Product Link:")
    assert body.index("Product Link:") < body.index(sink["description"])


def test_product_detail_omits_link_when_absent():
    table = next(p for p in SEED_PRODUCTS if p["category"] == "work_table")
    assert "product_url" not in table  # no public link recorded for this one
    resp = client.get(f"/products/{table['id']}")
    assert "Product Link:" not in resp.text


def test_unknown_product_returns_404():
    resp = client.get("/products/no-such-id")
    assert resp.status_code == 404


# --- payload weight -------------------------------------------------------


def test_environment_image_url_has_no_query_string():
    """model-viewer chooses the Radiance loader with /\\.hdr(\\.js)?$/ against
    the whole URL. A cache-buster on the end makes it miss, the HDRI is parsed
    as an image, and it fails silently — the fully metallic steel just renders
    black. Cheap to break, invisible in a diff, so pin it here."""
    resp = client.get(f"/products/{PARAMETRIC_ID}")
    env = re.search(r'environment-image="([^"]+)"', resp.text)
    assert env is not None, "the viewer must still light the model with an HDRI"
    assert env.group(1).endswith(".hdr"), env.group(1)


def test_catalog_ships_no_javascript():
    """The catalog is a grid of links and photos. model-viewer alone is ~900 KB
    of parser work for three.js, so nothing on this page may pull in a script."""
    resp = client.get("/")
    assert "<script" not in resp.text
    assert "unpkg.com" not in resp.text
    assert "cdn.tailwindcss.com" not in resp.text


def test_product_page_loads_the_viewer_and_htmx():
    resp = client.get(f"/products/{PARAMETRIC_ID}")
    assert "model-viewer@3.5.0" in resp.text
    # the full dist path, not the bare package, which unpkg answers with a 302
    assert "htmx.org@1.9.12/dist/htmx.min.js" in resp.text


def test_stylesheet_is_served_and_covers_the_classes_in_use():
    css = client.get("/static/css/app.css")
    assert css.status_code == 200
    used = set()
    for page in ("/", f"/products/{PARAMETRIC_ID}", "/login"):
        for attr in re.findall(r'class="([^"]*)"', client.get(page).text):
            used.update(attr.split())
    escaped = css.text.replace("\\", "")
    missing = sorted(c for c in used if f".{c}" not in escaped)
    assert not missing, f"utilities used in a template but absent from app.css: {missing}"


def test_static_assets_are_cacheable():
    versioned = client.get("/static/css/app.css?v=1")
    assert "immutable" in versioned.headers["cache-control"]
    plain = client.get("/static/hdr/studio.hdr")
    assert "max-age=" in plain.headers["cache-control"]
    assert "immutable" not in plain.headers["cache-control"]


def test_html_is_revalidated_rather_than_heuristically_cached():
    assert client.get("/").headers["cache-control"] == "no-cache"


def test_responses_are_compressed():
    resp = client.get("/", headers={"Accept-Encoding": "gzip"})
    assert resp.headers.get("content-encoding") == "gzip"


def test_hdri_stays_small_enough_for_a_phone():
    """It was 1.6 MB at 1k, on every product page. Anything above ~256 px wide
    is decoded at full float precision and then thrown away by the prefilter."""
    resp = client.get("/static/hdr/studio.hdr")
    assert len(resp.content) < 200_000, f"{len(resp.content)} bytes"
