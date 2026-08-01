# CLAUDE.md

## Project

GGM 3D Configurator. A mobile-first web app that generates and displays 3D models of GGM Gastro products, with AR placement on Android. Built as a live interview demo for the AI Integrator role at GGM Gastro. The demo runs on a smartphone in front of the interviewers, so reliability beats features.

Hybrid generation:

- Parametric path (live): Gemini turns product data into a build spec. trimesh builds the mesh in seconds. For boxy products: work tables, fridges, sinks.
- AI mesh path (cached): TripoSR converts a product photo into a mesh once, offline. The GLB is stored in Supabase Storage and served instantly. For products whose shape no builder covers: machines and fittings with complex geometry.

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

Spec cache rule: after Gemini returns a valid spec, save it into models.spec_json. On later requests reuse the cache before calling Gemini. The demo must survive a Gemini outage. A cached spec is only reused while it still matches the product's category and dimensions — a spec outlives the row it was built from, and reseeding with corrected dimensions must not rebuild the model at the old size.

## Generation flow

1. User taps Generate on a product page.
2. POST /products/{id}/generate. router.py picks the path by category. Stainless furniture, refrigeration, and sinks go parametric. Machines with complex shapes go ai and serve the cached GLB.
3. Parametric: call Gemini with name, category, and dimensions. Request JSON matching the BuildSpec schema through structured output (response_schema), temperature 0.2, with a timeout well inside the 30 s budget. Validate with Pydantic. Only `features` is taken from the reply: product_type and the three dimensions are pinned from the catalog row, because a model built to numbers the catalog does not claim stands in the room at the wrong size. Cache in spec_json.
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
- A builder must hold its bounding box at every spec size, not just the catalog SKU's. The double sink is written as the real 2000 x 700 layout and mapped onto the spec through `_scaled`; basins are fitted to the width before they are cut. Absolute millimetres left in a builder overflow the moment a product is resized — a 1200 mm sink once measured 1634 mm, which AR shows as a wrong-size object in the room. tests/test_builders.py sweeps sizes other than the catalog's for exactly this.
- The product photo is the spec for how a part looks, not just the drawing: the photo of product 1 shows a black collar, a bright steel fork and a grey wheel, so a caster is not one dark lump. But one photo is one camera angle. The catalog shot of product 7 looks along the worktop at a shallow angle and its bowls read as empty, which is how the overflow standpipes came to be deleted — the unit does have them. Check a detail shot, or the product page, before concluding a part is absent.
- Material: PBRMaterial, near-white baseColorFactor, metallicFactor 1.0, roughness 0.40 for the frame and 0.50 for worktops. Stainless is a real metal, so its colour is what it reflects — but it is brushed, not chromed, and a crisper setting turned every vertical panel into a picture of whatever was opposite it. Darker plastic preset (metallic 0) for wheels, feet and handles.
- Shading: `materials.face_normals` splits every vertex per face corner, then re-averages only across edges shallower than 35 degrees. Panels and the 45 degree chamfers stay crisp; cylinders, wheels and the pressed basin lose their facets. A normal per face everywhere — the previous rule — is what made a basin read as an angular pan.
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
- model-viewer attributes: src, ios-src when a USDZ exists, ar, ar-modes="scene-viewer webxr quick-look", ar-scale="fixed", camera-controls, loading="lazy", poster with the product photo. auto-rotate is set in markup but parked immediately on screens under 640 px, on first user interaction, and whenever the page is hidden — a spinning model keeps the GPU busy, and it has to be handed to ARCore intact.
- `static/hdr/studio.hdr` carries an authored floor bounce (see its README). The download's dark lower hemisphere left every vertical panel mid-grey, where the catalog photos — shot on a white sweep — show them close to white. It only changes the viewer: in AR the light comes from ARCore's read of the real room.
- Never put a ?v= cache-buster on environment-image. model-viewer selects the Radiance loader with /\.hdr(\.js)?$/ over the whole URL, so a query string silently falls back to the image loader and the steel renders black.
- Run `python scripts/optimize_assets.py` after dropping in a new HDRI or product photo. Phones pay for every byte here.
- `python scripts/inspect_glb.py <path|url>` reports the numbers Scene Viewer cares about: triangles, nodes, materials, NaN/inf coordinates, degenerate faces, bounding box. Run it on any GLB before blaming the phone.
- No `reveal="interaction"`. The viewer partial is what HTMX swaps in when Generate finishes, and a poster waiting for a tap right then reads as a failed build.
- Nothing outside the viewer partial may hold a reference to the `<model-viewer>` element. HTMX re-inserts that partial on every Generate, so a `document`-level listener closing over the element pins each detached viewer — and its WebGL context — for the life of the tab. Phones allow only a handful of live contexts. Register page-level listeners once (`window.__ggmParkOnHide`) and resolve the element by id when they fire.
- Auth stays light. Catalog, viewer, and AR are public. Generate requires login with a single Supabase email and password account. Interviewers never create accounts.

## Scene Viewer

Android Scene Viewer is stricter than model-viewer and gets no console. A model that renders in Chrome can still fail there, so the export path is defensive:

