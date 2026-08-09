"""Render a vault note to a round display. Evidence, not a product.

This exists for one reason: to run `glanceable.markdown` against markdown that
was written as notes rather than as test fixtures, and show that nothing
disappears. It is an example. It is not part of the package, nothing in
`glanceable/` imports it, and `markdown.py` knows nothing about Obsidian --
wikilinks are the only vault-flavoured thing that got in, because they are cheap
and CommonMark-adjacent.

Retrieval is NOT implemented here, and should not be. `--query` is a dumb
substring match over filenames and titles, roughly fifteen lines of it. Finding
the right note is a solved, commoditised problem: point this at an Obsidian MCP
server or the Local REST API plugin and delete `find_note`. Automatic contextual
surfacing -- deciding *for* the wearer which note to show -- is a much harder
problem and is deliberately out of scope.

Pagination is user-driven and discrete. The loop in `render` is where a real
client would wait for a click; here it just advances and writes the next PNG.
There is no scroll, no fade, no auto-advance: peripheral motion is
pre-attentional and hijacks attention whether or not it matters, which is the
failure mode this whole toolkit exists to prevent.

Usage:

    python examples/obsidian_bridge.py --vault examples/vault --query chord
    python examples/obsidian_bridge.py --vault examples/vault --list
    python examples/obsidian_bridge.py --vault examples/vault --query all --out /tmp/pages

Open questions, named so they are not mistaken for oversights. None are solved
here and none should be until the wire format is confirmed on hardware:
BLE transport for a paginated document, phone-to-desktop relay topology, sync.
"""

from __future__ import annotations

import argparse
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from glanceable import HALO, Font, PILSurface, find_system_font, ramp_palette
from glanceable.markdown import parse_markdown, render_markdown


def load_vault(root: pathlib.Path) -> dict[str, pathlib.Path]:
    """Every .md file, keyed by stem. Obsidian resolves wikilinks by basename
    regardless of folder, so this mirrors that."""
    if not root.is_dir():
        raise SystemExit(f"no such vault directory: {root}")
    notes = {p.stem: p for p in sorted(root.rglob("*.md"))}
    if not notes:
        raise SystemExit(f"no .md files under {root}")
    return notes


def read_note(path: pathlib.Path) -> str:
    """Decode defensively. Real vaults contain BOMs and CRLF from Windows sync;
    neither is the renderer's problem, so they are normalised here."""
    raw = path.read_bytes()
    text = raw.decode("utf-8-sig", errors="replace")
    return text.replace("\r\n", "\n").replace("\r", "\n")


def find_note(notes: dict[str, pathlib.Path], query: str) -> pathlib.Path:
    """Deliberately trivial. Substring over the stem, then over the body.

    This is NOT retrieval and is not trying to be. Swap it for a real vault
    server; that is the whole point of keeping it this small.
    """
    q = query.casefold()
    for stem, path in notes.items():
        if q == stem.casefold():
            return path
    for stem, path in notes.items():
        if q in stem.casefold():
            return path
    for stem, path in notes.items():
        if q in read_note(path).casefold():
            return path
    raise SystemExit(
        f"no note matching {query!r}. Try --list.\n"
        f"Known: {', '.join(sorted(notes))}"
    )


def report(layout, notes, page_no: int) -> None:
    """Print what did not reach the glass. The three-destination contract says
    every piece of source is on the glass, in leftover_source, or here."""
    m = layout.metadata
    if page_no == 0:
        if m.frontmatter:
            print("  frontmatter (flat scan, NOT yaml):")
            for k, v in m.frontmatter.items():
                print(f"      {k}: {v}")
        for w in m.wikilinks:
            # Resolving the target is the CALLER's job, which is exactly why
            # markdown.py hands back the target instead of acting on it.
            mark = "->" if w.target.split("#")[0] in notes else "!!"
            kind = "embed" if w.embed else "link"
            print(f"  {mark} {kind:6} [[{w.target}]]"
                  f"{' as ' + repr(w.display) if w.display != w.target else ''}"
                  f"{'   (unresolved)' if mark == '!!' else ''}")
        for l in m.links:
            if l.elided:
                print(f"  .. elided url  {l.text}  <- {l.href[:60]}...")
        for label, body in m.footnotes.items():
            print(f"  .. footnote [^{label}]  {body[:70]}")
        for d in m.dropped:
            print(f"  -- {d.kind:14} line {d.line + 1:>3}  {d.detail[:60].strip()!r}")
        for r in m.reformatted:
            print(f"  ~~ {r}")
    if m.unrenderable:
        print(f"  !! page {page_no}: face cannot draw {' '.join(m.unrenderable)}")


def render(path: pathlib.Path, notes, font: Font, out: pathlib.Path,
           max_pages: int, quiet: bool) -> int:
    source = read_note(path)
    doc = parse_markdown(source)  # parse once; layout is pure over it
    if not quiet:
        print(f"\n=== {path.relative_to(path.parents[1])} "
              f"({len(source)} chars, {len(doc.blocks)} blocks) ===")

    out.mkdir(parents=True, exist_ok=True)
    stem = path.stem.replace(" ", "-")
    page_no = 0
    while page_no < max_pages:
        surface = PILSurface(256, 256, ramp_palette(4))
        # Note it is `doc` going in, not `source`: one parse, many pages.
        layout = render_markdown(surface, doc, font, HALO, page=page_no, levels=4)
        png = out / f"{stem}-p{page_no}.png"
        surface.to_rgb().save(png)
        if not quiet:
            print(f"\n  --- page {page_no} -> {png} ---")
            for line in layout.lines:
                print(f"    [{line.kind:9}] {line.run.text}")
            report(layout, notes, page_no)
        if not layout.has_more:
            return page_no + 1
        page_no += 1
        # A real client advances HERE, on a click. Not on a timer.
    return page_no


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--vault", type=pathlib.Path,
                    default=pathlib.Path(__file__).parent / "vault")
    ap.add_argument("--query", default="all",
                    help="note to show, or 'all'. A dumb substring match, "
                         "not retrieval -- see the module docstring.")
    ap.add_argument("--list", action="store_true", help="list notes and exit")
    ap.add_argument("--out", type=pathlib.Path,
                    default=pathlib.Path("build/vault-pages"))
    ap.add_argument("--size", type=int, default=13)
    ap.add_argument("--max-pages", type=int, default=24,
                    help="safety stop; pagination is bounded, not infinite")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    notes = load_vault(args.vault)
    if args.list:
        for stem, path in sorted(notes.items()):
            print(f"  {stem:24} {path}")
        return

    font = Font(find_system_font(), args.size)
    targets = (sorted(notes.values()) if args.query == "all"
               else [find_note(notes, args.query)])

    total = 0
    for path in targets:
        total += render(path, notes, font, args.out, args.max_pages, args.quiet)
    print(f"\n{len(targets)} note(s), {total} pages -> {args.out}/")


if __name__ == "__main__":
    main()
