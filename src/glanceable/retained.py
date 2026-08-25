"""Retained-mode wrapper for any ``Surface``.

Wraps a surface, buffers the ops for a frame, and on ``present()`` forwards
only what changed since the last frame. Works over ``PILSurface`` and
``LuaSurface`` identically, because it is written against the ABC and knows
nothing about either.

It exists because of two facts that only bite on real hardware:

* **Nothing erases.** ``blit_coverage`` writes ink pixels through a mask, so
  re-rendering a shorter line leaves the tail of the previous line on the
  glass. On ``PILSurface`` you only see this if a test reuses the image; on
  device it is guaranteed.
* **There is no back buffer.** ``display.show()`` is a registered no-op in the
  Halo firmware, so drawing lands in the buffer the panel is scanning out. A
  clear-and-repaint is a full-field luminance transient -- the exact
  pre-attentional motion this library exists to avoid.

The saving is bandwidth, not statements. A 240x18 coverage map at 4 levels is
1,080 bytes; a five-line HUD is 5,400. Repainting one changed line ships 1,080
instead, which is why this wrapper is load-bearing rather than an
optimisation.
"""

from __future__ import annotations

import hashlib

from PIL import Image

from .damage import BlitCoverage, Box, FillRect, Op, plan
from .surface import Surface


class RetainedSurface(Surface):
    """Buffers a frame and forwards only the damaged regions on ``present()``.

    Args:
        inner: the surface actually driving pixels.
        background_index: palette entry to fill damaged regions with before
            redrawing. Must match the background the coverage blits assume --
            entry 0 for ``ramp_palette``.
    """

    def __init__(self, inner: Surface, background_index: int = 0):
        self._inner = inner
        self._background = background_index
        self._pending: list[Op] = []
        self._committed: tuple[Op, ...] | None = None
        self.last_plan = None

    @property
    def size(self) -> tuple[int, int]:
        return self._inner.size

    @property
    def bounds(self) -> Box:
        w, h = self._inner.size
        return Box(0, 0, w, h)

    def invalidate(self) -> None:
        """Forget what is on the panel; the next present repaints everything."""
        self._committed = None

    def fill_rect(self, x: int, y: int, w: int, h: int, color_index: int) -> None:
        if w <= 0 or h <= 0:
            return
        self._pending.append(FillRect(x, y, w, h, color_index))

    def blit_coverage(
        self, coverage: Image.Image, x: int, y: int, palette_base: int, levels: int
    ) -> None:
        digest = hashlib.blake2b(coverage.tobytes(), digest_size=16).digest()
        self._pending.append(
            BlitCoverage(
                x=x,
                y=y,
                w=coverage.width,
                h=coverage.height,
                palette_base=palette_base,
                levels=levels,
                digest=digest,
                image=coverage,
            )
        )

    def present(self) -> None:
        current = tuple(self._pending)
        self._pending.clear()

        damage = plan(self._committed, current, self.bounds)
        self.last_plan = damage

        for region in damage.regions:
            box = region.box.clip(self.bounds)
            if box.is_empty:
                continue
            if region.needs_fill:
                self._inner.fill_rect(box.x, box.y, box.w, box.h, self._background)
            for op in region.ops:
                op.replay(self._inner)

        self._committed = current
        self._inner.present()
