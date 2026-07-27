# CLAUDE.md

## Project

GGM 3D Configurator. A mobile-first web app that generates and displays 3D models of GGM Gastro products, with AR placement on Android. Built as a live interview demo for the AI Integrator role at GGM Gastro. The demo runs on a smartphone in front of the interviewers, so reliability beats features.

Hybrid generation:

- Parametric path (live): Gemini turns product data into a build spec. trimesh builds the mesh in seconds. For boxy products: work tables, fridges, sinks.
- AI mesh path (cached): TripoSR converts a product photo into a mesh once, offline. The GLB is stored in Supabase Storage and served instantly. For shaped products: mixer, faucet, grill.

## Hard rules

- Zero cost. Never add paid APIs, SDKs, or services. Allowed keys: GEMINI_API_KEY, SUPABASE_URL, SUPABASE_ANON_KEY, SUPABASE_SERVICE_KEY, HF_TOKEN (optional). If a task appears to need a paid service, stop and propose a free alternative.
- Never commit .env or any secret. Keep .env.example current.
- GLB unit is meters. Build geometry in mm, scale by 0.001 on export. Origin at floor center, model resting on the ground plane. Real scale is what makes AR show true size.
- Mobile first. Check every page at 390 px width. Touch targets 44 px or larger.
- Ask before adding any dependency.
- Small steps. After each task, run the dev server and confirm the page works before moving on.

## Stack

- Python 3.12, FastAPI, Uvicorn
- Jinja2, HTMX, hand-written Tailwind-style CSS in app/static/css/app.css (no node build), model-viewer web component
- trimesh + manifold3d for parametric meshes
- google-genai SDK, model gemini-2.5-flash. Never use the deprecated google-generativeai package.
- supabase-py for auth, Postgres, and Storage
- Hosting: Render free tier, region Frankfurt
- GitHub for version control

Core packages for requirements.txt: fastapi, uvicorn, jinja2, python-multipart, trimesh, manifold3d, numpy, google-genai, supabase, httpx, pydantic, pytest, ruff.

## Commands

- Setup: python -m venv .venv, activate, pip install -r requirements.txt
- Run dev: uvicorn app.main:app --reload
- Test: pytest
- Seed products: python scripts/seed_products.py

## Structure

```
app/
  main.py          FastAPI app and routes
  config.py        settings loaded from env
  db.py            Supabase client
  llm.py           Gemini provider layer (single swap point for a local model later)
  schemas.py       Pydantic models, BuildSpec lives here
  generator/
    router.py      picks parametric or ai per product category
    parts.py       reusable part functions
    parametric.py  product builders returning a trimesh.Scene
    materials.py   PBR material presets
    sanitize.py    mesh repair run on every scene before export
  templates/       Jinja pages and HTMX partials
  static/
scripts/
  seed_products.py
  pregenerate_ai_meshes.py
  inspect_glb.py
supabase/
  schema.sql       tables and RLS policies, run by hand in the SQL editor
tests/
requirements.txt
.env.example
CLAUDE.md
```

## Database (Supabase)

products:

- id uuid pk, name text, category text
- width_mm int, depth_mm int, height_mm int
- image_url text, description text, created_at timestamptz

models:

- id uuid pk, product_id uuid fk
- method text: parametric or ai
- status text: pending, running, ready, failed
- glb_url text, spec_json jsonb, error text
- created_at, updated_at timestamptz

Storage bucket "models" with public read access. AR needs a public HTTPS GLB URL, the public bucket provides it.

Schema workflow: Claude Code writes all SQL into supabase/schema.sql. Cem pastes it into the Supabase SQL editor by hand. Enable RLS with public read policies on both tables. Writes only go through the service key on the server.

Spec cache rule: after Gemini returns a valid spec, save it into models.spec_json. On later requests reuse the cache before calling Gemini. The demo must survive a Gemini outage.

## Generation flow

1. User taps Generate on a product page.
2. POST /products/{id}/generate. router.py picks the path by category. Stainless furniture, refrigeration, and sinks go parametric. Machines with complex shapes go ai and serve the cached GLB.
3. Parametric: call Gemini with name, category, and dimensions. Request JSON matching the BuildSpec schema through structured output (response_schema), temperature 0.2. Validate with Pydantic. Cache in spec_json.
4. Build the mesh with part functions, export GLB, upload to Storage, set status ready.
5. The page polls a status partial with HTMX every 2 s, then swaps in the model-viewer.

BuildSpec sketch:

```python
class BuildSpec(BaseModel):
    product_type: Literal["work_table", "fridge", "sink"]
    width_mm: int
    depth_mm: int
    height_mm: int
    features: dict  # example: {"undershelf": True, "doors": 1, "basins": 1}
```

## Parametric builders

- Compose from part functions in parts.py: box_part, cylinder_part, top_slab, legs, undershelf, door_panel, handle, feet, basin.
- Product builders in parametric.py: build_work_table, build_fridge, build_sink. Each takes a BuildSpec and returns a trimesh.Scene. Recognizable equipment, not plain boxes. A work table has a top slab, four legs, and an undershelf. A fridge has a body, a door panel, a handle, and feet.
- Material: PBRMaterial with light gray baseColorFactor, metallicFactor 0.9, roughnessFactor 0.3 for stainless steel. Darker plastic preset for handles.
- Check axis orientation in model-viewer during Phase 1. glTF is Y-up. If the model lies on its side, apply a fixed rotation before export.
- Keep parametric GLB files under 1 MB.

