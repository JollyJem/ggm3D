"""FastAPI app and routes."""

from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app import db, llm, storage
from app.generator import router as generator
from app.schemas import Product

BASE_DIR = Path(__file__).resolve().parent

app = FastAPI(title="GGM 3D Configurator")
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "templates")

# Phase 1 hand-placed GLB, shown until a product has a generated model.
SAMPLE_GLB_URL = "/static/models/sample.glb"

# In-memory generation status per product id (single process is fine here).
JOBS: dict[str, dict] = {}


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
    glb_url = storage.get_model_url(product_id)
    return templates.TemplateResponse(
        request,
        "product.html",
        {
            "product": product,
            "glb_url": glb_url or SAMPLE_GLB_URL,
            "is_sample": glb_url is None,
            "method": generator.method_for(product.category),
        },
    )


def _run_generation(product: Product) -> None:
    """Spec (cached, Gemini, or fallback) -> mesh -> GLB -> storage."""
    try:
        result = storage.load_cached_spec(product.id) or llm.get_build_spec(product)
        scene = generator.build_scene(result.spec)
        glb = scene.export(file_type="glb")
        storage.save_model(product.id, glb, result)
        JOBS[product.id] = {"status": "ready"}
    except Exception as exc:  # surfaced in the status partial
        JOBS[product.id] = {"status": "failed", "error": str(exc)}


@app.post("/products/{product_id}/generate", response_class=HTMLResponse)
def generate(request: Request, product_id: str, background_tasks: BackgroundTasks):
    product = db.get_product(product_id)
    if product is None:
        return templates.TemplateResponse(request, "404.html", {}, status_code=404)
    context = {"product": product}
    if generator.method_for(product.category) == "ai":
        context["status"] = "unavailable"
    else:
        JOBS[product_id] = {"status": "running"}
        background_tasks.add_task(_run_generation, product)
        context["status"] = "running"
    return templates.TemplateResponse(request, "partials/status.html", context)


@app.get("/products/{product_id}/model-status", response_class=HTMLResponse)
def model_status(request: Request, product_id: str):
    product = db.get_product(product_id)
    if product is None:
        return templates.TemplateResponse(request, "404.html", {}, status_code=404)
    job = JOBS.get(product_id, {})
    if job.get("status") == "ready":
        return templates.TemplateResponse(
            request,
            "partials/viewer.html",
            {
                "product": product,
                "glb_url": storage.get_model_url(product_id) or SAMPLE_GLB_URL,
                "is_sample": False,
            },
        )
    status = "failed" if job.get("status") == "failed" else "running"
    return templates.TemplateResponse(
        request,
        "partials/status.html",
        {"product": product, "status": status, "error": job.get("error", "")},
    )
