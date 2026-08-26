"""Render the same text two ways and measure the difference.

The pitch for `glanceable` in one image: wrapping to the largest inscribed
rectangle is the intuitive move on a round panel, and it throws away the
widest part of the glass. Both panels below use the same font, the same
size, and the same source string. Only the wrap constraint differs.

Nothing here is mocked -- the left panel is `glanceable`'s own layout
engine, and the right panel is a plain greedy wrap at the inscribed-square
width, which is what a rectangular layout engine does when you point it at
a circle.
"""

import math

from PIL import Image, ImageDraw

from glanceable import HALO, Font, PILSurface, find_system_font, ramp_palette, render_text

TEXT = (
    "Peripheral motion is detected pre-attentionally, so anything that "
    "moves out there hijacks attention whether or not it matters."
)
SIZE = 256
LEVELS = 4
FONT_PX = 13


def inscribed_width(display) -> int:
    """Side of the largest axis-aligned square inside the usable circle."""
    return int(display.usable_radius * math.sqrt(2))


def naive_layout(font: Font, text: str, width: int, max_lines: int):
    """Greedy wrap at a fixed width -- a rectangular engine on a round panel."""
    words, lines, current = text.split(), [], ""
    for word in words:
        trial = f"{current} {word}".strip()
        if font.advance(trial) <= width:
            current = trial
        else:
            if current:
                lines.append(current)
            current = word
            if len(lines) == max_lines:
                break
    if current and len(lines) < max_lines:
        lines.append(current)
    leftover = " ".join(words[len(" ".join(lines).split()):])
    return lines[:max_lines], leftover


def draw_circle(img: Image.Image, radius: float, colour=(38, 38, 38)):
    d = ImageDraw.Draw(img)
    c = SIZE / 2
    d.ellipse([c - radius, c - radius, c + radius, c + radius], outline=colour)
    return img


def render_chord_aware(font: Font):
    surface = PILSurface(SIZE, SIZE, ramp_palette(LEVELS))
    layout = render_text(surface, font, TEXT, HALO, max_lines=6, levels=LEVELS)
    return draw_circle(surface.to_rgb(), HALO.usable_radius), layout


def render_naive(font: Font):
    """Same rasterizer, same panel -- only the wrap width differs."""
    width = inscribed_width(HALO)
    lines, leftover = naive_layout(font, TEXT, width, max_lines=6)

    surface = PILSurface(SIZE, SIZE, ramp_palette(LEVELS))
    left = (SIZE - width) // 2
    top = int(HALO.widest_band(font.line_height, len(lines)))

    for i, line in enumerate(lines):
        runs = font.layout(line, HALO, max_lines=1).runs
        if not runs:
            continue
        run = runs[0]
        coverage = font.rasterize(run, LEVELS)
        surface.blit_coverage(coverage, left, top + i * font.line_height, 0, LEVELS)

    img = draw_circle(surface.to_rgb(), HALO.usable_radius)
    d = ImageDraw.Draw(img)
    d.rectangle(
        [left, top, left + width, top + len(lines) * font.line_height],
        outline=(80, 40, 40),
    )
    return img, lines, leftover


def main():
    font = Font(find_system_font(), FONT_PX)

    chord_img, chord_layout = render_chord_aware(font)
    naive_img, naive_lines, naive_leftover = render_naive(font)

    chord_chars = sum(len(r.text) for r in chord_layout.runs)
    naive_chars = sum(len(l) for l in naive_lines)

    equator = 2 * HALO.half_chord(SIZE / 2)
    inscribed = inscribed_width(HALO)

    print(f"equator chord      : {equator:.0f}px")
    print(f"inscribed square   : {inscribed}px  ({inscribed / equator:.0%} of it)")
    print()
    print(f"chord-aware        : {len(chord_layout.runs)} lines, {chord_chars} chars")
    print(f"inscribed rectangle: {len(naive_lines)} lines, {naive_chars} chars")
    print(f"difference         : {chord_chars - naive_chars} more chars "
          f"({chord_chars / naive_chars - 1:+.0%})")
    print(f"leftover (naive)   : {naive_leftover[:60]!r}")

    sheet = Image.new("RGB", (SIZE * 2 + 24, SIZE), (0, 0, 0))
    sheet.paste(chord_img, (0, 0))
    sheet.paste(naive_img, (SIZE + 24, 0))
    sheet.save("/home/claude/comparison.png")
    chord_img.save("/home/claude/chord_aware.png")
    naive_img.save("/home/claude/inscribed.png")
    print("\nwrote comparison.png")


if __name__ == "__main__":
    main()
