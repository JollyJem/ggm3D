"""FastAPI app and routes."""

import logging
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from fastapi import BackgroundTasks, FastAPI, Form, Request
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.datastructures import MutableHeaders

from app import auth, db, llm, storage
from app.generator import router as generator
from app.schemas import Product

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"

# One year. Only ever sent for URLs that carry a ?v= stamp, so a changed file
# means a changed URL and the old entry is simply never asked for again.
IMMUTABLE_MAX_AGE = 31_536_000
# Everything else: long enough that a phone revalidates nothing during a demo,
# short enough that a deploy is picked up the same day.
DEFAULT_MAX_AGE = 3_600


def _asset_version() -> str:
    """Newest mtime under static/, stamped onto asset URLs as ?v=.

    Read once at import. Editing a stylesheet during development changes the
    number, which changes the URL, which is what lets the responses be cached
    as immutable without ever serving a stale file.
    """
    mtimes = [p.stat().st_mtime for p in STATIC_DIR.rglob("*") if p.is_file()]
    return str(int(max(mtimes))) if mtimes else "0"


ASSET_VERSION = _asset_version()


class CachedStaticFiles(StaticFiles):
    """StaticFiles with cache lifetimes. Stock StaticFiles sends an ETag and
    nothing else, so a phone pays a revalidation round trip per asset per page
    view — on mobile latency that costs more than the bytes do."""

    def file_response(
        self,
        full_path,
        stat_result,
        scope,
        status_code: int = 200,
    ) -> Response:
        response = super().file_response(full_path, stat_result, scope, status_code)
        query = parse_qs(scope.get("query_string", b"").decode("latin-1"))
        # Cache-Control survives on a 304 too, which is how a phone that already
        # revalidated once learns not to ask again.
        response.headers["Cache-Control"] = (
            f"public, max-age={IMMUTABLE_MAX_AGE}, immutable"
            if query.get("v")
            else f"public, max-age={DEFAULT_MAX_AGE}"
        )
        return response


class HTMLCacheHeaders:
    """Mark HTML as must-revalidate.

    With no Cache-Control at all a browser invents its own freshness window
    from the Last-Modified date, which on a demo means tapping Generate and
    being handed the page as it looked before. no-cache still lets the phone
    keep the body and revalidate into a 304 — it only forbids using it blind.

    Written as raw ASGI rather than the usual `@app.middleware("http")`, which
    is BaseHTTPMiddleware: that wraps every response in a streaming task and
    drops Content-Length on the way through, so the whole app would go chunked
    to set one header.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_header(message):
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                content_type = headers.get("content-type", "")
                if content_type.startswith("text/html") and "cache-control" not in headers:
                    headers["cache-control"] = "no-cache"
            await send(message)

        await self.app(scope, receive, send_with_header)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # uvicorn.error so the line shows up in the standard uvicorn startup output
    logging.getLogger("uvicorn.error").info("GGM 3D Configurator mode: %s", db.MODE)
    yield


app = FastAPI(title="GGM 3D Configurator", lifespan=lifespan)
app.add_middleware(HTMLCacheHeaders)
# HTML and CSS compress hard (~65%), and the RGBE HDRI still gives up ~23%.
# The 500-byte floor skips payloads too small for the CPU cost to pay off.
app.add_middleware(GZipMiddleware, minimum_size=500)
app.mount("/static", CachedStaticFiles(directory=STATIC_DIR), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "templates")
templates.env.globals["asset_version"] = ASSET_VERSION

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
            "usdz_url": storage.get_usdz_url(product_id) if glb_url else None,
            "is_sample": glb_url is None,
            "has_model": glb_url is not None,
            "method": generator.method_for(product.category),
            "model_origin": _origin_of(glb_url),
        },
    )


def _origin_of(url: str | None) -> str | None:
    """Scheme and host of an absolute URL, None when it is a local path.

    In supabase mode the GLB is served from the storage bucket, a third origin
    the phone has not talked to yet. model-viewer cannot ask for it until its
    own bundle has parsed, so without a hint the DNS, TCP and TLS setup starts
    late. Handing the origin to the template lets that happen up front.
    """
    if not url or not url.startswith(("http://", "https://")):
        return None
    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}"


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
                {
                    "product": product,
                    "glb_url": glb_url,
                    "usdz_url": storage.get_usdz_url(product_id),
                    "is_sample": False,
                },
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
            {
                "product": product,
                "glb_url": glb_url,
                "usdz_url": storage.get_usdz_url(product_id),
                "is_sample": False,
            },
        )
    return templates.TemplateResponse(
        request,
        "partials/status.html",
        {"product": product, "status": "running"},
    )
