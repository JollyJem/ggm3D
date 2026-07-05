"""One-time QR code generation for the catalog header.

Writes app/static/img/qr.png linking to the deployed app, so interviewers
can scan it from a laptop screen and open the demo on their phone.

The qrcode package is NOT a runtime dependency and must stay out of
requirements.txt. Install it only when regenerating the image:

    pip install "qrcode[pil]"
    python scripts/make_qr.py
"""

from pathlib import Path

import qrcode

APP_URL = "https://ggm3d.onrender.com"
OUT = Path(__file__).resolve().parent.parent / "app" / "static" / "img" / "qr.png"


def main() -> None:
    img = qrcode.make(APP_URL, border=2)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    img.save(OUT)
    print(f"{APP_URL} -> {OUT} ({OUT.stat().st_size / 1024:.1f} KB)")


if __name__ == "__main__":
    main()
