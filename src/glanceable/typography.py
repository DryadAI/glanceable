"""Typography with real metrics and chord-aware wrapping.

What the stock SDK path (TxTextSpriteBlock) does today, and why each of these
matters on a 256px round panel:

  * It splits on "\\n" only -- there is no word wrap. `width` merely sizes the
    scratch buffer, so long lines run off the edge.
  * It crops each line to its own ink bbox, so a line of "acemn" and a line of
    "Tphgy" come back as sprites of different heights with no shared origin.
    Baselines do not align. Text visibly bounces between lines.
  * It hard-thresholds at >127, discarding the antialiased coverage PIL just
    computed. At 12px on a high-DPI panel, aliased stems are the single
    largest legibility cost, and Halo supports 16-entry palettes.
  * If the TTF fails to load it falls back to ImageFont.load_default(), which
    ignores font_size entirely -- so the text silently renders at the wrong
    size rather than raising.

This module fixes all four and adds wrapping to the circle rather than to a
rectangle.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterator

from PIL import Image, ImageDraw, ImageFont

from .geometry import CircularDisplay


class FontLoadError(RuntimeError):
    """Raised instead of silently falling back to a wrong-sized bitmap font."""


@dataclass
class GlyphRun:
    """One laid-out line, positioned in display space with a stable baseline."""

    text: str
    x: int
    baseline: int
    width: int


@dataclass
class Layout:
    """Result of laying text out. `leftover` is text that did not fit --
    exposed rather than dropped, so a HUD can show an ellipsis, paginate, or
    shrink instead of silently truncating mid-sentence."""

    runs: list[GlyphRun]
    leftover: str
    font: "Font"

    @property
    def truncated(self) -> bool:
        return bool(self.leftover)

    def __iter__(self):
        return iter(self.runs)

    def __len__(self):
        return len(self.runs)

    def __getitem__(self, i):
        return self.runs[i]


class Font:
    """A TTF at one size, with metrics exposed.

    Metrics are read once from the face rather than measured per-string, so
    every line shares an ascent/descent and therefore a baseline.
    """

    def __init__(self, path: str, size: int, line_gap: float = 0.25):
        try:
            self._font = ImageFont.truetype(path, size)
        except OSError as exc:
            # Deliberately loud. The stock path swallows this and renders at
            # the wrong size, which is far harder to debug than a crash.
            raise FontLoadError(f"could not load {path!r} at {size}px") from exc
        self.path = path
        self.size = size
        self.ascent, self.descent = self._font.getmetrics()
        self.line_height = int((self.ascent + self.descent) * (1 + line_gap))

    def advance(self, text: str) -> int:
        """Horizontal advance in px -- includes side bearings, unlike a bbox."""
        return int(self._font.getlength(text))

    def wrap(
        self,
        text: str,
        width_at: Callable[[int, int], int],
        y_start: int,
        max_lines: int | None = None,
    ) -> tuple[list[tuple[str, int]], str]:
        """Greedy word wrap where available width depends on y.

        Args:
            width_at: callback (y_top, y_bottom) -> usable px. This is the seam
                that makes the engine shape-agnostic: pass a constant for a
                rectangle, CircularDisplay.line_width for a round panel.

        Returns:
            (lines, leftover) where lines is [(text, y_top), ...] and leftover
            is any text that did not fit. Callers must decide what to do with
            leftover; it is never silently discarded.
        """
        lines: list[tuple[str, int]] = []
        y = y_start
        words = text.split()
        cur: list[str] = []

        while words or cur:
            avail = width_at(y, y + self.line_height)
            if avail <= 0:
                break

            if words and self.advance(" ".join(cur + [words[0]])) <= avail:
                cur.append(words.pop(0))
                continue

            if not cur:
                # Single word wider than the chord. Break it rather than
                # overflow -- on a round panel an overflowing word vanishes
                # behind the bezel instead of merely looking bad.
                word = words.pop(0)
                cut = len(word)
                while cut > 1 and self.advance(word[:cut] + "-") > avail:
                    cut -= 1
                if cut > 1:
                    words.insert(0, word[cut:])
                    cur = [word[:cut] + "-"]
                elif self.advance(word[:1]) <= avail:
                    # Emit one glyph and REQUEUE the remainder. Dropping it
                    # here was a silent text-loss bug.
                    if len(word) > 1:
                        words.insert(0, word[1:])
                    cur = [word[:1]]
                else:
                    # Not even one glyph fits. Nothing renderable at this
                    # width; stop rather than emit overflowing ink.
                    words.insert(0, word)
                    break

            lines.append((" ".join(cur), y))
            cur = []
            y += self.line_height
            if max_lines and len(lines) >= max_lines:
                break

        leftover = " ".join(([" ".join(cur)] if cur else []) + words).strip()
        return lines, leftover

    def max_feasible_lines(self, display: CircularDisplay, min_width: int = 24) -> int:
        """How many lines of this font actually fit on the panel.

        Guards the blank-screen failure: a caller asking for more lines than
        the glass can hold used to push the probe origin off-panel, where every
        chord is zero width, and get an empty layout back with no error.
        """
        n = 0
        while True:
            cand = n + 1
            y = display.radius - (self.line_height * cand) / 2.0
            if y < 0 or not display.fits(y, y + self.line_height, min_width):
                return max(n, 1)
            if not display.fits(
                y + self.line_height * (cand - 1),
                y + self.line_height * cand,
                min_width,
            ):
                return max(n, 1)
            n = cand
            if n > 64:
                return n

    def layout(
        self,
        text: str,
        display: CircularDisplay,
        max_lines: int = 5,
        center_block: bool = True,
    ) -> "Layout":
        """Wrap `text` to the circle and return positioned runs.

        `max_lines` is a ceiling, not a demand: it is clamped to what the panel
        can physically hold. Anything that does not fit comes back in
        Layout.leftover rather than disappearing.
        """
        cap = min(max_lines, self.max_feasible_lines(display))
        y = int(display.radius - (self.line_height * cap) / 2)
        y = max(0, y)
        lines, leftover = self.wrap(text, display.line_width, y, cap)
        if not lines:
            return Layout([], text, self)

        if center_block:
            # Re-centring for N lines can change N, because chord width varies
            # with y -- and the change can oscillate (5 -> 6 -> 5), so
            # iterating to a fixed point does not terminate. Search instead:
            # find a line count that is self-consistent, i.e. wrapping at the
            # y that centres N lines actually produces N lines. Prefer the
            # smallest such N that consumes all the text (tightest, best
            # centred); otherwise the largest self-consistent N (most text).
            best_complete = None
            best_partial = None
            for n in range(1, cap + 1):
                y_n = max(0, int(display.widest_band(self.line_height, n)))
                cand, cand_left = self.wrap(text, display.line_width, y_n, n)
                if len(cand) != n:
                    continue
                if not cand_left and best_complete is None:
                    best_complete = (cand, cand_left, y_n)
                    break
                best_partial = (cand, cand_left, y_n)
            chosen = best_complete or best_partial
            if chosen:
                lines, leftover, y = chosen

        runs: list[GlyphRun] = []
        for line, y_top in lines:
            w = self.advance(line)
            avail = display.line_width(y_top, y_top + self.line_height)
            left = display.line_left(y_top, y_top + self.line_height)
            x = int(display.radius - w / 2)
            runs.append(
                GlyphRun(text=line, x=max(x, left), baseline=y_top + self.ascent,
                         width=min(w, avail))
            )
        return Layout(runs, leftover, self)

    def rasterize(self, run: GlyphRun, levels: int) -> Image.Image:
        """Render one run to an L-mode coverage map, quantized to `levels`.

        Coverage is preserved rather than thresholded. With levels=4 this
        costs 4 palette entries out of Halo's 16 and buys back the stem
        definition that 1-bit rendering destroys.
        """
        img = Image.new("L", (max(run.width, 1), self.line_height), 0)
        draw = ImageDraw.Draw(img)
        draw.text((0, self.ascent), run.text, font=self._font, fill=255, anchor="ls")
        if levels >= 256:
            return img
        step = 255 / (levels - 1)
        return img.point(lambda p: int(round(p / step) * step))


def ramp_palette(levels: int, fg: tuple[int, int, int] = (255, 255, 255)) -> list[int]:
    """A black->fg ramp, flattened RGB, for TxSprite palette_data."""
    out: list[int] = []
    for i in range(levels):
        t = i / (levels - 1)
        out.extend(int(c * t) for c in fg)
    return out
