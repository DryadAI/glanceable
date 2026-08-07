"""Circular display geometry.

Every text layout engine ever written wraps to a rectangle. Halo's panel is a
256x256 circle, so the usable line width is a function of vertical position:
the chord narrows as you move away from center. Wrapping to the largest
inscribed rectangle wastes ~36% of the glass; wrapping to the bounding box
clips against the curve. This module solves for the actual chord.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class CircularDisplay:
    """Geometry of a round panel.

    Args:
        diameter: panel diameter in pixels (Halo: 256).
        safe_inset: pixels to pull in from the physical edge. The outermost
            ring of a round panel is where lens vignetting and the wearer's
            own eye-box misalignment bite, so glyphs placed there are
            unreliable even though they are technically addressable.
    """

    diameter: int = 256
    safe_inset: int = 8

    @property
    def radius(self) -> float:
        return self.diameter / 2.0

    @property
    def center(self) -> tuple[float, float]:
        return (self.radius, self.radius)

    @property
    def usable_radius(self) -> float:
        return self.radius - self.safe_inset

    def half_chord(self, y: float) -> float:
        """Half-width of the usable circle at scanline `y`. 0.0 outside."""
        dy = abs(y - self.radius)
        if dy >= self.usable_radius:
            return 0.0
        return math.sqrt(self.usable_radius**2 - dy**2)

    def line_width(self, y_top: float, y_bottom: float) -> int:
        """Usable width for a line box spanning [y_top, y_bottom].

        A line box is a rectangle, so it is constrained by whichever of its
        two horizontal edges sits farther from the vertical center -- that is
        the narrower chord. Using the midpoint instead (the intuitive move)
        overestimates and clips descenders against the curve near the poles.
        """
        return int(2 * min(self.half_chord(y_top), self.half_chord(y_bottom)))

    def line_left(self, y_top: float, y_bottom: float) -> int:
        """Left x of a centered line box spanning [y_top, y_bottom]."""
        return int(self.radius - self.line_width(y_top, y_bottom) / 2)

    def widest_band(self, line_height: int, n_lines: int) -> float:
        """y_top for the vertically-centered block of `n_lines`.

        Centering the block on the equator maximises total usable area,
        because chord width is greatest at the center and falls off
        symmetrically.
        """
        block = line_height * n_lines
        return self.radius - block / 2.0

    def fits(self, y_top: float, y_bottom: float, min_width: int = 24) -> bool:
        """Whether a line box is wide enough to hold anything useful."""
        return self.line_width(y_top, y_bottom) >= min_width
