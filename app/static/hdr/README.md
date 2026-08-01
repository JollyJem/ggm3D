# Environment lighting

`studio.hdr` — "Photo Studio 01" by Sergej Majboroda, from
[Poly Haven](https://polyhaven.com/a/photo_studio_01), downloaded at 1k and
stored here downsampled to **256x128 (100 KB, was 1.6 MB)**.

Poly Haven publishes all assets under **CC0**: free, no attribution required, no
account, no API key. Credited here as a courtesy and to record provenance.

**Edited**: the lower hemisphere carries a floor bounce (see below). The file is
no longer bit-identical to the download.

model-viewer uses it as `environment-image` only, never as a skybox, so it lights
the model without appearing behind it. The parametric builders emit
`metallicFactor: 1.0` stainless, which renders **black** with nothing to reflect
— this file is what produces the highlights. Do not remove it.

## Why this HDRI and not a "nicer" one

First attempt was `studio_small_09`, a small dark studio. It looks dramatic on a
still, but it is one bright softbox surrounded by near-black walls, so with
`auto-rotate` the vertical panels swung from silver to almost black as the model
turned. `photo_studio_01` is a white cyclorama: bright and even in every
direction, so the unit stays readable at every angle. For a live demo,
recognisable beats dramatic.

If you swap this file, re-check the model through a full rotation, not just one
frame. 1k is the smallest size Poly Haven offers for either HDRI.

## The floor bounce

The download's lower hemisphere averages 0.11 radiance against 1.0 above: a dark
floor. A vertical panel sees half sky and half floor, so every apron, leg and
door came out mid-grey — while in the GGM catalog photos, shot on a white sweep
that bounces light back up, those same panels are close to white. That gap was
the single largest difference left between the render and the photo.

So the bottom half is lifted toward the horizon colour, ramped from nothing at
the horizon to full at the nadir, never darkening a pixel:

```python
from scripts.optimize_assets import read_hdr, write_hdr
rgb = read_hdr(path); h = rgb.shape[0]
below = np.clip(((np.arange(h) + 0.5) / h - 0.5) / 0.5, 0, 1)
target = rgb[int(h * 0.42):int(h * 0.52)].mean(axis=(0, 1)) * 0.65
write_hdr(path, rgb + below[:, None, None] * np.maximum(0.0, target - rgb))
```

Applied once, to the 256x128 file. It only affects `model-viewer`: in AR the
lighting comes from ARCore's estimate of the actual room, which is exactly why
the material has to hold up on its own (see generator/materials.py).

## Why 256x128 and not the 1k download

1k is 1.6 MB on the wire and decodes to an 8 MB float texture on the phone, on
every product page. `environment-image` is never shown directly — model-viewer
prefilters it into a small roughness-mipped reflection map and throws the
original away — so the detail above ~256 px wide is decoded and discarded.
Downsampled in linear light by `scripts/optimize_assets.py`, which is
energy-preserving: mean radiance is identical to the 1k file, and at the
frequency band the reflections are actually sampled from the two are
bit-identical. The highlights look the same; the download is 94% smaller.

Re-run `python scripts/optimize_assets.py` after dropping in a fresh 1k file.
