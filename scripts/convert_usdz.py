"""Convert product GLBs to USDZ for iPhone AR (Quick Look).

Android AR uses Scene Viewer with the GLB directly; iOS Quick Look only
accepts USDZ, wired into model-viewer through the ios-src attribute. This
script batch-converts every ready GLB to USDZ with Blender's command line
(free, keeps the zero-cost rule), uploads the files to the Supabase Storage
"models" bucket, and writes models.usdz_url. Run it once after generating
or regenerating models; regenerating a GLB later makes its USDZ stale, so
rerun this script afterwards.

Requires Blender 4.0+ (the USD exporter gained direct .usdz output in 4.0):
    winget install BlenderFoundation.Blender
or download from https://www.blender.org/download/ (free and open source).

Each file is converted headless, no UI:
    blender --background --python-expr "import bpy; \
        bpy.ops.wm.read_factory_settings(use_empty=True); \
        bpy.ops.import_scene.gltf(filepath=r'in.glb'); \
        bpy.ops.wm.usd_export(filepath=r'out.usdz')"

Scale notes: the GLB is authored in meters and Blender imports/exports USD
at 1 meter per unit, so Quick Look shows the product at real size. Blender
writes a Z-up USD stage with upAxis metadata, which Quick Look reads, so no
manual rotation is needed. Verify on an iPhone that the model stands upright
and matches the printed dimensions.

Usage:
    python scripts/convert_usdz.py                 # all products with a ready GLB
    python scripts/convert_usdz.py --blender "C:/Program Files/Blender Foundation/Blender 4.1/blender.exe"
"""

import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import httpx  # noqa: E402

from app import storage  # noqa: E402
from app.schemas import Product  # noqa: E402
from app.seed_data import SEED_PRODUCTS  # noqa: E402

# One expression per file keeps Blender state clean between conversions.
PY_EXPR = (
    "import bpy; "
    "bpy.ops.wm.read_factory_settings(use_empty=True); "
    "bpy.ops.import_scene.gltf(filepath=r'{src}'); "
    "bpy.ops.wm.usd_export(filepath=r'{dst}')"
)


def find_blender(override: str | None) -> str:
    if override:
        return override
    found = shutil.which("blender")
    if found:
        return found
    candidates = sorted(
        Path("C:/Program Files/Blender Foundation").glob("Blender */blender.exe")
    )
    if candidates:
        return str(candidates[-1])
    sys.exit("Blender not found. Install it (see docstring) or pass --blender PATH.")


def fetch_glb(product_id: str) -> bytes | None:
    """GLB bytes for a ready model, from local static files or Supabase."""
    url = storage.get_model_url(product_id)
    if url is None:
        return None
    if url.startswith("/static/"):
        return (ROOT / "app" / url.split("?")[0].lstrip("/")).read_bytes()
    return httpx.get(url, timeout=60).content


def convert(blender: str, glb_bytes: bytes) -> bytes:
    """GLB -> USDZ through headless Blender in a temp dir."""
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "in.glb"
        dst = Path(tmp) / "out.usdz"
        src.write_bytes(glb_bytes)
        expr = PY_EXPR.format(src=src, dst=dst)
        result = subprocess.run(
            [blender, "--background", "--python-expr", expr],
            capture_output=True,
            text=True,
        )
        if not dst.is_file():
            raise RuntimeError(f"Blender export failed:\n{result.stdout}\n{result.stderr}")
        return dst.read_bytes()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--blender", help="path to blender.exe if not on PATH")
    args = parser.parse_args()
    blender = find_blender(args.blender)
    print(f"Using {blender}")
    for raw in SEED_PRODUCTS:
        product = Product(**raw)
        glb = fetch_glb(product.id)
        if glb is None:
            print(f"  {product.name}: no ready GLB, skipped")
            continue
        usdz = convert(blender, glb)
        url = storage.save_usdz(product.id, usdz)
        print(f"  {product.name}: {len(usdz) / 1024:.0f} KB -> {url}")


if __name__ == "__main__":
    main()