- `sanitize_scene` runs on every scene before shading: drops faces on NaN/inf vertices, welds duplicates, removes degenerate and duplicate faces, re-winds an inverted shell. scipy and networkx are not installed, so `trimesh.repair.fix_winding` / `fix_normals` / `convex_hull` raise at call time — sanitize.py is numpy only and must stay that way.
- One mesh per material, so a product exports as at most three nodes however many boxes went into it. Scene Viewer pays per node.
- Budget: under 60k triangles and 500 KB. Products land near 1k triangles, and tests/test_builders.py holds a 4k tripwire so a regression is caught long before the ceiling.
- model-viewer copies the query string off `src` into the Scene Viewer intent, so the `?v=` cache-buster on a Supabase GLB URL arrives as a stray Scene Viewer launch parameter. Harmless today because `v` is not a parameter it defines — but never name a cache-buster `mode`, `title`, `link`, `sound`, `resizable`, or `disable_occlusion`.

## Debugging the phone over USB

The A71 froze once on AR and the cause was guessed at, not read. Wire up the cable *before* trying to reproduce it — a hard freeze takes the console with it unless something on the desktop is already writing to disk.

Enable USB debugging on the A71 (Android 13, One UI 5):

1. Settings → About phone → Software information → tap **Build number** seven times → enter the PIN → "Developer mode has been enabled".
2. Settings → Developer options → turn on **USB debugging**.
3. Plug the phone into the desktop. On the USB notification pick **File transfer / Android Auto**; charging-only mode sometimes hides the device.
4. The phone shows "Allow USB debugging?" with the desktop's RSA fingerprint. Tick **Always allow from this computer** → Allow. This prompt reappears after every OS update.

Attach DevTools:

5. Desktop Chrome → `chrome://inspect/#devices` → tick **Discover USB devices**.
6. Open the product page in Chrome *on the phone*. It appears under the device name.
7. Click **inspect** next to it. The Console and Network tabs are the real page's, live.

What this does and does not reach:

- It reaches the page: model-viewer's own logs, the GLB and HDRI requests, WebGL errors. On an AR failure model-viewer logs `Attempting to present in AR with Scene Viewer` and then `Error while trying to present in AR with Scene Viewer` before falling through to the next `ar-mode` — that pair tells you whether the handoff even started.
- It does **not** reach Scene Viewer. That is a separate native app (`com.google.android.googlequicksearchbox`), not a web view, so nothing inside it shows up in DevTools. For that you need `adb logcat`.
- A DevTools console buffer dies with the device. To survive a freeze, stream to the desktop instead: install Android platform-tools (`winget install Google.PlatformTools`), then `adb logcat > freeze.txt` in a terminal that stays open while you reproduce. Filter afterwards for `ARCore`, `SceneViewer`, `Adreno`, or `libGLESv2`.

## Deploy (Render)

- Build: pip install -r requirements.txt
- Start: uvicorn app.main:app --host 0.0.0.0 --port $PORT
- Env vars live in the Render dashboard.
- Free plan sleeps after 15 min idle. A cron-job.org job pings /health every 10 min.
- Supabase free projects pause after 7 days of inactivity. Open the dashboard before demo day.

## Phases

Phase 1, skeleton. FastAPI app, /health, catalog and detail pages, Supabase tables, seed the catalog, one hand-placed GLB in the viewer with AR turned on. Done when the model rotates in Android Chrome on the deployed URL and the AR button places it in a room.

Phase 2, parametric live. Gemini spec, part functions, builders for work table, fridge, and sink. HTMX polling. Done when Generate produces a correct-size GLB in under 30 s on the deployed app.

Phase 3, AI meshes. Pregenerate a mesh for every ai-path product, cache them, wire to the UI. Done when every catalog product shows a model and AR places one at real size in a room.

Phase 4, optional. A worker loop that processes pending rows from models, plus an Ollama provider behind llm.py as a local fallback. Interview talking point about production readiness.

## Demo insurance

- Warm the Render app 10 min before the interview.
- Specs are cached, so Generate keeps working if Gemini fails mid-demo.
- Record a 60 s screen capture as a backup.
- Confirm ARCore runs on the demo phone during week 1.

## Seed products

The catalog lives in app/seed_data.py, one entry per product: id, name, category, width_mm, depth_mm, height_mm, image, description, and an optional product_url. It is the single source of truth for both the seed script and the local fallback used when Supabase is not configured. Adding or removing a product means editing that list and, in supabase mode, rerunning python scripts/seed_products.py.

Category decides the generation path. A category that router.py has a builder for goes parametric; anything else goes ai and needs a pregenerated mesh.

Dimensions and photos come from public GGM Gastro catalog pages. Internal demo use only. Download product photos into app/static/img as {slug}.jpg; a sketch SVG at {slug}.svg stands in until then. Do not hotlink GGM URLs.

## Code style

- Small files. Functions under 40 lines where possible.
- Pydantic models in schemas.py for every request, response, and spec.
- Type hints everywhere. Ruff for linting.
- Tests cover the builders. Bounding box must match spec dimensions and the GLB must export clean.
- One task per commit. Run the app before committing.
