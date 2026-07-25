# Environment lighting

`studio.hdr` — "Photo Studio 01" by Sergej Majboroda, from
[Poly Haven](https://polyhaven.com/a/photo_studio_01), 1k resolution (1.6 MB).

Poly Haven publishes all assets under **CC0**: free, no attribution required, no
account, no API key. Credited here as a courtesy and to record provenance.

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
