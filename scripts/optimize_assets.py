"""Shrink the static assets that phones have to download. Dev tool, run by hand.

Two jobs, both offline. The results are committed as files, so nothing here
runs on the server and nothing here is a runtime dependency:

  studio.hdr   1024x512 -> 256x128. model-viewer only uses environment-image to
               prefilter a small reflection map, so anything above ~256 wide is
               decoded at full float precision and then thrown away.
  *.jpg        product photos re-encoded at the largest size actually displayed
               (the model-viewer poster, ~800 px on a phone in landscape).

Needs Pillow, which trimesh already pulls in. Deliberately not in
requirements.txt: the server never imports this.

    python scripts/optimize_assets.py [--check]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

STATIC = Path(__file__).resolve().parent.parent / "app" / "static"
HDR_PATH = STATIC / "hdr" / "studio.hdr"
HDR_TARGET_WIDTH = 256
JPEG_TARGET_WIDTH = 800
JPEG_QUALITY = 78


# --------------------------------------------------------------------------
# Radiance RGBE (.hdr). Pillow cannot read it, and the format is small enough
# to do with numpy: a text header, then scanlines of four RLE-coded planes.
# --------------------------------------------------------------------------


def read_hdr(path: Path) -> np.ndarray:
    """Decode a Radiance .hdr into a float32 (H, W, 3) array of linear RGB."""
    data = path.read_bytes()
    pos = data.index(b"\n\n") + 2 if b"\n\n" in data else 0
    eol = data.index(b"\n", pos)
    resolution = data[pos:eol].decode("ascii").split()
    if resolution[0] != "-Y" or resolution[2] != "+X":
        raise ValueError(f"unsupported scanline order: {' '.join(resolution)}")
    height, width = int(resolution[1]), int(resolution[3])

    raw = np.frombuffer(data, dtype=np.uint8, offset=eol + 1)
    rgbe = np.empty((height, width, 4), dtype=np.uint8)
    at = 0
    for y in range(height):
        if not (raw[at] == 2 and raw[at + 1] == 2 and 8 <= width <= 0x7FFF):
            raise ValueError("only new-style RLE scanlines are supported")
        at += 4
        for plane in range(4):
            at = _decode_plane(raw, at, rgbe[y, :, plane])
    return _rgbe_to_float(rgbe)


def _decode_plane(raw: np.ndarray, at: int, out: np.ndarray) -> int:
    """Fill one scanline plane from the RLE stream, return the new offset."""
    x = 0
    width = out.shape[0]
    while x < width:
        count = int(raw[at])
        at += 1
        if count > 128:  # a run of one repeated value
            out[x : x + count - 128] = raw[at]
            x += count - 128
            at += 1
        else:  # a literal span
            out[x : x + count] = raw[at : at + count]
            x += count
            at += count
    return at


def _rgbe_to_float(rgbe: np.ndarray) -> np.ndarray:
    scale = np.ldexp(1.0, rgbe[..., 3].astype(np.int32) - 136)  # 128 bias + 8 bits
    rgb = rgbe[..., :3].astype(np.float32) * scale[..., None].astype(np.float32)
    return np.where(rgbe[..., 3:4] == 0, 0.0, rgb).astype(np.float32)


def write_hdr(path: Path, rgb: np.ndarray) -> None:
    """Encode linear float RGB back to a Radiance .hdr with RLE scanlines."""
    height, width = rgb.shape[:2]
    rgbe = _float_to_rgbe(rgb)
    out = bytearray(b"#?RADIANCE\nFORMAT=32-bit_rle_rgbe\n\n")
    out += f"-Y {height} +X {width}\n".encode("ascii")
    for y in range(height):
        out += bytes((2, 2, width >> 8, width & 0xFF))
        for plane in range(4):
            out += _encode_plane(rgbe[y, :, plane])
    path.write_bytes(bytes(out))


def _float_to_rgbe(rgb: np.ndarray) -> np.ndarray:
    peak = rgb.max(axis=-1)
    mantissa, exponent = np.frexp(peak)  # peak == mantissa * 2**exponent
    # mantissa * 256 / peak spreads the brightest channel across the full byte
    scale = np.where(peak > 1e-32, mantissa * 256.0 / np.maximum(peak, 1e-32), 0.0)
    rgbe = np.zeros((*rgb.shape[:2], 4), dtype=np.uint8)
    rgbe[..., :3] = np.clip(rgb * scale[..., None], 0, 255).astype(np.uint8)
    rgbe[..., 3] = np.where(peak > 1e-32, np.clip(exponent + 128, 0, 255), 0)
    return rgbe


def _encode_plane(values: np.ndarray) -> bytes:
    """RLE one scanline plane: runs of >=4 as a count byte, the rest literal."""
    out = bytearray()
    x, width = 0, values.shape[0]
    while x < width:
        run = 1
        while x + run < width and values[x + run] == values[x] and run < 127:
            run += 1
        if run >= 4:
            out += bytes((128 + run, int(values[x])))
            x += run
            continue
        span = x
        while span < width and span - x < 128:
            # stop the literal span just before a run worth coding separately
            if span + 3 < width and values[span] == values[span + 1] == values[span + 2] == values[span + 3]:
                break
            span += 1
        out += bytes((span - x,)) + values[x:span].tobytes()
        x = span
    return bytes(out)


def box_downsample(rgb: np.ndarray, factor: int) -> np.ndarray:
    """Average factor x factor blocks. Correct in linear light, which is what
    an HDRI holds, so the softbox keeps its energy instead of dimming."""
    height, width = rgb.shape[:2]
    trimmed = rgb[: height // factor * factor, : width // factor * factor]
    blocks = trimmed.reshape(height // factor, factor, width // factor, factor, 3)
    return blocks.mean(axis=(1, 3)).astype(np.float32)


def optimize_hdr(check: bool) -> list[str]:
    if not HDR_PATH.is_file():
        return [f"skip {HDR_PATH.name}: not found"]
    before = HDR_PATH.stat().st_size
    rgb = read_hdr(HDR_PATH)
    height, width = rgb.shape[:2]
    if width <= HDR_TARGET_WIDTH:
        return [f"skip {HDR_PATH.name}: already {width}x{height}"]
    factor = width // HDR_TARGET_WIDTH
    small = box_downsample(rgb, factor)
    if check:
        return [f"would shrink {HDR_PATH.name} {width}x{height} -> {small.shape[1]}x{small.shape[0]}"]
    write_hdr(HDR_PATH, small)
    after = HDR_PATH.stat().st_size
    # a round trip through the encoder proves the file still parses
    check_rgb = read_hdr(HDR_PATH)
    error = float(np.abs(check_rgb - small).max())
    return [
        f"{HDR_PATH.name}: {width}x{height} -> {small.shape[1]}x{small.shape[0]}, "
        f"{_kb(before)} -> {_kb(after)} ({100 - after * 100 // before}% smaller), "
        f"reencode error {error:.4f}"
    ]


# --------------------------------------------------------------------------
# Product photos
# --------------------------------------------------------------------------


def optimize_jpegs(check: bool) -> list[str]:
    from PIL import Image

    lines = []
    for path in sorted((STATIC / "img").glob("*.jpg")):
        before = path.stat().st_size
        with Image.open(path) as image:
            image = image.convert("RGB")
            width, height = image.size
            if width > JPEG_TARGET_WIDTH:
                height = round(height * JPEG_TARGET_WIDTH / width)
                width = JPEG_TARGET_WIDTH
                image = image.resize((width, height), Image.LANCZOS)
            if check:
                lines.append(f"would re-encode {path.name} -> {width}x{height}")
                continue
            image.save(
                path, "JPEG", quality=JPEG_QUALITY, optimize=True, progressive=True
            )
        after = path.stat().st_size
        lines.append(
            f"{path.name}: {_kb(before)} -> {_kb(after)} "
            f"({100 - after * 100 // before}% smaller), {width}x{height}"
        )
    return lines


def _kb(size: int) -> str:
    return f"{size / 1024:.0f} KB"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check", action="store_true", help="report what would change, write nothing"
    )
    args = parser.parse_args()
    for line in optimize_hdr(args.check) + optimize_jpegs(args.check):
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
