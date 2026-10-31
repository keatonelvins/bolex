#!/usr/bin/env python3
"""Build Bolex webfonts from the UFO sources.

    sources/Bolex-*.ufo
      -> ufo2ft (TrueType outlines, overlaps removed, kern/liga/smcp... GSUB/GPOS)
      -> ttfautohint
      -> build/ttf/Bolex-*.ttf  and  fonts/Bolex-*.woff2

Usage: tools/build.py [sources/Bolex-Roman.ufo ...]
"""
import io
import sys
from pathlib import Path

import ttfautohint
import ufo2ft
import ufoLib2
from fontTools.ttLib import TTFont

ROOT = Path(__file__).resolve().parent.parent
BUILD = ROOT / "build"
FONTS = ROOT / "fonts"


def compile_ttf(ufo_path, win=None):
    ufo = ufoLib2.Font.open(ufo_path)
    # GDEF glyph classes: ligatures and everything else (no marks here).
    ufo.lib["public.openTypeCategories"] = {
        g.name: "ligature" if g.name.startswith("f_") else "base"
        for g in ufo if g.name != ".notdef"}
    if win:
        ufo.info.openTypeOS2WinAscent, ufo.info.openTypeOS2WinDescent = win
    ttf = ufo2ft.compileTTF(
        ufo,
        removeOverlaps=True,
        overlapsBackend="pathops",
        useProductionNames=True,
        reverseDirection=True,
    )
    buf = io.BytesIO()
    ttf.save(buf)
    hinted = ttfautohint.ttfautohint(
        in_buffer=buf.getvalue(),
        hinting_range_min=8,
        hinting_range_max=50,
        hinting_limit=200,
        increase_x_height=14,
        # Win metrics already cover every glyph (win_metrics), so no -W:
        # it adds blue zones at the win metrics that squeeze tall accents
        # into the capitals.  Strong stems for DirectWrite: dashes and
        # crossbars snap to a solid pixel (the default thinned them to
        # 0.75 px) and accents clear the capitals (Ë Ñ at 20-21 px);
        # natural for grayscale.
        dw_cleartype_stem_width_mode=ttfautohint.StemWidthMode.STRONG,
        gray_stem_width_mode=ttfautohint.StemWidthMode.NATURAL,
        no_info=True,
    )
    font = TTFont(io.BytesIO(hinted), recalcTimestamp=False)
    # ttfautohint keeps the source's timestamps; make builds reproducible.
    font["head"].modified = font["head"].created
    font["head"].flags |= 1 << 3          # hinted: force integer ppem
    font["post"].formatType = 3.0         # no glyph names in the webfont
    return ufo, font


def win_metrics(paths):
    """usWinAscent/Descent: the family's real extents (+10), so Windows
    never clips a tall accent or a deep descender."""
    top = bottom = 0
    for path in paths:
        ufo = ufoLib2.Font.open(path)
        for glyph in ufo:
            b = glyph.getBounds(ufo)
            if b:
                top, bottom = max(top, b.yMax), min(bottom, b.yMin)
    return round(top) + 10, round(-bottom) + 10


def main(paths):
    paths = paths or sorted(str(p) for p in (ROOT / "sources").glob("*.ufo"))
    (BUILD / "ttf").mkdir(parents=True, exist_ok=True)
    FONTS.mkdir(exist_ok=True)
    all_sources = sorted(str(p) for p in (ROOT / "sources").glob("*.ufo"))
    win = win_metrics(all_sources)
    for path in paths:
        ufo, font = compile_ttf(path, win)
        name = ufo.info.postscriptFontName
        ttf_path = BUILD / "ttf" / f"{name}.ttf"
        font.save(ttf_path)
        font.flavor = "woff2"
        woff2_path = FONTS / f"{name}.woff2"
        font.save(woff2_path)
        print(f"{woff2_path.relative_to(ROOT)}: "
              f"{woff2_path.stat().st_size / 1024:.1f} KiB, "
              f"{len(font.getGlyphOrder())} glyphs")


if __name__ == "__main__":
    main(sys.argv[1:])
