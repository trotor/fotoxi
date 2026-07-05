"""Generate Fotoxi PWA icons (a colored 3x3 grid mark on a dark background).

Run: python frontend/scripts/generate_icons.py
Outputs PNGs to frontend/public/icons/. Swap these for a real icon anytime.
"""
from pathlib import Path

from PIL import Image, ImageDraw

OUT = Path(__file__).resolve().parent.parent / "public" / "icons"
OUT.mkdir(parents=True, exist_ok=True)

BG = (10, 10, 10, 255)  # #0a0a0a — matches app theme
COLORS = [
    (79, 140, 255), (34, 197, 94), (245, 158, 11),
    (168, 85, 247), (239, 68, 68), (6, 182, 212),
    (234, 179, 8), (59, 130, 246), (16, 185, 129),
]


def draw_icon(size: int, full_bleed: bool, content_scale: float, radius_frac: float = 0.22) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    if full_bleed:
        d.rectangle([0, 0, size, size], fill=BG)
    else:
        d.rounded_rectangle([0, 0, size - 1, size - 1], radius=int(size * radius_frac), fill=BG)

    content = int(size * content_scale)
    off = (size - content) // 2
    gap = max(1, content // 24)
    cell = (content - gap * 2) // 3
    for i, color in enumerate(COLORS):
        row, col = divmod(i, 3)
        x = off + col * (cell + gap)
        y = off + row * (cell + gap)
        d.rounded_rectangle([x, y, x + cell, y + cell], radius=max(2, cell // 6), fill=color + (255,))
    return img


def main() -> None:
    draw_icon(192, full_bleed=False, content_scale=0.66).save(OUT / "icon-192.png")
    draw_icon(512, full_bleed=False, content_scale=0.66).save(OUT / "icon-512.png")
    # Maskable needs full bleed + content inside the ~80% safe zone.
    draw_icon(512, full_bleed=True, content_scale=0.56).save(OUT / "icon-512-maskable.png")
    # Apple touch icon: full bleed, opaque (iOS applies its own corner mask).
    draw_icon(180, full_bleed=True, content_scale=0.66).convert("RGB").save(OUT / "apple-touch-icon-180.png")
    print("icons written to", OUT)


if __name__ == "__main__":
    main()
