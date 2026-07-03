"""FastAPI app and routes."""

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app import auth, db, llm, storage
from app.generator import router as generator
from app.schemas import Product

BASE_DIR = Path(__file__).resolve().parent


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # uvicorn.error so the line shows up in the standard uvicorn startup output
    logging.getLogger("uvicorn.error").info("GGM 3D Configurator mode: %s", db.MODE)
    yield


app = FastAPI(title="GGM 3D Configurator", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "templates")

# Phase 1 hand-placed GLB, shown until a product has a generated model.
SAMPLE_GLB_URL = "/static/models/sample.glb"

# In-memory generation status per product id (single process is fine here).
JOBS: dict[str, dict] = {}


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "mode": db.MODE}


def _login_required(request: Request) -> Response | None:
    """Redirect to /login in supabase mode without a valid session, else None."""
    if db.MODE != "supabase":
        return None
    if auth.verify_session_token(request.cookies.get(auth.COOKIE_NAME)):
        return None
    if request.headers.get("HX-Request"):
        return Response(status_code=401, headers={"HX-Redirect": "/login"})
    return RedirectResponse("/login", status_code=303)


@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse(request, "login.html", {"error": None})


@app.post("/login", response_class=HTMLResponse)
def login(request: Request, email: str = Form(...), password: str = Form(...)):
    error = auth.sign_in(email, password)
    if error:
        return templates.TemplateResponse(
            request, "login.html", {"error": error}, status_code=401
        )
    response = RedirectResponse("/", status_code=303)
    response.set_cookie(
        auth.COOKIE_NAME,
        auth.create_session_token(email),
        max_age=auth.COOKIE_MAX_AGE,
        httponly=True,
        samesite="lax",
    )
    return response


@app.get("/logout")
def logout():
    response = RedirectResponse("/", status_code=303)
    response.delete_cookie(auth.COOKIE_NAME)
    return response


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
            "has_model": glb_url is not None,
            "method": generator.method_for(product.category),
        },
    )


def _run_generation(product: Product) -> None:
    """Spec (cached, Gemini, or fallback) -> mesh -> GLB -> storage."""
    try:
        cached = storage.load_cached_spec(product.id)
        result = cached if cached and cached.spec else llm.get_build_spec(product)
        scene = generator.build_scene(result.spec)
        glb = scene.export(file_type="glb")
        storage.save_model(product.id, glb, result)
        JOBS[product.id] = {"status": "ready"}
    except Exception as exc:  # surfaced in the status partial
        JOBS[product.id] = {"status": "failed", "error": str(exc)}


@app.post("/products/{product_id}/generate", response_class=HTMLResponse)
def generate(request: Request, product_id: str, background_tasks: BackgroundTasks):
    denied = _login_required(request)
    if denied is not None:
        return denied
    product = db.get_product(product_id)
    if product is None:
        return templates.TemplateResponse(request, "404.html", {}, status_code=404)
    if generator.method_for(product.category) == "ai":
        # ai meshes are pregenerated; serve from cache or report pending
        glb_url = storage.get_model_url(product_id)
        if glb_url:
            return templates.TemplateResponse(
                request,
                "partials/viewer.html",
                {"product": product, "glb_url": glb_url, "is_sample": False},
            )
        return templates.TemplateResponse(
            request, "partials/status.html", {"product": product, "status": "pending"}
        )
    JOBS[product_id] = {"status": "running"}
    background_tasks.add_task(_run_generation, product)
    return templates.TemplateResponse(
        request, "partials/status.html", {"product": product, "status": "running"}
    )


@app.get("/products/{product_id}/model-status", response_class=HTMLResponse)
def model_status(request: Request, product_id: str):
    product = db.get_product(product_id)
    if product is None:
        return templates.TemplateResponse(request, "404.html", {}, status_code=404)
    job = JOBS.get(product_id, {})
    if job.get("status") == "failed":
        return templates.TemplateResponse(
            request,
            "partials/status.html",
            {"product": product, "status": "failed", "error": job.get("error", "")},
        )
    glb_url = None if job.get("status") == "running" else storage.get_model_url(product_id)
    if glb_url:
        return templates.TemplateResponse(
            request,
            "partials/viewer.html",
            {"product": product, "glb_url": glb_url, "is_sample": False},
        )
    return templates.TemplateResponse(
        request,
        "partials/status.html",
        {"product": product, "status": "running"},
    )
