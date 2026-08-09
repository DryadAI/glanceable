"""Markdown -> circular display. Device-agnostic; sits above `surface.py`.

Markdown assumes a wide rectangular viewport and rich typography. A 256px
circle at a legible near-eye size gives roughly five to seven usable lines, and
the first and last of them are chord-narrowed to a fraction of the equator. So
most markdown syntax must *degrade*, not render.

Two rules from CLAUDE.md drive every decision here:

  * Rule 4, never silently drop text. Anything not rendered is either in
    `MarkdownLayout.leftover_source` (it did not fit yet) or in
    `MarkdownLayout.metadata` (it was deliberately degraded). There is no third
    outcome. Even a glyph the loaded face cannot draw -- which PIL renders as an
    invisible .notdef rather than raising -- is reported in
    `Metadata.unrenderable`.
  * Rule 2, no animation. Pagination is a discrete, caller-driven index. There
    is no cursor, no scroll, no auto-advance. `layout_markdown(src, ..., page=n)`
    is a pure function; asking for page 3 re-flows pages 0-2 to find where it
    starts, which is the honest price of having no hidden state.

Frontmatter deserves a specific warning, because getting it wrong is silent.
CommonMark does not know what frontmatter is: it reads a leading

    ---
    title: Notes
    ---

as a thematic break followed by a *setext H2* whose text is "title: Notes".
Feed raw source to any CommonMark parser and your frontmatter renders as a
heading. It is therefore stripped before the parser sees it, in
`_strip_frontmatter`, which blanks the lines rather than deleting them so that
every `token.map` still indexes the original source.

Known limitations, stated rather than hidden:

  * Latin-oriented. Line filling breaks on whitespace, so a CJK run with no
    spaces is treated as one long word and hyphen-broken -- text is conserved,
    but the break points are wrong for the script. No BiDi, no shaping.
  * Left-aligned blocks (lists, tables, quotes) use each line's own chord, so
    their left edge is ragged where the chord changes fastest, near the poles.
    Code blocks do not have this problem; they get a rectangular sub-viewport.
    Whether the ragged edge is acceptable is a hardware question and there is no
    hardware yet.
  * `frontmatter` is a flat best-effort scan, NOT a YAML parse. See `Metadata`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, replace
from typing import Iterator, Mapping, Sequence

from .geometry import CircularDisplay
from .surface import Surface
from .typography import Font, GlyphRun


class MarkdownDependencyError(ImportError):
    """Raised when the optional parser is missing.

    Loud, per rule 5. `glanceable` core depends only on Pillow; the markdown
    layer needs a CommonMark parser, which is an optional extra.
    """


# --- policy -----------------------------------------------------------------


@dataclass(frozen=True)
class Policy:
    """Every degradation knob, in one place.

    Defaults are the ones argued for in review. They are collected here so that
    disagreeing with one later is a keyword argument rather than a refactor.
    """

    #: "records" renders each table row as one `header: cell` line per column.
    #: Lossless at any column count, and degenerates to plain `key: value` for
    #: the two-column case. "omit" replaces the table with a stated token and
    #: records its shape in metadata -- cheaper, but it drops content.
    table: str = "records"

    #: Indent levels beyond this are clamped, not dropped; the text still
    #: renders, it just stops moving right. Three levels at `indent_px` already
    #: costs a tenth of the equator chord.
    max_list_depth: int = 3
    indent_px: int = 10

    #: A grid line narrower than this holds a word or two and reads as noise.
    #: `Font.max_feasible_lines` defaults to 24px -- about four characters --
    #: which is far too permissive once a block also carries an indent and a
    #: bullet. Measured at 13px on a 256px panel, 96px is ~13 characters.
    min_line_width: int = 96

    #: Bare URLs longer than this are elided to host + ellipsis. An unelided
    #: 200-character URL is one unbreakable token: it hyphenates into several
    #: lines of noise and consumes the entire display. The full target is
    #: always kept in `Metadata.links`.
    url_elide_over: int = 32

    #: Fence languages whose bodies are opaque programs, not prose. Dropped
    #: with a metadata note rather than rendered as broken source.
    opaque_fences: frozenset[str] = frozenset(
        {"dataview", "dataviewjs", "query", "mermaid", "chart", "tasks"}
    )

    #: Markers. Each is a (preferred, ascii_fallback) pair; the preferred form
    #: is used only if the loaded face actually has the glyph. A missing glyph
    #: is drawn by PIL as an invisible .notdef, so an unchecked box would
    #: vanish without raising -- exactly the silent loss rule 4 forbids.
    bullet: tuple[str, str] = ("• ", "- ")
    heading_prefix: tuple[str, str] = ("▸ ", "* ")
    quote_prefix: tuple[str, str] = ("│ ", "| ")
    rule_char: tuple[str, str] = ("─", "-")
    code_continuation: tuple[str, str] = ("↳", "\\")
    ellipsis: tuple[str, str] = ("…", "...")
    checked: str = "[x] "
    unchecked: str = "[ ] "

    #: Fraction of the available chord a thematic break spans.
    rule_fraction: float = 0.55

    #: Ceiling on hanging indent. Continuation lines normally align under the
    #: text after the marker, but a callout label like "WARNING: " is ~60px --
    #: a quarter of the equator chord -- and aligning to it starves the body.
    #: Beyond this the continuation is merely indented, not aligned.
    hang_max_px: int = 24


# --- metadata ---------------------------------------------------------------


@dataclass(frozen=True)
class Wikilink:
    """`[[Target]]`, `[[Target|alias]]`, or `[[Target#heading]]`.

    The only Obsidian-flavoured construct allowed into this module, and only
    because it is cheap and CommonMark-adjacent. `display` is what actually
    reached the glass; `target` is for a caller to act on.
    """

    target: str
    alias: str | None
    display: str
    line: int
    embed: bool = False


@dataclass(frozen=True)
class Link:
    """A standard `[text](href)`, or a bare URL found in running text."""

    text: str
    href: str
    line: int
    elided: bool = False


@dataclass(frozen=True)
class Dropped:
    """Something deliberately not rendered. `kind` is a stable slug.

    `detail` is COMPLETE, not a preview. Truncating it to a readable length was
    tempting and wrong: an opaque `dataview` block whose metadata note stops at
    60 characters has silently lost the rest, which is the whole failure rule 4
    forbids. Notes are small; keep the text.
    """

    kind: str
    detail: str
    line: int


@dataclass(frozen=True)
class Metadata:
    """Everything that did not reach the glass, and why.

    `frontmatter` is a FLAT BEST-EFFORT SCAN, NOT A YAML PARSE. It picks up
    top-level `key: value` lines and leaves the value as the literal string, so
    `tags: [a, b]` arrives as the five-character string "[a, b]". Nested maps
    and block scalars are not interpreted. `frontmatter_raw` is always the
    verbatim block, which is what a caller wanting real YAML should parse.

    Every field is document-scoped except `unrenderable`, which can only be
    known once a face is chosen and lines are placed, so it describes the page
    it came back on. Union them across pages for a whole-document view.
    """

    frontmatter_raw: str = ""
    frontmatter: Mapping[str, str] = field(default_factory=dict)
    wikilinks: tuple[Wikilink, ...] = ()
    links: tuple[Link, ...] = ()
    footnotes: Mapping[str, str] = field(default_factory=dict)
    dropped: tuple[Dropped, ...] = ()
    reformatted: tuple[str, ...] = ()
    unrenderable: tuple[str, ...] = ()


class _Sink:
    """Mutable accumulator; frozen into `Metadata` at the end of parsing."""

    def __init__(self) -> None:
        self.wikilinks: list[Wikilink] = []
        self.links: list[Link] = []
        self.footnotes: dict[str, str] = {}
        self.dropped: list[Dropped] = []
        self.reformatted: list[str] = []

    def freeze(self, raw: str, front: Mapping[str, str]) -> Metadata:
        return Metadata(
            frontmatter_raw=raw,
            frontmatter=dict(front),
            wikilinks=tuple(self.wikilinks),
            links=tuple(self.links),
            footnotes=dict(self.footnotes),
            dropped=tuple(self.dropped),
            reformatted=tuple(self.reformatted),
        )


# --- blocks -----------------------------------------------------------------

#: Block kinds. `text` blocks reflow; `code` blocks never do.
HEADING, PARAGRAPH, LIST, QUOTE, TABLE, CODE, RULE = (
    "heading", "paragraph", "list", "quote", "table", "code", "rule",
)
_LEFT_ALIGNED = frozenset({LIST, TABLE, QUOTE, CODE})


@dataclass(frozen=True)
class Block:
    """One paginatable unit.

    `text` reflows and may contain "\\n" for authored hard breaks. `lines` is
    verbatim and belongs to code only. `prefix` renders as part of the block's
    first line and its width becomes the hanging indent for continuations.
    `source` is the half-open `[start, end)` line range in the original source,
    from the parser's own source map, which is what makes `leftover_source` a
    real slice rather than a re-serialization.
    """

    kind: str
    text: str = ""
    lines: tuple[str, ...] = ()
    level: int = 0
    prefix: str = ""
    info: str = ""
    source: tuple[int, int] = (0, 0)


@dataclass(frozen=True)
class MarkdownDoc:
    """Parsed source. Immutable, and independent of any font or display.

    Splitting parse from layout means pagination can be a pure function without
    re-parsing on every page, and means `parse_markdown` is testable with no
    font installed.
    """

    blocks: tuple[Block, ...]
    metadata: Metadata
    source: str
    source_lines: tuple[str, ...]


# --- inline scrubbing -------------------------------------------------------

_WIKILINK = re.compile(r"(!?)\[\[([^\[\]|]+?)(?:\|([^\[\]]*?))?\]\]")
_FOOTNOTE_REF = re.compile(r"\[\^([^\]\s]+)\]")
_FOOTNOTE_DEF = re.compile(r"^\[\^([^\]\s]+)\]:\s*(.*)$", re.S)
_COMMENT = re.compile(r"%%.*?%%", re.S)
_BARE_URL = re.compile(r"(?:https?|ftp)://[^\s<>\"')\]]+")
_CALLOUT = re.compile(r"^\[!([A-Za-z][\w-]*)\]([+-]?)\s*(.*)$", re.S)
_TASK = re.compile(r"^\[([ xX])\]\s+(.*)$", re.S)
_HOST = re.compile(r"^[a-z][a-z0-9+.-]*://([^/\s]+)", re.I)


def _elide(url: str, ell: str) -> str:
    m = _HOST.match(url)
    return (m.group(1) if m else url) + ell


def _scrub(text: str, sink: _Sink, policy: Policy, line: int, ell: str) -> str:
    """Rewrite one plain-text run, routing degraded constructs to metadata.

    Only ever called on `text` tokens. Code spans arrive as `code_inline` and
    never reach here, so `` `[[not a link]]` `` is correctly left alone -- a
    property that falls out of using a real parser and would have to be
    hand-built with a regex-only approach.
    """
    def _comment(m: re.Match[str]) -> str:
        sink.dropped.append(Dropped("comment", m.group(0), line))
        return ""

    text = _COMMENT.sub(_comment, text)

    def _wiki(m: re.Match[str]) -> str:
        bang, target, alias = m.group(1), m.group(2).strip(), m.group(3)
        if bang:
            sink.dropped.append(Dropped("embed", target, line))
            sink.wikilinks.append(Wikilink(target, alias, "", line, embed=True))
            return ""
        shown = (alias if alias else target.split("#")[-1] or target).strip()
        sink.wikilinks.append(Wikilink(target, alias, shown, line))
        return shown

    text = _WIKILINK.sub(_wiki, text)

    def _fn(m: re.Match[str]) -> str:
        sink.dropped.append(Dropped("footnote-ref", m.group(1), line))
        return ""

    text = _FOOTNOTE_REF.sub(_fn, text)

    def _url(m: re.Match[str]) -> str:
        url = m.group(0)
        if len(url) <= policy.url_elide_over:
            sink.links.append(Link(url, url, line))
            return url
        sink.links.append(Link(_elide(url, ell), url, line, elided=True))
        return _elide(url, ell)

    return _BARE_URL.sub(_url, text)


#: Softbreak sentinel. A source newline inside a paragraph is not a rendered
#: break -- the text reflows across it -- but some constructs are defined
#: line-wise (a callout's title is the rest of ITS line; each footnote
#: definition owns one line). Marking softbreaks distinctly lets those be split
#: correctly and then collapsed to spaces, instead of guessing after the fact.
SOFT = "\x00"


def _flatten_inline(tok, sink: _Sink, policy: Policy, ell: str) -> str:
    """Collapse an inline token tree to display text.

    Softbreaks come back as `SOFT` and authored hard breaks as "\\n"; callers
    that do not care about line structure call `_collapse`.

    Emphasis markup is dropped and its text kept: `Font` is a single TTF at a
    single size with no style axis, so there is no bold or italic to collapse
    *to*. Nothing is lost that we could have rendered.
    """
    line = (tok.map or (0, 0))[0]
    out: list[str] = []
    link_start: int | None = None
    href = ""

    for ch in tok.children or []:
        t = ch.type
        if t == "text":
            out.append(_scrub(ch.content, sink, policy, line, ell))
        elif t == "code_inline":
            out.append(ch.content)
        elif t == "softbreak":
            out.append(SOFT)
        elif t == "hardbreak":
            out.append("\n")
        elif t == "image":
            alt = (ch.content or "").strip()
            src = ch.attrGet("src") or ""
            sink.dropped.append(
                Dropped("image", f"{alt} -> {src}" if alt else src, line)
            )
        elif t == "link_open":
            href = ch.attrGet("href") or ""
            link_start = len(out)
        elif t == "link_close" and link_start is not None:
            shown = "".join(out[link_start:]).strip()
            del out[link_start:]
            bare = not shown or shown == href or shown == href.rstrip("/")
            if bare and len(href) > policy.url_elide_over:
                shown = _elide(href, ell)
                sink.links.append(Link(shown, href, line, elided=True))
            else:
                sink.links.append(Link(shown, href, line))
            out.append(shown)
            link_start, href = None, ""
        elif t in ("html_inline",):
            sink.dropped.append(Dropped("html", ch.content, line))
        # strong/em/s open+close carry no text of their own: dropping the
        # token keeps the children, which is exactly the wanted degradation.

    return "".join(out)


def _collapse(text: str) -> str:
    """Softbreaks back to spaces, once any line-wise splitting is done."""
    return text.replace(SOFT, " ")


# --- parsing ----------------------------------------------------------------

_FM_OPEN = re.compile(r"^---\s*$")
_FM_CLOSE = re.compile(r"^(?:---|\.\.\.)\s*$")


def _strip_frontmatter(source: str) -> tuple[str, str, str]:
    """Return (body_with_blanked_frontmatter, raw_block, ...).

    The frontmatter lines are replaced with empty lines instead of removed, so
    every source-map line number the parser produces still indexes the original
    text. An unterminated `---` is NOT frontmatter -- it is a thematic break,
    and treating it as frontmatter would eat the whole note.
    """
    lines = source.split("\n")
    if not lines or not _FM_OPEN.match(lines[0]):
        return source, "", source
    for i in range(1, len(lines)):
        if _FM_CLOSE.match(lines[i]):
            raw = "\n".join(lines[1:i])
            body = [""] * (i + 1) + lines[i + 1:]
            return "\n".join(body), raw, source
    return source, "", source


def _flat_frontmatter(raw: str) -> dict[str, str]:
    """Top-level `key: value` only. NOT a YAML parse -- see `Metadata`."""
    out: dict[str, str] = {}
    for ln in raw.split("\n"):
        if not ln or ln[0].isspace() or ln.lstrip().startswith("#"):
            continue
        key, sep, val = ln.partition(":")
        if sep and key.strip() and " " not in key.strip():
            out[key.strip()] = val.strip()
    return out


def _parser(policy: Policy):
    try:
        from markdown_it import MarkdownIt
    except ImportError as exc:  # pragma: no cover - exercised by a skip test
        raise MarkdownDependencyError(
            "glanceable.markdown needs a CommonMark parser. Install it with "
            "`pip install 'glanceable[markdown]'` (adds markdown-it-py, pure "
            "Python, one small dependency)."
        ) from exc
    return MarkdownIt("commonmark").enable("table").enable("strikethrough")


def _report_lost_table_cells(src_lines, span, headers, sink: _Sink) -> None:
    """GFM truncates a row to the header count, before we ever see the tokens.

    The excess cells are gone from the token stream, so the only way to honour
    rule 4 is to count them in the source and name them in metadata. Splitting
    on "|" is crude -- it miscounts escaped pipes and pipes inside code spans --
    so this only ever ADDS a metadata note and never changes what renders.
    """
    if not headers:
        return
    start, end = span
    for n, raw in enumerate(src_lines[start:end], start=start):
        line = raw.strip()
        if not line.startswith("|") or set(line) <= set("|-: "):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) > len(headers):
            extra = ", ".join(cells[len(headers):])
            sink.dropped.append(
                Dropped("table-cell", f"row at line {n + 1}: {extra}", n)
            )


def _table_records(tokens, i: int, sink: _Sink, policy: Policy, ell: str, src_lines):
    """Expand a table into record blocks. Returns (blocks, next_index).

    Both obvious degradations are wrong. "Table omitted" throws away what is
    often the note's entire payload. `key: value` is lossless only at two
    columns and silently discards the third onward, which is precisely the
    failure rule 4 exists to prevent. Emitting one `header: cell` line per
    column per row keeps every cell, costs N lines per row, and paginates like
    anything else. At two columns it *is* `key: value`.
    """
    start = (tokens[i].map or (0, 0))[0]
    end = start + 1
    headers: list[str] = []
    rows: list[list[str]] = []
    cur: list[str] | None = None
    in_head = False
    depth = 0

    while i < len(tokens):
        t = tokens[i]
        if t.map:
            end = max(end, t.map[1])
        if t.type == "table_open":
            depth += 1
        elif t.type == "table_close":
            depth -= 1
            if depth == 0:
                i += 1
                break
        elif t.type == "thead_open":
            in_head = True
        elif t.type == "thead_close":
            in_head = False
        elif t.type == "tr_open":
            cur = []
        elif t.type == "tr_close":
            if cur is not None:
                (headers.extend(cur) if in_head and not headers else rows.append(cur))
            cur = None
        elif t.type == "inline" and cur is not None:
            cur.append(_collapse(_flatten_inline(t, sink, policy, ell)).strip())
        i += 1

    span = (start, end)
    _report_lost_table_cells(src_lines, span, headers, sink)
    if policy.table == "omit":
        sink.dropped.append(
            Dropped("table", f"{len(rows)} rows x {len(headers) or '?'} cols", start)
        )
        return [Block(PARAGRAPH, text="[table omitted]", source=span)], i

    sink.reformatted.append(
        f"table at line {start + 1} rendered as {len(rows)} records "
        f"x {len(headers) or (len(rows[0]) if rows else 0)} fields"
    )
    blocks: list[Block] = []
    for r, row in enumerate(rows):
        for c, cell in enumerate(row):
            if headers and c < len(headers):
                text = f"{headers[c]}: {cell}"
            elif headers:
                # More cells than headers: keep the cell, name it by position
                # rather than drop it.
                text = f"col{c + 1}: {cell}"
            else:
                text = cell
            blocks.append(Block(TABLE, text=text, source=span))
    if not blocks:
        sink.dropped.append(Dropped("table", "no body rows", start))
    return blocks, i


def parse_markdown(source: str, policy: Policy = Policy()) -> MarkdownDoc:
    """Source -> blocks + metadata. Pure; needs no font and no display."""
    # The ASCII ellipsis, unconditionally: `parse_markdown` takes no font, and
    # keeping it font-independent is what lets the same MarkdownDoc be laid out
    # against several faces. "..." is safe on every face.
    ell = policy.ellipsis[1]
    body, raw_fm, original = _strip_frontmatter(source)
    sink = _Sink()
    tokens = _parser(policy).parse(body)

    blocks: list[Block] = []
    list_stack: list[dict] = []
    quote_depth = 0
    pending: str | None = None  # bullet marker awaiting its first paragraph
    i = 0

    while i < len(tokens):
        t = tokens[i]
        kind = t.type
        span = tuple(t.map) if t.map else (0, 0)

        if kind == "heading_open":
            level = int(t.tag[1]) if t.tag[1:].isdigit() else 1
            inline = tokens[i + 1]
            blocks.append(
                Block(HEADING,
                      text=_collapse(_flatten_inline(inline, sink, policy, ell)),
                      level=level, source=span)
            )
            i += 3
            continue

        if kind in ("bullet_list_open", "ordered_list_open"):
            start = t.attrGet("start")
            list_stack.append(
                {"ordered": kind[0] == "o", "n": int(start) if start else 1}
            )
            i += 1
            continue

        if kind in ("bullet_list_close", "ordered_list_close"):
            if list_stack:
                list_stack.pop()
            i += 1
            continue

        if kind == "list_item_open":
            lst = list_stack[-1] if list_stack else {"ordered": False, "n": 1}
            if lst["ordered"]:
                pending = f"{lst['n']}. "
                lst["n"] += 1
            else:
                pending = policy.bullet[0]
            i += 1
            continue

        if kind == "blockquote_open":
            quote_depth += 1
            i += 1
            continue

        if kind == "blockquote_close":
            quote_depth = max(0, quote_depth - 1)
            i += 1
            continue

        if kind == "paragraph_open":
            inline = tokens[i + 1]
            i += 3
            # Footnote definitions are tested on the RAW content, because
            # `_scrub` strips `[^1]` as a reference and would leave a
            # definition looking like a paragraph that begins ": ". They also
            # have to be split per line: consecutive definitions are one
            # CommonMark paragraph, so matching with DOTALL swallows every
            # definition after the first into the first one's body.
            kept, defs = _split_footnote_defs((inline.content or ""))
            for label, bodytext in defs:
                sink.footnotes[label] = bodytext
                sink.dropped.append(Dropped("footnote-def", label, span[0]))
            if defs and not kept.strip():
                pending = None
                continue
            text = _flatten_inline(inline, sink, policy, ell)
            blocks.extend(
                _text_block(text, pending, list_stack, quote_depth, policy, span)
            )
            pending = None
            continue

        if kind in ("fence", "code_block"):
            info = (t.info or "").strip().split()[0].lower() if t.info else ""
            if info in policy.opaque_fences:
                sink.dropped.append(
                    Dropped("opaque-fence", f"{info}: {t.content}", span[0])
                )
                i += 1
                continue
            if info:
                # The body renders; the language does not. It is still
                # something the author wrote, so it is named rather than lost.
                sink.dropped.append(Dropped("fence-info", info, span[0]))
            body_lines = t.content.split("\n")
            while body_lines and not body_lines[-1].strip():
                body_lines.pop()
            blocks.append(
                Block(CODE, lines=tuple(body_lines), info=info, source=span)
            )
            i += 1
            continue

        if kind == "html_block":
            # Stripping tags would happily render the body of a <script>.
            # Opaque is the safe reading.
            sink.dropped.append(Dropped("html", t.content.strip(), span[0]))
            i += 1
            continue

        if kind == "hr":
            blocks.append(Block(RULE, source=span))
            i += 1
            continue

        if kind == "table_open":
            made, i = _table_records(
                tokens, i, sink, policy, ell, original.split("\n")
            )
            blocks.extend(made)
            continue

        i += 1

    return MarkdownDoc(
        blocks=tuple(blocks),
        metadata=sink.freeze(raw_fm, _flat_frontmatter(raw_fm)),
        source=original,
        source_lines=tuple(original.split("\n")),
    )


def _split_footnote_defs(raw: str) -> tuple[str, list[tuple[str, str]]]:
    """Peel `[^label]: body` lines off a paragraph. -> (kept_text, defs).

    Consecutive definitions are a single CommonMark paragraph joined by
    softbreaks, so they must be separated line-wise. A definition's body runs
    until the next line that opens a new definition.
    """
    lines = raw.split("\n")
    defs: list[tuple[str, str]] = []
    kept: list[str] = []
    cur: list[str] | None = None
    label = ""
    for ln in lines:
        m = _FOOTNOTE_DEF.match(ln.strip())
        if m:
            if cur is not None:
                defs.append((label, " ".join(cur).strip()))
            label, cur = m.group(1), [m.group(2)]
        elif cur is not None:
            cur.append(ln.strip())
        else:
            kept.append(ln)
    if cur is not None:
        defs.append((label, " ".join(cur).strip()))
    return "\n".join(kept), defs


def _text_block(text, pending, list_stack, quote_depth, policy, span) -> list[Block]:
    """Classify a flowed paragraph by the containers it sits inside.

    Returns a list because a callout splits in two: the `[!TYPE] Title` line
    collapses to a prefixed lead line, and whatever follows it inside the same
    blockquote paragraph is the body. That split is line-wise, which is why
    softbreaks survive as `SOFT` until here.
    """
    if pending is not None:
        depth = max(0, len(list_stack) - 1)
        flat = _collapse(text)
        task = _TASK.match(flat)
        if task:
            mark = policy.checked if task.group(1) in "xX" else policy.unchecked
            return [Block(LIST, text=task.group(2), level=depth, prefix=mark,
                          source=span)]
        return [Block(LIST, text=flat, level=depth, prefix=pending, source=span)]

    if quote_depth:
        head, _, rest = text.partition(SOFT)
        head = head.partition("\n")[0]
        call = _CALLOUT.match(head)
        if call:
            label = call.group(1).upper()
            title = call.group(3).strip()
            tail = _collapse(rest).strip()
            lead = Block(QUOTE, text=title or label, level=quote_depth - 1,
                         prefix=f"{label}: " if title else "", source=span)
            if not tail:
                return [lead]
            # The body carries the quote marker, same as a plain blockquote.
            # It ties the body visually to its label, and it is the only form
            # that survives a `leftover_source` round trip -- there is no
            # markdown for "blockquote continuation with no marker", so a
            # bare body would come back as a centred paragraph.
            return [lead, Block(QUOTE, text=tail, level=quote_depth - 1,
                                prefix=policy.quote_prefix[0], source=span)]
        return [Block(QUOTE, text=_collapse(text), level=quote_depth - 1,
                      prefix=policy.quote_prefix[0], source=span)]

    return [Block(PARAGRAPH, text=_collapse(text), source=span)]


# --- glyph coverage ---------------------------------------------------------

_MISSING_PROBE = "\uE0FF"  # private use area; no sane face maps this
_COVERAGE_CACHE: dict[tuple[str, int, str], bool] = {}


def _notdef_signature(font: Font) -> tuple[int, bytes]:
    run = GlyphRun(_MISSING_PROBE, 0, 0, max(font.advance(_MISSING_PROBE), 1))
    img = font.rasterize(run, 256)
    return img.width, img.tobytes()


def has_glyph(font: Font, ch: str) -> bool:
    """Whether `font` can actually draw `ch`.

    PIL draws a character the face does not cover as .notdef -- frequently an
    invisible zero-ink box -- and raises nothing. A checkbox or bullet chosen
    without this check disappears on any face that lacks it, which is silent
    loss through a path `Layout.leftover` does not cover.
    """
    if not ch or ch.isspace():
        return True
    key = (font.path, font.size, ch)
    hit = _COVERAGE_CACHE.get(key)
    if hit is not None:
        return hit
    adv = font.advance(ch)
    if adv <= 0:
        _COVERAGE_CACHE[key] = False
        return False
    img = font.rasterize(GlyphRun(ch, 0, 0, max(adv, 1)), 256)
    w, sig = _notdef_signature(font)
    ok = not (img.width == w and img.tobytes() == sig)
    _COVERAGE_CACHE[key] = ok
    return ok


def _pick(font: Font, pair: tuple[str, str]) -> str:
    """Preferred marker if the face has every glyph in it, else the fallback."""
    return pair[0] if all(has_glyph(font, c) for c in pair[0]) else pair[1]


# --- line filling -----------------------------------------------------------


def _fill(words: list[str], avail: int, font: Font) -> tuple[str, list[str]]:
    """Greedily take words for one line of `avail` px. Never drops a word.

    Mirrors `Font.wrap`'s inner loop, including both bugs it has already had
    fixed: an over-long word is hyphenated and its remainder RE-QUEUED, and when
    not even one glyph fits the word is put back untouched so the caller can
    stop rather than emit nothing and lose it. `Font.wrap` cannot be reused
    directly because it owns its own y advance and knows nothing about per-line
    prefixes or hanging indents.
    """
    if avail <= 0 or not words:
        return "", words
    cur: list[str] = []
    while words:
        cand = " ".join(cur + [words[0]])
        if font.advance(cand) <= avail:
            cur.append(words.pop(0))
            continue
        if cur:
            break
        word = words.pop(0)
        cut = len(word)
        while cut > 1 and font.advance(word[:cut] + "-") > avail:
            cut -= 1
        if cut > 1:
            words.insert(0, word[cut:])
            cur = [word[:cut] + "-"]
        elif font.advance(word[:1]) <= avail:
            if len(word) > 1:
                words.insert(0, word[1:])
            cur = [word[:1]]
        else:
            words.insert(0, word)
        break
    return " ".join(cur), words


def _break_verbatim(
    line: str, avail: int, font: Font, cont: str
) -> tuple[list[tuple[str, str]], str]:
    """Split one code line at `avail` px without reflowing it.

    Returns `(pieces, unplaced)` where each piece is `(display, raw)` and the
    raw fragments concatenate back to the consumed prefix of `line`, so a page
    break inside a code line can be resumed exactly.

    "Preserve line breaks verbatim" cannot mean "let a 60-character line run off
    a 32-character panel". The two honest options are to break it or to push the
    tail into leftover, and leftover is *worse than clipping*: the tail would
    reappear after the lines that followed it, so the reader gets wrong order
    rather than merely incomplete text. Breaking with a visible continuation
    marker keeps order and keeps every character. Words are never reflowed and
    lines are never joined.
    """
    if avail <= 0:
        return [], line
    if font.advance(line) <= avail:
        return [(line, line)], ""

    indent = line[: len(line) - len(line.lstrip())][:8]
    out: list[tuple[str, str]] = []
    rest = line
    while rest:
        lead = "" if not out else indent
        if font.advance(lead + rest) <= avail:
            out.append((lead + rest, rest))
            return out, ""
        room = avail - font.advance(lead) - font.advance(cont)
        if room <= 0:
            break
        cut = len(rest)
        while cut > 1 and font.advance(rest[:cut]) > room:
            cut -= 1
        if cut < 1 or font.advance(rest[:cut]) > room:
            break
        out.append((lead + rest[:cut] + cont, rest[:cut]))
        rest = rest[cut:]
    return out, rest


# --- flow -------------------------------------------------------------------


@dataclass(frozen=True)
class MarkdownLine:
    """One placed line, with the block it came from.

    `font` is per-line because a caller may supply an `emphasis_font` for
    headings; `MarkdownLayout.runs` is the base-font view kept for structural
    compatibility with `Layout`.
    """

    run: GlyphRun
    block: int
    kind: str
    level: int
    font: Font


class _Page:
    """One flowed page.

    `next_block` is the index of the first block not yet *started*. `remainder`,
    when set, is the unconsumed tail of block `remainder_index`, which is always
    `next_block - 1`. Keeping the two separate is what makes the next page's
    starting state unambiguous -- conflating them is how an off-by-one silently
    duplicates or skips a block across a page boundary.
    """

    __slots__ = ("lines", "next_block", "remainder", "remainder_index", "exhausted")

    def __init__(self, lines, next_block, remainder, remainder_index, exhausted):
        self.lines: list[MarkdownLine] = lines
        self.next_block: int = next_block
        self.remainder: Block | None = remainder
        self.remainder_index: int = remainder_index
        self.exhausted: bool = exhausted


class _Grid:
    """The page's fixed baseline grid. Every block shares it."""

    def __init__(self, display: CircularDisplay, font: Font, n: int):
        lh = font.line_height
        y0 = max(0, int(display.widest_band(lh, n)))
        self.ys = [y0 + i * lh for i in range(n)]
        self.lh = lh
        self.display = display

    def width(self, i: int) -> int:
        y = self.ys[i]
        return self.display.line_width(y, y + self.lh)

    def left(self, i: int) -> int:
        y = self.ys[i]
        return self.display.line_left(y, y + self.lh)


