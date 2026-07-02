"""FastAPI app and routes."""

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app import db

BASE_DIR = Path(__file__).resolve().parent

app = FastAPI(title="GGM 3D Configurator")
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "templates")

# Phase 1: one hand-placed GLB shown on every product page.
SAMPLE_GLB_URL = "/static/models/sample.glb"


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/", response_class=HTMLResponse)
def catalog(request: Request):
    products = db.list_products()
    return templates.TemplateResponse(
        request, "index.html", {"products": products}
    )


@app.get("/products/{product_id}", response_class=HTMLResponse)
def product_detail(request: Request, product_id: str):
    product = db.get_product(product_id)
    if product is None:
        return templates.TemplateResponse(
            request, "404.html", {}, status_code=404
        )
    return templates.TemplateResponse(
        request,
        "product.html",
        {"product": product, "glb_url": SAMPLE_GLB_URL},
    )
