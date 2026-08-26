"""Re-measure the README's line-budget table on one interpreter.

Prints a machine-readable line per budget so the same script can be run under
several interpreters and the outputs diffed. The point is provenance: a figure
in a doc should name the run it came from.
"""

import math
import sys

from PIL import Image, ImageFont
import PIL

from glanceable import HALO, Font, find_system_font

TEXT = (
    "Peripheral motion is detected pre-attentionally, so anything that "
    "moves out there hijacks attention whether or not it matters."
)
LONG = TEXT + (
    " A glanceable display is read in under a second, so what fits on one "
    "page is the whole design constraint."
)
FONT_PX = 13


def inscribed_width(display) -> int:
    return int(display.usable_radius * math.sqrt(2))


def naive_layout(font, text, width, max_lines):
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
    return lines[:max_lines]


def main() -> None:
    face = find_system_font()
    font = Font(face, FONT_PX)
    width = inscribed_width(HALO)

    print(f"# python={sys.version.split()[0]} pillow={PIL.__version__}")
    print(f"# face={face}")
    print(f"# freetype={ImageFont.core.freetype2_version} "
          f"equator={2 * HALO.half_chord(128):.1f} inscribed={width}")

    for budget in (3, 4, 5, 6):
        chord = sum(len(r.text) for r in font.layout(LONG, HALO, max_lines=budget).runs)
        naive = sum(len(l) for l in naive_layout(font, LONG, width, budget))
        print(f"{budget} {chord} {naive} {chord / naive - 1:+.4f}")


if __name__ == "__main__":
    main()