def usable_lines(font: Font, display: CircularDisplay, policy: Policy = Policy()) -> int:
    """How many grid lines are wide enough to carry structured text.

    Deliberately stricter than `Font.max_feasible_lines`, whose 24px floor is
    about four characters. Measured on a 256px panel with DejaVu at 13px, that
    default reports 11 lines whose outermost hold ~9 characters each -- and a
    depth-2 bullet on such a line has room for five. This asks for
    `policy.min_line_width` on every line of the block instead.
    """
    lh = font.line_height
    n = 0
    while n < 64:
        cand = n + 1
        y0 = display.widest_band(lh, cand)
        if y0 < 0:
            break
        if any(
            display.line_width(y0 + i * lh, y0 + (i + 1) * lh) < policy.min_line_width
            for i in range(cand)
        ):
            break
        n = cand
    return max(n, 1)


class _Flow:
    def __init__(self, font, emphasis, display, policy):
        self.font = font
        self.emphasis = emphasis
        self.display = display
        self.policy = policy
        self.bullet = _pick(font, policy.bullet)
        self.head = _pick(font, policy.heading_prefix)
        self.quote = _pick(font, policy.quote_prefix)
        self.rule_char = _pick(font, policy.rule_char)
        self.cont = _pick(font, policy.code_continuation)
        self.ell = _pick(font, policy.ellipsis)

    def _font_for(self, block: Block) -> Font:
        return self.emphasis if (block.kind == HEADING and self.emphasis) else self.font

    def _marker(self, block: Block) -> str:
        """Substitute face-safe markers chosen at parse time by the policy."""
        p = block.prefix
        if block.kind == HEADING:
            return "" if self.emphasis else self.head
        if p == self.policy.bullet[0]:
            return self.bullet
        if p == self.policy.quote_prefix[0]:
            return self.quote
        return p

    def block(self, block: Block, bi: int, grid: _Grid, slot: int):
        """Place one block. Returns (lines, next_slot, remainder_or_None)."""
        if block.kind == CODE:
            return self._code(block, bi, grid, slot)
        if block.kind == RULE:
            return self._rule(block, bi, grid, slot)
        return self._text(block, bi, grid, slot)

    def _text(self, block, bi, grid, slot):
        font = self._font_for(block)
        policy = self.policy
        indent = min(block.level, policy.max_list_depth) * policy.indent_px
        prefix = self._marker(block)
        hang = min(font.advance(prefix), policy.hang_max_px)
        centred = block.kind not in _LEFT_ALIGNED
        segments = block.text.split("\n")  # authored hard breaks
        out: list[MarkdownLine] = []
        first = True

        for si, seg in enumerate(segments):
            words = seg.split()
            if not words and len(segments) > 1:
                continue
            while words or (first and prefix):
                if slot >= len(grid.ys):
                    rest = " ".join(words)
                    tail = "\n".join([rest] + segments[si + 1:]) if rest else \
                        "\n".join(segments[si + 1:])
                    if not tail.strip():
                        return out, slot, None
                    # The remainder KEEPS its prefix, so a list item continuing
                    # onto the next page carries its bullet again. On a HUD
                    # there is no scrollback: the reader arriving at page 2 has
                    # no memory of page 1, so each page has to stand alone.
                    # It also makes `leftover_source` round-trip exactly --
                    # dropping the prefix here meant re-paginating the leftover
                    # produced a bullet the direct page did not have.
                    return out, slot, replace(block, text=tail)
                lead = prefix if first else ""
                extra = 0 if first else hang
                avail = grid.width(slot) - indent - extra - font.advance(lead)
                text, words = _fill(list(words), avail, font)
                if not text and not lead:
                    # Nothing renderable at this width; try the next slot rather
                    # than spin. If no slot is wider the page loop above ends it.
                    slot += 1
                    continue
                shown = lead + text
                w = font.advance(shown)
                if centred:
                    x = int(self.display.radius - w / 2)
                    x = max(x, grid.left(slot) + indent)
                else:
                    x = grid.left(slot) + indent + extra
                out.append(
                    MarkdownLine(
                        GlyphRun(shown, x, grid.ys[slot] + font.ascent, w),
                        bi, block.kind, block.level, font,
                    )
                )
                slot += 1
                first = False
                if not words:
                    break
        return out, slot, None

    def _code(self, block, bi, grid, slot):
        """Code gets a rectangular sub-viewport.

        Using each line's own chord would give left-aligned code a ragged left
        edge, which is unreadable. Instead the block is fitted to the narrowest
        chord across the slots it occupies, so every line in it shares one left
        edge and one width. The span is not known before breaking and the break
        depends on the width, so this iterates -- monotonically (a narrower
        width only ever yields more lines) and boundedly.
        """
        font = self.font
        room = len(grid.ys) - slot
        if room <= 0:
            return [], slot, block

        def cut_at(width: int):
            """Break every source line at `width`. -> [(pieces, unplaced)]."""
            return [
                ([("", "")], "") if not ln.strip()
                else _break_verbatim(ln, width, font, self.cont)
                for ln in block.lines
            ]

        span = min(max(len(block.lines), 1), room)
        width = grid.width(slot)
        cuts: list[tuple[list[tuple[str, str]], str]] = []
        for _ in range(4):
            width = min(grid.width(i) for i in range(slot, slot + span))
            cuts = cut_at(width)
            need = min(sum(max(len(p), 1) for p, _ in cuts), room)
            if need == span:
                break
            span = max(1, need)

        left = int(self.display.radius - width / 2)
        out: list[MarkdownLine] = []
        k = slot
        stop_line, tail = None, ""

        for li, (pieces, unplaced) in enumerate(cuts):
            if unplaced:
                # Not even one character fits at this width. usable_lines()
                # makes this unreachable in practice; surface it rather than
                # spin or clip if it ever happens.
                stop_line, tail = li, block.lines[li]
                break
            take = pieces[: len(grid.ys) - k]
            for disp, _raw in take:
                if disp:
                    out.append(
                        MarkdownLine(
                            GlyphRun(disp, left, grid.ys[k] + font.ascent,
                                     min(font.advance(disp), width)),
                            bi, CODE, block.level, font,
                        )
                    )
                k += 1
            if len(take) < len(pieces):
                consumed = "".join(raw for _d, raw in take)
                stop_line, tail = li, block.lines[li][len(consumed):]
                break
        else:
            return out, k, None

        rest = ((tail,) if tail else ()) + tuple(block.lines[stop_line + 1:])
        if not rest:
            return out, k, None
        return out, k, replace(block, lines=rest)

    def _rule(self, block, bi, grid, slot):
        if slot >= len(grid.ys):
            return [], slot, block
        font = self.font
        target = int(grid.width(slot) * self.policy.rule_fraction)
        unit = max(font.advance(self.rule_char), 1)
        text = self.rule_char * max(1, target // unit)
        w = font.advance(text)
        x = int(self.display.radius - w / 2)
        return (
            [MarkdownLine(GlyphRun(text, x, grid.ys[slot] + font.ascent, w),
                          bi, RULE, 0, font)],
            slot + 1,
            None,
        )

    def page(
        self,
        blocks: Sequence[Block],
        start: int,
        pending: Block | None,
        pending_index: int,
        n: int,
    ) -> _Page:
        """Fill one page of `n` grid lines, beginning at `pending` if given."""
        grid = _Grid(self.display, self.font, n)
        lines: list[MarkdownLine] = []
        slot = 0
        queue: list[tuple[int, Block]] = []
        if pending is not None:
            queue.append((pending_index, pending))
        queue.extend((j, blocks[j]) for j in range(start, len(blocks)))

        for j, blk in queue:
            if slot >= len(grid.ys):
                return _Page(lines, j, None, -1, False)
            made, slot, rest = self.block(blk, j, grid, slot)
            lines.extend(made)
            if rest is not None:
                return _Page(lines, j + 1, rest, j, False)
        return _Page(lines, len(blocks), None, -1, True)


# --- public API -------------------------------------------------------------


@dataclass(frozen=True)
class MarkdownLayout:
    """One page of markdown, placed.

    Structurally compatible with `Layout`: it exposes `.runs`, `.leftover` and
    `.truncated` with the same meanings, so the blit loop in `render.py` works
    on it unchanged. `.lines` carries the extra structure -- which block each
    line came from, and which font to draw it with when an `emphasis_font` is in
    play.

    `leftover_source` is a real slice of the input for whole blocks that have
    not been reached. For a block split part-way it is a RE-SYNTHESIS of that
    one block's remainder in minimal markdown, not a byte slice, because a
    partially consumed paragraph has no source range. It is stable under
    re-pagination: laying out `leftover_source` at page 0 yields the same lines
    as page n+1 of the original, which is what the round-trip test pins.
    """

    lines: tuple[MarkdownLine, ...]
    metadata: Metadata
    leftover_source: str
    page: int
    has_more: bool
    doc: MarkdownDoc

    @property
    def runs(self) -> tuple[GlyphRun, ...]:
        return tuple(l.run for l in self.lines)

    @property
    def leftover(self) -> str:
        return self.leftover_source

    @property
    def truncated(self) -> bool:
        return self.has_more

    def text(self) -> str:
        """The page's rendered text, one line per line. For tests and logs."""
        return "\n".join(l.run.text for l in self.lines)

    def __iter__(self) -> Iterator[GlyphRun]:
        return iter(self.runs)

    def __len__(self) -> int:
        return len(self.lines)

    def __getitem__(self, i):
        return self.lines[i].run


def _resynth(block: Block, policy: Policy) -> str:
    """Minimal markdown for a partially consumed block.

    The marker has to be mapped back to MARKDOWN, not reused as rendered.
    `Block.prefix` holds the display form -- "• ", "[x] ", "WARNING: " -- and
    emitting "• text" produces a paragraph on re-parse, not a list item, which
    silently changes the block kind on the next page.
    """
    if block.kind == CODE:
        return f"```{block.info}\n" + "\n".join(block.lines) + "\n```"
    if block.kind == HEADING:
        return "#" * max(1, block.level) + " " + block.text
    if block.kind == RULE:
        return "---"

    if block.kind == LIST:
        p = block.prefix
        if p == policy.checked:
            marker = "- [x]"
        elif p == policy.unchecked:
            marker = "- [ ]"
        elif re.match(r"^\d+\.\s*$", p):
            marker = p.strip()
        else:
            marker = "-"
        return "  " * block.level + marker + " " + block.text

    if block.kind == QUOTE:
        bar = "> " * (block.level + 1)
        p = block.prefix
        if p and p != policy.quote_prefix[0]:
            # A callout lead line: "WARNING: " came from "[!WARNING]".
            return f"{bar}[!{p.rstrip(': ')}] {block.text}"
        return bar + block.text

    return block.text  # paragraph, and table records re-parse as paragraphs


def _leftover(doc: MarkdownDoc, page: _Page, policy: Policy) -> str:
    """Source for everything this page did not render, in reading order."""
    if page.exhausted:
        return ""
    parts: list[str] = []
    if page.remainder is not None:
        parts.append(_resynth(page.remainder, policy))
    nxt = page.next_block
    if nxt < len(doc.blocks):
        start = doc.blocks[nxt].source[0]
        parts.append("\n".join(doc.source_lines[start:]).strip("\n"))
    return "\n\n".join(p for p in parts if p.strip())


def layout_markdown(
    source: str | MarkdownDoc,
    display: CircularDisplay,
    font: Font,
    *,
    page: int = 0,
    max_lines: int | None = None,
    emphasis_font: Font | None = None,
    policy: Policy = Policy(),
) -> MarkdownLayout:
    """Lay one page of markdown out on a round panel.

    Pure. `page` is an index, not a cursor: reaching page 3 re-flows pages 0-2
    to find where it begins, which is deterministic and cheap on note-sized
    input, and is the price of having no hidden state to get out of sync.

    `max_lines` is a ceiling clamped to `usable_lines()`. `emphasis_font` is
    optional and, if given, must not have a taller `line_height` than `font` --
    the page shares one baseline grid, and a taller face would silently overrun
    its slot.
    """
    if emphasis_font is not None and emphasis_font.line_height > font.line_height:
        raise ValueError(
            f"emphasis_font line_height {emphasis_font.line_height} exceeds "
            f"{font.line_height}; the page shares one baseline grid. Use a "
            "smaller size for the emphasis face."
        )
    if page < 0:
        raise ValueError(f"page must be >= 0, got {page}")

    doc = source if isinstance(source, MarkdownDoc) else parse_markdown(source, policy)
    cap = usable_lines(font, display, policy)
    if max_lines is not None:
        cap = max(1, min(cap, max_lines))
    flow = _Flow(font, emphasis_font, display, policy)

    start, pending, pending_index = 0, None, -1
    result = flow.page(doc.blocks, start, pending, pending_index, cap)
    for _ in range(page):
        if result.exhausted:
            result = _Page([], len(doc.blocks), None, -1, True)
            start, pending, pending_index = len(doc.blocks), None, -1
            break
        start = result.next_block
        pending, pending_index = result.remainder, result.remainder_index
        result = flow.page(doc.blocks, start, pending, pending_index, cap)

    if result.exhausted and len(result.lines) < cap:
        # Short final page: centre for the count it actually has. Re-flowing at
        # a smaller n can itself change the count, and iterating to a fixed
        # point can oscillate -- the non-terminating bug typography.py already
        # hit. Search for a self-consistent n instead, over a bounded range.
        for n in range(1, cap + 1):
            cand = flow.page(doc.blocks, start, pending, pending_index, n)
            if cand.exhausted and len(cand.lines) <= n:
                result = cand
                break

    return MarkdownLayout(
        lines=tuple(result.lines),
        metadata=_with_unrenderable(doc.metadata, result.lines, font),
        leftover_source=_leftover(doc, result, policy),
        page=page,
        has_more=not result.exhausted,
        doc=doc,
    )


def _with_unrenderable(meta: Metadata, lines, font: Font) -> Metadata:
    """Report characters the face cannot draw. PIL will not."""
    bad: list[str] = []
    seen: set[str] = set()
    for l in lines:
        for ch in l.run.text:
            if ch in seen:
                continue
            seen.add(ch)
            if not has_glyph(l.font, ch):
                bad.append(ch)
    if not bad:
        return meta
    return replace(meta, unrenderable=tuple(sorted(set(meta.unrenderable) | set(bad))))


def render_markdown(
    surface: Surface,
    source: str | MarkdownDoc,
    font: Font,
    display: CircularDisplay | None = None,
    *,
    page: int = 0,
    max_lines: int | None = None,
    emphasis_font: Font | None = None,
    policy: Policy = Policy(),
    levels: int = 4,
    palette_base: int = 0,
) -> MarkdownLayout:
    """Lay out and draw one page. Mirrors `render.render_text`'s shape."""
    from .render import HALO

    layout = layout_markdown(
        source, display or HALO, font, page=page, max_lines=max_lines,
        emphasis_font=emphasis_font, policy=policy,
    )
    for line in layout.lines:
        cov = line.font.rasterize(line.run, levels)
        surface.blit_coverage(
            cov, line.run.x, line.run.baseline - line.font.ascent, palette_base, levels
        )
    surface.present()
    return layout
