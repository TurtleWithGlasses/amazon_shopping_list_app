"""Generate a neutral fallback logo (assets/logos/generic.png) for retailers
without a bundled brand mark. A slate rounded badge with a white shopping-bag
glyph, drawn at 4x and downscaled with LANCZOS for smooth edges.
"""
from pathlib import Path

from PIL import Image, ImageDraw

S = 352           # 4x of the 88px target
PAD = 8
SLATE = (100, 116, 139, 255)   # #64748b
WHITE = (255, 255, 255, 255)

img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
d = ImageDraw.Draw(img)

# rounded badge
d.rounded_rectangle([PAD, PAD, S - PAD, S - PAD], radius=64, fill=SLATE)

# shopping bag body (trapezoid: narrower at top)
cx = S / 2
body_top, body_bot = S * 0.42, S * 0.78
top_half_w, bot_half_w = S * 0.20, S * 0.24
d.polygon(
    [(cx - top_half_w, body_top), (cx + top_half_w, body_top),
     (cx + bot_half_w, body_bot), (cx - bot_half_w, body_bot)],
    fill=WHITE,
)
# bag handle (arc above the body)
hw = S * 0.11
d.arc([cx - hw, body_top - hw * 1.5, cx + hw, body_top + hw * 0.5],
      start=180, end=360, fill=WHITE, width=int(S * 0.035))

out = Path("assets/logos/generic.png")
img.resize((88, 88), Image.LANCZOS).save(out, "PNG")
print("wrote", out, "88x88")
