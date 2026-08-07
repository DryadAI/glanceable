"""glanceable -- a layout and typography engine for round, glanceable displays."""

from .geometry import CircularDisplay
from .typography import Font, FontLoadError, GlyphRun, Layout, ramp_palette
from .surface import (
    Surface, PILSurface, SpriteSurface, SpriteOp, SpritePayload, SpriteCoords,
)
from .render import render_text, HALO
from .fonts import find_system_font

__version__ = "0.1.0"
__all__ = [
    "CircularDisplay", "Font", "FontLoadError", "GlyphRun", "Layout", "ramp_palette",
    "Surface", "PILSurface", "SpriteSurface", "SpriteOp", "SpritePayload",
    "SpriteCoords", "render_text", "HALO",
    "find_system_font",
]
