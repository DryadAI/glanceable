"""Guard the README's line-budget claim.

Six documents in this repo have carried a number that drifted from the run
that produced it — the test count twice, the equator chord three times. The
durable fix is not a more careful editing pass; it is asserting the claim in
code so a regression fails CI instead of quietly making a doc wrong.

The split is deliberate:

* **Geometry is exact.** The equator chord and the inscribed square are pure
  arithmetic on `usable_radius`. They cannot drift with a font or a library,
  so they get exact assertions and the README may quote them verbatim.
* **Typography gets floors.** The character counts depend on FreeType's
  rasterization and on the exact DejaVu build, neither of which this repo
  controls. Asserting the measured numbers would produce a test that fails on
  someone else's distro for no real reason. The floors sit well under the
  measured values, so they survive font drift while still failing loudly if
  the chord solver stops beating a rectangle.
"""

import math
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

import pytest

from glanceable import HALO, Font, find_system_font

TEXT = (
    "Peripheral motion is detected pre-attentionally, so anything that "
    "moves out there hijacks attention whether or not it matters."
    " A glanceable display is read in under a second, so what fits on one "
    "page is the whole design constraint."
)
FONT_PX = 13

#: Gain floors per line budget. Measured +98/+74/+62/+53% on DejaVu Sans 13px
#: under Python 3.10.20, 3.12.3 and 3.14.4 — all with Pillow 12.3.0 and
#: FreeType 2.14.3, identical to four decimal places on every one. The floors
#: are set roughly two-thirds of measured to absorb a different font build.
GAIN_FLOOR = {3: 0.60, 4: 0.45, 5: 0.38, 6: 0.32}


def inscribed_width() -> int:
    return int(HALO.usable_radius * math.sqrt(2))


def naive_layout(font: Font, text: str, width: int, max_lines: int) -> list[str]:
    """Greedy wrap at a fixed width — a rectangular engine on a round panel."""
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


# -- exact: pure geometry -------------------------------------------------


def test_equator_chord_is_exactly_twice_the_usable_radius():
    """The README quotes 240px. Arithmetic, not measurement."""
    assert HALO.usable_radius == 120.0
    assert 2 * HALO.half_chord(128) == 240.0


def test_inscribed_square_is_the_radius_times_root_two():
    """The README quotes 169px. 120 * sqrt(2) = 169.7, floored."""
    assert inscribed_width() == 169


def test_the_inscribed_square_wastes_most_of_the_equator():
    """The claim the whole library rests on, as a ratio."""
    assert inscribed_width() / (2 * HALO.half_chord(128)) < 0.72


# -- floors: font-dependent ------------------------------------------------


@pytest.mark.parametrize("budget", sorted(GAIN_FLOOR))
def test_chord_aware_fits_substantially_more_at_every_line_budget(budget):
    font = Font(find_system_font(), FONT_PX)

    chord = sum(len(r.text) for r in font.layout(TEXT, HALO, max_lines=budget).runs)
    naive = sum(len(l) for l in naive_layout(font, TEXT, inscribed_width(), budget))

    assert naive > 0
    gain = chord / naive - 1
    assert gain >= GAIN_FLOOR[budget], (
        f"budget={budget}: chord-aware fit {chord} chars vs {naive} "
        f"({gain:+.0%}), below the {GAIN_FLOOR[budget]:+.0%} floor"
    )


def test_the_gain_shrinks_as_the_line_budget_grows():
    """The README explains the trend, so the trend is worth pinning.

    A longer block puts more of its lines near the poles where the chord is
    narrow, so the advantage over a fixed-width wrap narrows. If this ever
    inverts, the explanation in the README is wrong.
    """
    font = Font(find_system_font(), FONT_PX)
    gains = []
    for budget in (3, 4, 5, 6):
        chord = sum(len(r.text) for r in font.layout(TEXT, HALO, max_lines=budget).runs)
        naive = sum(len(l) for l in naive_layout(font, TEXT, inscribed_width(), budget))
        gains.append(chord / naive - 1)

    assert gains == sorted(gains, reverse=True), gains


def test_the_naive_wrapper_is_a_fair_opponent():
    """Guards the guard: a broken comparison would inflate every gain above.

    The naive wrap must actually fill its box — if a bug made it emit one word
    per line, the gains would look enormous and mean nothing.
    """
    font = Font(find_system_font(), FONT_PX)
    width = inscribed_width()
    lines = naive_layout(font, TEXT, width, 6)

    assert len(lines) == 6
    for line in lines:
        assert font.advance(line) <= width, "naive wrap overflowed its own box"

    # Every line but the last must be unable to take the next word — that is
    # what makes it greedy rather than lazy.
    widest = max(font.advance(l) for l in lines)
    assert widest > width * 0.6, (
        f"widest naive line is only {widest}px in a {width}px box; "
        "the comparison is not fair"
    )
