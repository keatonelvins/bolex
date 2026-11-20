"""Build Bolex from ET Book: uv run bolex [--face italic] [--out build] [-v]"""

import argparse
import functools
import io
import logging
import time
from pathlib import Path

import ttfautohint
import ufo2ft
import ufoLib2
from fontTools.ttLib import TTFont

from . import config, etbook, features, figures, fshort, glyphs, kerning, ligatures, smallcaps, spacing


@functools.cache
def draw(face: str) -> ufoLib2.Font:
    """ET Book's face with everything Bolex changes, ready to compile."""
    font = etbook.load(face)
    spacing.fix(font, face)
    ligatures.add(font)
    fshort.add(font, face)
    if face == "Roman":
        figures.set_up(font)
        glyphs.add_all(font, face)
        smallcaps.complete(font)
    else:
        glyphs.add_all(font, face, roman=draw("Roman"))
    font.features.text = features.build(font)
    kerning.kern(font, face)
    return font


@functools.cache
def win_metrics() -> tuple[int, int]:
    """usWinAscent and usWinDescent: the family's real extents (+10), so Windows clips no accent or descender."""
    top = bottom = 0
    for face in config.FACES:
        font = draw(face)
        for glyph in font:
            if bounds := glyph.getBounds(font):
                top, bottom = max(top, bounds.yMax), min(bottom, bounds.yMin)
    return round(top) + 10, round(-bottom) + 10


def compile_ttf(face: str) -> TTFont:
    """Compile the face to hinted TrueType."""
    font = draw(face)
    # GDEF glyph classes: ligatures and everything else (no marks here).
    font.lib["public.openTypeCategories"] = {
        glyph.name: "ligature" if glyph.name.startswith("f_") else "base" for glyph in font if glyph.name != ".notdef"
    }
    font.info.openTypeOS2WinAscent, font.info.openTypeOS2WinDescent = win_metrics()
    ttf = ufo2ft.compileTTF(
        font, removeOverlaps=True, overlapsBackend="pathops", useProductionNames=True, reverseDirection=True
    )
    buffer = io.BytesIO()
    ttf.save(buffer)
    hinted = ttfautohint.ttfautohint(
        in_buffer=buffer.getvalue(),
        hinting_range_min=8,
        hinting_range_max=50,
        hinting_limit=200,
        increase_x_height=14,
        # The Win metrics already cover every glyph, so no -W: it adds blue zones there that squeeze tall
        # accents into the capitals. Strong stems for DirectWrite: dashes and crossbars snap to a solid pixel
        # (the default thinned them to 0.75 px) and accents clear the capitals (Ë Ñ at 20-21 px).
        dw_cleartype_stem_width_mode=ttfautohint.StemWidthMode.STRONG,
        gray_stem_width_mode=ttfautohint.StemWidthMode.NATURAL,
        no_info=True,
    )
    ttf = TTFont(io.BytesIO(hinted), recalcTimestamp=False)
    ttf["head"].modified = ttf["head"].created  # ttfautohint keeps the source's stamp, so a build repeats exactly
    ttf["head"].flags |= 1 << 3  # hinted: sizes are whole pixels
    return ttf


def build(face: str, out: Path) -> None:
    """Write the face's .ttf and .woff2 into `out`."""
    ttf = compile_ttf(face)
    out.mkdir(parents=True, exist_ok=True)
    name = f"{config.FAMILY}-{face}"
    # The .ttf keeps its glyph names: apps map ligatures and small caps back to text with them (PDF copy, search).
    ttf.save(out / f"{name}.ttf")
    ttf["post"].formatType = 3.0
    ttf.flavor = "woff2"
    ttf.save(out / f"{name}.woff2")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the Bolex fonts.")
    parser.add_argument("--face", action="append", type=str.title, choices=config.FACES, help="build only this face")
    parser.add_argument("--out", type=Path, default=config.FONTS, help="output folder (default: fonts/)")
    parser.add_argument("-v", "--verbose", action="store_true", help="say what each step changes")
    args = parser.parse_args()
    logging.basicConfig(format="  %(message)s")
    logging.getLogger("bolex").setLevel(logging.INFO if args.verbose else logging.WARNING)
    for face in config.FACES:
        if args.face and face not in args.face:
            continue
        start = time.perf_counter()
        build(face, args.out)
        print(f"{config.FAMILY}-{face}  {time.perf_counter() - start:.1f}s")


if __name__ == "__main__":
    main()
