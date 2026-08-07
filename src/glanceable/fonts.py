"""Cross-platform font discovery.

Exists because hardcoding an absolute font path is the fastest way to make a
library fail on someone else's machine thirty seconds after they clone it.
Also useful to callers: you should not have to know where your OS keeps its
fonts to render one line of text.
"""

from __future__ import annotations

import os
from pathlib import Path

# Ordered by preference. DejaVu first because it is metrically stable across
# distros and is what the golden tests were tuned against.
CANDIDATES = [
    # Linux
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/TTF/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    # macOS
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/Library/Fonts/Arial.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
    "/System/Library/Fonts/SFNS.ttf",
    # Windows
    r"C:\Windows\Fonts\arial.ttf",
    r"C:\Windows\Fonts\segoeui.ttf",
]


def find_system_font(extra: list[str] | None = None) -> str:
    """Return a path to a usable sans-serif TTF.

    Set GLANCEABLE_FONT to override, which is also how CI pins a specific face
    so golden comparisons stay stable.

    Raises:
        FileNotFoundError: with the list of places searched, rather than
            silently substituting a wrong-sized bitmap font.
    """
    env = os.environ.get("GLANCEABLE_FONT")
    if env and Path(env).is_file():
        return env

    for path in (extra or []) + CANDIDATES:
        if Path(path).is_file():
            return path

    raise FileNotFoundError(
        "No system font found. Set GLANCEABLE_FONT to a .ttf path, or install "
        "DejaVu (Debian/Ubuntu: apt install fonts-dejavu-core). Searched:\n  "
        + "\n  ".join((extra or []) + CANDIDATES)
    )
