"""Pregenerate AI meshes for the shaped products: mixer, faucet, grill.

One-time offline pipeline. Input photo: app/static/img/{slug}.jpg where the
slug is the product category (mixer, faucet, grill). Raw TripoSR output goes
into the watched folder scripts/ai_raw/{slug}.glb; this script then
normalizes it (real scale, floor origin, Y-up), compresses it if needed, and
installs it through app.storage, replacing any placeholder.

Two ways to produce the raw GLB (nothing here goes in requirements.txt):

Option A — local TripoSR on a Windows GPU (~6 GB VRAM, e.g. GTX 1660 Ti):
    git clone https://github.com/VAST-AI-Research/TripoSR
    cd TripoSR
    pip install torch torchvision --index-url https://download.pytorch.org/whl/cu121
    pip install -r requirements.txt
    python run.py ../app/static/img/mixer.jpg --output-dir ../scripts/ai_raw --model-save-format glb
    # rename the output to scripts/ai_raw/mixer.glb, repeat per product

Option B — free Hugging Face Space (no local GPU needed):
    Open https://huggingface.co/spaces/stabilityai/TripoSR in a browser,
    upload the product photo, download the resulting GLB and save it as
    scripts/ai_raw/{slug}.glb. HF_TOKEN is not required for manual use.

Then run:
    python scripts/pregenerate_ai_meshes.py            # install raw GLBs
    python scripts/pregenerate_ai_meshes.py --z-up     # if meshes lie on their side
    python scripts/pregenerate_ai_meshes.py --placeholders
        # build rough parametric placeholder meshes instead, so every
        # product shows a model before TripoSR has run

Compression: if a normalized GLB exceeds 8 MB and gltfpack is on PATH it is
compressed in place; without gltfpack a note is printed and the file is
kept uncompressed.
"""

import argparse
import io
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
import trimesh  # noqa: E402

from app import storage  # noqa: E402
from app.schemas import Product, SpecResult  # noqa: E402
from app.seed_data import SEED_PRODUCTS  # noqa: E402

RAW_DIR = ROOT / "scripts" / "ai_raw"
MAX_BYTES = 8 * 1024 * 1024

AI_PRODUCTS = [Product(**p) for p in SEED_PRODUCTS if p["category"] in ("mixer", "faucet", "grill")]


def normalize(raw_glb: bytes, height_mm: int, z_up: bool = False) -> bytes:
    """Real scale from height, floor origin, Y-up, single mesh."""
    scene = trimesh.load(io.BytesIO(raw_glb), file_type="glb")
    mesh = scene.to_geometry() if isinstance(scene, trimesh.Scene) else scene
    if z_up:
        mesh.apply_transform(
            trimesh.transformations.rotation_matrix(np.radians(-90), [1, 0, 0])
        )
    extents = mesh.bounds[1] - mesh.bounds[0]
    mesh.apply_scale(height_mm / 1000 / extents[1])
    low, high = mesh.bounds
    mesh.apply_translation([-(low[0] + high[0]) / 2, -low[1], -(low[2] + high[2]) / 2])
    return trimesh.Scene({"ai_mesh": mesh}).export(file_type="glb")


def compress_if_needed(glb: bytes, slug: str) -> bytes:
    if len(glb) <= MAX_BYTES:
        return glb
    if not shutil.which("gltfpack"):
        print(f"  {slug}: {len(glb) / 1e6:.1f} MB > 8 MB but gltfpack is not "
              "installed, keeping uncompressed (https://meshoptimizer.org/gltf/)")
        return glb
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "in.glb"
        dst = Path(tmp) / "out.glb"
        src.write_bytes(glb)
        subprocess.run(["gltfpack", "-i", str(src), "-o", str(dst)], check=True)
        packed = dst.read_bytes()
    print(f"  {slug}: gltfpack {len(glb) / 1e6:.1f} MB -> {len(packed) / 1e6:.1f} MB")
    return packed


def install_triposr(z_up: bool) -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    for product in AI_PRODUCTS:
        raw_path = RAW_DIR / f"{product.category}.glb"
        if not raw_path.is_file():
            print(f"  {product.category}: no {raw_path.relative_to(ROOT)}, skipped "
                  "(see docstring for TripoSR options)")
            continue
        glb = normalize(raw_path.read_bytes(), product.height_mm, z_up=z_up)
        glb = compress_if_needed(glb, product.category)
        url = storage.save_model(product.id, glb, SpecResult(source="triposr"))
        print(f"  {product.category}: installed {len(glb) / 1024:.0f} KB -> {url}")


def install_placeholders() -> None:
    from app.generator.placeholder import build_placeholder

    for product in AI_PRODUCTS:
        glb = build_placeholder(product).export(file_type="glb")
        url = storage.save_model(product.id, glb, SpecResult(source="placeholder"))
        print(f"  {product.category}: placeholder {len(glb) / 1024:.0f} KB -> {url}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--placeholders", action="store_true",
                        help="build rough placeholder meshes instead of TripoSR")
    parser.add_argument("--z-up", action="store_true",
                        help="rotate raw meshes that were exported Z-up")
    args = parser.parse_args()
    if args.placeholders:
        install_placeholders()
    else:
        install_triposr(z_up=args.z_up)


if __name__ == "__main__":
    main()