## AI mesh path (offline, one time)

- scripts/pregenerate_ai_meshes.py documents the process end to end.
- Generate with TripoSR locally (GTX 1660 Ti, 6 GB VRAM) or through a free Hugging Face Space. Use one clean product photo per item.
- Scale the output to the real height from the product spec. Compress with gltfpack if the file exceeds 8 MB. Upload to Storage and insert a models row with method ai, status ready.

## Frontend

- Pages: / catalog grid, /products/{id} detail with viewer and Generate button.
- Load HTMX and model-viewer from CDN. No build step. Both are scoped to the product page via the `head_scripts` block — the catalog ships zero JavaScript and must stay that way.
- Styles are a static file, not the Tailwind CDN compiler. Class names are real Tailwind v3 utilities; a new one in a template needs the matching rule added to app/static/css/app.css. A test fails if the two drift apart.
- model-viewer attributes: src, ar, ar-modes="scene-viewer webxr", ar-scale="fixed", camera-controls, auto-rotate, poster with the product photo.
- Never put a ?v= cache-buster on environment-image. model-viewer selects the Radiance loader with /\.hdr(\.js)?$/ over the whole URL, so a query string silently falls back to the image loader and the steel renders black.
- Run `python scripts/optimize_assets.py` after dropping in a new HDRI or product photo. Phones pay for every byte here.
- `python scripts/inspect_glb.py <path|url>` reports the numbers Scene Viewer cares about: triangles, nodes, materials, NaN/inf coordinates, degenerate faces, bounding box. Run it on any GLB before blaming the phone.

## Scene Viewer

Android Scene Viewer is stricter than model-viewer and gets no console. A model that renders in Chrome can still fail there, so the export path is defensive:

- `sanitize_scene` runs on every scene before shading: drops faces on NaN/inf vertices, welds duplicates, removes degenerate and duplicate faces, re-winds an inverted shell. scipy and networkx are not installed, so `trimesh.repair.fix_winding` / `fix_normals` / `convex_hull` raise at call time — sanitize.py is numpy only and must stay that way.
- One mesh per material, so a product exports as at most three nodes however many boxes went into it. Scene Viewer pays per node.
- Budget: under 60k triangles and 500 KB. Products land near 1k triangles, and tests/test_builders.py holds a 4k tripwire so a regression is caught long before the ceiling.
- model-viewer copies the query string off `src` into the Scene Viewer intent, so the `?v=` cache-buster on a Supabase GLB URL arrives as a stray Scene Viewer launch parameter. Harmless today because `v` is not a parameter it defines — but never name a cache-buster `mode`, `title`, `link`, `sound`, `resizable`, or `disable_occlusion`.
- Auth stays light. Catalog, viewer, and AR are public. Generate requires login with a single Supabase email and password account. Interviewers never create accounts.

## Deploy (Render)

- Build: pip install -r requirements.txt
- Start: uvicorn app.main:app --host 0.0.0.0 --port $PORT
- Env vars live in the Render dashboard.
- Free plan sleeps after 15 min idle. A cron-job.org job pings /health every 10 min.
- Supabase free projects pause after 7 days of inactivity. Open the dashboard before demo day.

## Phases

Phase 1, skeleton. FastAPI app, /health, catalog and detail pages, Supabase tables, seed 6 products, one hand-placed GLB in the viewer with AR turned on. Done when the model rotates in Android Chrome on the deployed URL and the AR button places it in a room.

Phase 2, parametric live. Gemini spec, part functions, builders for work table, fridge, and sink. HTMX polling. Done when Generate produces a correct-size GLB in under 30 s on the deployed app.

Phase 3, AI meshes. Pregenerate mixer, faucet, and grill meshes, cache them, wire to the UI. Done when all 6 products show a model and AR places the fridge at real size in a room.

Phase 4, optional. A worker loop that processes pending rows from models, plus an Ollama provider behind llm.py as a local fallback. Interview talking point about production readiness.

## Demo insurance

- Warm the Render app 10 min before the interview.
- Specs are cached, so Generate keeps working if Gemini fails mid-demo.
- Record a 60 s screen capture as a backup.
- Confirm ARCore runs on the demo phone during week 1.

## Seed products (6)

- Work table with undershelf, 1200 x 700 x 850 mm, parametric
- Refrigerated cabinet, 700 x 810 x 2050 mm, parametric
- Sink unit with one basin, 1200 x 600 x 850 mm, parametric
- Planetary mixer, ai mesh
- Pre-rinse faucet, ai mesh
- Contact grill, ai mesh

Dimensions and photos come from public GGM Gastro catalog pages. Internal demo use only. Download the 6 photos into app/static/img. Do not hotlink GGM URLs.

## Code style

- Small files. Functions under 40 lines where possible.
- Pydantic models in schemas.py for every request, response, and spec.
- Type hints everywhere. Ruff for linting.
- Tests cover the builders. Bounding box must match spec dimensions and the GLB must export clean.
- One task per commit. Run the app before committing.
