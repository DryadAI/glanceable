"""Deliberately ugly markdown.

Not a showcase. Every fixture here is something that broke, or would have
broken, an earlier version of the renderer. The point of the corpus is rule 4:
for any of these, everything in the source must end up either on the glass, in
`leftover_source`, or in `metadata` -- never nowhere.
"""

FRONTMATTER = """\
---
title: Chord solver
tags: [halo, round]
aliases:
  - chords
---

# Real heading
Body text.
"""

# The trap: an unterminated `---` is a thematic break, not frontmatter. Eating
# to EOF here would swallow the whole note.
FRONTMATTER_UNTERMINATED = """\
---
This is a paragraph under a thematic break, not frontmatter.
"""

NESTED_CALLOUTS = """\
> [!WARNING] Outer warning
> Body of the outer callout.
>
> > [!NOTE] Inner note
> > Body of the inner one.
> > > deeper still, past the depth cap
"""

# A callout whose *title* is long enough to wrap. The lead line carries the
# "WARNING: " prefix, so its continuation lines are where an uncapped hanging
# indent actually bites.
LONG_CALLOUT_TITLE = """\
> [!WARNING] Using the midpoint chord overestimates the usable width for any
> line box that is not centred on the equator.
"""

DATAVIEW = """\
Before the block.

```dataview
TABLE file.mtime AS "Modified"
FROM #halo
SORT file.mtime DESC
```

After the block.
"""

TABLE_WIDE = """\
| element | treatment | cost | note |
|---|---|---|---|
| tables | records | N lines | lossless |
| code | sub-viewport | none | no reflow |
"""

TABLE_HEADERLESS_RAGGED = """\
| a | b |
|---|---|
| 1 | 2 | 3 |
"""

LONG_URL = (
    "Reference: https://example.com/"
    + "segment/" * 24
    + "index.html?query=1&other=2#fragment and then some trailing prose.\n"
)

LONG_WORD = (
    "Prefix " + "z" * 200 + " suffix.\n"
)

CJK = """\
# 円形ディスプレイ

近眼ディスプレイの可読性は行の垂直位置に依存します。弦の幅は極に近づくほど狭くなるため、
矩形に折り返す既存のレイアウトエンジンはガラスの約三分の一を無駄にします。
"""

EMOJI = """\
Status 🔴 critical, 🟡 degraded, 🟢 nominal — plus a 𝔊 mathematical fraktur G.
"""

TASKS = """\
- [ ] unchecked item
- [x] checked item
- [X] capital checked
- plain bullet
1. ordered one
2. ordered two
"""

DEEP_LIST = """\
- one
  - two
    - three
      - four
        - five
"""

CODE_LONG_LINES = """\
Intro paragraph.

```python
def half_chord(y, radius, safe_inset):
    return math.sqrt((radius - safe_inset) ** 2 - abs(y - radius) ** 2)

x = {"a": 1, "b": 2, "c": 3, "d": 4, "e": 5, "f": 6, "g": 7, "h": 8, "i": 9}
```
"""

WIKILINKS = """\
See [[Geometry]], [[Typography|the type note]], [[Notes#Chord section]],
and an embed ![[Diagram.png]]. Not a link: `[[literal in code]]`.
"""

FOOTNOTES = """\
Claim needing support[^src] and another[^2].

[^src]: Read from brilliant-msg 7.0.0 on PyPI.
[^2]: Measured at 13px on the sample string.
"""

HTML_AND_COMMENTS = """\
Visible text.

<div class="callout">
  <script>alert('should never render')</script>
</div>

Inline <br> break and %%an obsidian comment%% mid-sentence.
"""

IMAGES = """\
![A diagram of the chord solver](assets/chord.png)

Text after the image.
"""

HARD_BREAKS = "First line.  \nSecond line after a hard break.\n"

EMPHASIS = """\
Some **bold**, some _italic_, some ***both***, some ~~struck~~, an
identifier like snake_case_name that must not lose its underscores, and
a**mid**word emphasis.
"""

SETEXT = """\
Setext heading
==============
Body under it.

Second level
------------
More body.
"""

# Joined with blank lines, NOT concatenated. Butting a table directly against
# the list above it means GFM never sees a table at all -- it becomes paragraph
# text full of pipes, and every sweep test that thought it was exercising the
# table path was passing on nothing.
EVERYTHING = "\n\n".join(
    s.strip("\n")
    for s in (
        FRONTMATTER,
        NESTED_CALLOUTS,
        TASKS,
        TABLE_WIDE,
        CODE_LONG_LINES,
        DATAVIEW,
        WIKILINKS,
        FOOTNOTES,
        HTML_AND_COMMENTS,
        IMAGES,
        LONG_URL,
        EMOJI,
        "---",
        DEEP_LIST,
    )
) + "\n"

#: Every fixture, for the sweep tests that must hold on all of them.
ALL = {
    name: value
    for name, value in sorted(globals().items())
    if name.isupper() and name != "ALL" and isinstance(value, str)
}
