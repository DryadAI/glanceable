"""Three-panel comparison. The middle panel is the important one: it gives the
stock path its intended contract (caller pre-wraps and passes \\n) so the
comparison is not a strawman."""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from PIL import Image, ImageDraw, ImageFont

from glanceable import (HALO, Font, PILSurface, find_system_font,
                        ramp_palette, render_text)

FONT = find_system_font()
TEXT = (
    "Peripheral motion is detected pre-attentionally, so anything that moves "
    "out there hijacks attention whether or not it matters."
)
SCALE = 3
SIZE = 13


def _stock_render(text: str) -> Image.Image:
    """Faithful reproduction of TxTextSpriteBlock.create_text_sprites:
    split on newlines only, crop each line to its own ink bbox, hard threshold
    at >127, 2-colour palette. Sprites then placed at uniform line pitch,
    which is all the caller can do -- pack() transmits no per-line origin."""
    scratch = Image.new("RGB", (200, 16 * 8), "black")
    draw = ImageDraw.Draw(scratch)
    font = ImageFont.truetype(FONT, SIZE)

    boxes, y = [], 0
    for line in text.split("\n"):
        bbox = draw.textbbox((0, y), line, font=font)
        if bbox[3] - bbox[1] > 0:
            draw.text((0, y), line, font=font, fill="white")
            boxes.append((bbox[0], bbox[1], bbox[2], bbox[3]))
        y += 16

    out = Image.new("L", (256, 256), 0)
    cy = 128 - (len(boxes) * 16) // 2
    for i, (l, t, r, b) in enumerate(boxes):
        crop = scratch.crop((l, t, r, b)).convert("L")
        crop = crop.point(lambda p: 255 if p > 127 else 0)  # 1-bit threshold
        # Centre if it fits, else left-align at the widest chord so the
        # clipping is visible rather than the whole line landing off-canvas.
        x = 128 - crop.width // 2 if crop.width <= 240 else 12
        out.paste(crop, (x, cy + i * 16))
    return Image.merge("RGB", (out, out, out))


def stock_naive() -> Image.Image:
    """What a caller gets passing a paragraph straight in: no wrap exists."""
    return _stock_render(TEXT)


def stock_prewrapped() -> Image.Image:
    """Stock given its intended contract. Caller wraps to a rectangle -- the
    only thing available, since nothing in the SDK knows the panel is round."""
    font = ImageFont.truetype(FONT, SIZE)
    width, cur, lines = 200, [], []
    for w in TEXT.split():
        if font.getlength(" ".join(cur + [w])) <= width:
            cur.append(w)
        else:
            lines.append(" ".join(cur))
            cur = [w]
    if cur:
        lines.append(" ".join(cur))
    return _stock_render("\n".join(lines))


def ours() -> Image.Image:
    surf = PILSurface(256, 256, ramp_palette(4))
    lay = render_text(surf, Font(FONT, SIZE), TEXT, levels=4, max_lines=6)
    print(f"glanceable: {len(lay)} lines, truncated={lay.truncated}")
    return surf.to_rgb()


def panel(img: Image.Image, label: str, sub: str) -> Image.Image:
    big = img.resize((256 * SCALE, 256 * SCALE), Image.NEAREST)
    mask = Image.new("L", big.size, 0)
    ImageDraw.Draw(mask).ellipse([0, 0, big.size[0] - 1, big.size[1] - 1], fill=255)
    p = Image.new("RGB", big.size, (18, 18, 20))
    p.paste(big, (0, 0), mask)
    d = ImageDraw.Draw(p)
    d.ellipse([0, 0, big.size[0] - 1, big.size[1] - 1], outline=(70, 70, 78), width=3)
    ins = HALO.safe_inset * SCALE
    d.ellipse([ins, ins, big.size[0] - 1 - ins, big.size[1] - 1 - ins],
              outline=(64, 42, 42), width=2)
    cap = ImageFont.truetype(FONT, 21)
    small = ImageFont.truetype(FONT, 16)
    c = Image.new("RGB", (big.size[0], big.size[1] + 74), (10, 10, 12))
    c.paste(p, (0, 0))
    dd = ImageDraw.Draw(c)
    dd.text((big.size[0] // 2, big.size[1] + 24), label, font=cap,
            fill=(214, 214, 220), anchor="mm")
    dd.text((big.size[0] // 2, big.size[1] + 52), sub, font=small,
            fill=(128, 128, 136), anchor="mm")
    return c


panels = [
    panel(stock_naive(), "stock, no newlines", "no word wrap exists"),
    panel(stock_prewrapped(), "stock, caller pre-wrapped", "1-bit - baselines drift - ignores circle"),
    panel(ours(), "glanceable v0.1", "chord-aware - 4-level - baselines locked"),
]
w = sum(p.width for p in panels) + 16 * (len(panels) + 1)
sheet = Image.new("RGB", (w, panels[0].height + 32), (10, 10, 12))
x = 16
for p in panels:
    sheet.paste(p, (x, 16))
    x += p.width + 16
out = pathlib.Path(__file__).resolve().parents[1] / "docs" / "comparison.png"
sheet.save(out)
print("wrote", out, sheet.size)
