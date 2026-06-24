"""Normalize retailer logos for the per-row logo column (roadmap Phase 23).

Drop raw logo images into ``assets/logos/_src/`` named by retailer key
(``amazon.png``, ``n11.png``, ``hepsiburada.png``, ``itopya.png``,
``sinerji.png``, ``incehesap.png``, ``aliexpress.png``, ``generic.png`` — any
common image extension works), then run:

    python scripts/normalize_logos.py

For each source it trims the solid border, scales to a uniform height with
high-quality LANCZOS resampling, and writes ``assets/logos/<key>.png`` as RGBA.
Square brand badges (Amazon, Hepsiburada) stay square; wide wordmarks keep their
aspect ratio. The displayed table cell can scale these down further cleanly.
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageChops

# Retailer keys that map to Product.retailer (see core/scraping adapters).
RETAILERS = [
    "amazon", "n11", "hepsiburada", "itopya", "sinerji", "incehesap",
    "aliexpress", "teknosa", "vatanbilgisayar", "akakce", "mediamarkt",
    "trendyol", "generic",
]
SRC_DIR = Path("assets/logos/_src")
OUT_DIR = Path("assets/logos")
TARGET_H = 88          # stored height (px); ~2x of a ~40px row cell for crispness
MAX_W = 220            # clamp very wide wordmarks
EXTS = (".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp")


def _trim_border(img: Image.Image) -> Image.Image:
    """Crop a uniform solid margin (detected from the top-left pixel)."""
    rgb = img.convert("RGB")
    bg = Image.new("RGB", rgb.size, rgb.getpixel((0, 0)))
    diff = ImageChops.difference(rgb, bg)
    bbox = diff.getbbox()
    return img.crop(bbox) if bbox else img


def _find_src(key: str) -> Path | None:
    for ext in EXTS:
        p = SRC_DIR / f"{key}{ext}"
        if p.exists():
            return p
    return None


def normalize(src: Path, dst: Path) -> tuple[int, int]:
    img = Image.open(src).convert("RGBA")
    img = _trim_border(img)
    w, h = img.size
    scale = TARGET_H / h
    new_w = min(round(w * scale), MAX_W)
    new_h = round(h * (new_w / w)) if new_w == MAX_W else TARGET_H
    img = img.resize((new_w, new_h), Image.LANCZOS)
    dst.parent.mkdir(parents=True, exist_ok=True)
    img.save(dst, "PNG")
    return img.size


def main() -> None:
    done, missing = [], []
    for key in RETAILERS:
        src = _find_src(key)
        if not src:
            missing.append(key)
            continue
        size = normalize(src, OUT_DIR / f"{key}.png")
        done.append(f"  {key:<12} {src.name:<18} -> {size[0]}x{size[1]}")
    if done:
        print("Normalized:")
        print("\n".join(done))
    if missing:
        print("\nMissing source(s) in assets/logos/_src/:")
        print("  " + ", ".join(missing))


if __name__ == "__main__":
    main()
