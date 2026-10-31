#!/usr/bin/env python3
"""Add fb, fh, fk (and ffb, ffh, ffk) ligatures.

The f's hook reaches about 110 units past its advance; before the
ascender of b, h or k it collides, and kerning it apart opens a hole in
the middle of words like "offhand" or "halfback".  ET Book already has
fl and ffl, where the hook flows into the l's stem, and b, h and k share
the l's stem.  So each new ligature is the existing fl (or ffl) with the
l-stem cut away below a clip height, unioned with the real b, h or k
aligned on that stem: the f, the join and the top of the stem are ET
Book's own, and everything below the clip (bowl, arch, arm, feet) is
the letter's own.

Usage: tools/ligatures.py
"""
from pathlib import Path

import pathops
import ufoLib2
from fontTools.pens.transformPen import TransformPen

import outline

ROOT = Path(__file__).resolve().parent.parent
CLIP = 560            # below the x-height serifs, above the ascender flag
FOOT_HEIGHT = 60      # the l's foot serif lies below this
LETTERS = ["b", "h", "k"]


def _path(font, name, transform=(1, 0, 0, 1, 0, 0)):
    path = pathops.Path()
    font[name].draw(TransformPen(path.getPen(glyphSet=font), transform))
    return path


def _rect(x0, x1, y0, y1, tan):
    """Axis-aligned in upright space, sheared to the italic angle."""
    path = pathops.Path()
    pen = path.getPen()
    pts = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
    pen.moveTo((pts[0][0] + pts[0][1] * tan, pts[0][1]))
    for x, y in pts[1:]:
        pen.lineTo((x + y * tan, y))
    pen.closePath()
    return path


def _runs(font, name, y, tan):
    """Ink runs (upright x) of a glyph at height y."""
    pen = outline._SegmentPen(font)
    font[name].draw(TransformPen(pen, (1, 0, -tan, 1, 0, 0)))
    xs = []
    for (x0, y0), (x1, y1) in pen.segments:
        if (y0 <= y < y1) or (y1 <= y < y0):
            xs.append(x0 + (y - y0) / (y1 - y0) * (x1 - x0))
    xs.sort()
    return [(xs[i], xs[i + 1]) for i in range(0, len(xs) - 1, 2)]


def build(font, base, letter, name):
    tan = outline.slant(font)
    y_ref = CLIP - 20
    stem = _runs(font, base, y_ref, tan)[-1]            # the l's stem
    letter_stem = _runs(font, letter, y_ref, tan)[0]     # b/h/k's stem
    dx = round(stem[0] - letter_stem[0])                 # align left edges

    # Cut the l's stem below the clip (slightly inside its left edge, so
    # the f's crossbar still runs into the new stem) and the l's foot
    # serif, which reaches back toward the f.
    foot = min(_runs(font, base, y, tan)[-1][0] for y in (5, 20, 40))
    cut = pathops.op(_rect(stem[0] + 3, 4000, -400, CLIP, tan),
                     _rect(foot - 2, 4000, -400, FOOT_HEIGHT, tan),
                     pathops.PathOp.UNION)
    kept = pathops.op(_path(font, base), cut, pathops.PathOp.DIFFERENCE)
    lower = pathops.op(_path(font, letter, (1, 0, 0, 1, dx, 0)),
                       _rect(-4000, 4000, -400, CLIP, tan),
                       pathops.PathOp.INTERSECTION)
    # Taper any difference in stem width over 100 units below the clip.
    right = letter_stem[1] + dx
    taper = pathops.Path()
    pen = taper.getPen()
    for i, (x, y) in enumerate([(stem[0] + 4, CLIP - 100), (right, CLIP - 100),
                                (stem[1], CLIP + 1), (stem[0] + 4, CLIP + 1)]):
        (pen.moveTo if i == 0 else pen.lineTo)((x + y * tan, y))
    pen.closePath()
    lower = pathops.op(lower, taper, pathops.PathOp.UNION)
    result = pathops.op(kept, lower, pathops.PathOp.UNION)

    glyph = font.newGlyph(name)
    result.draw(outline.CubicPen(glyph.getPen()))
    glyph.width = dx + font[letter].width
    order = font.lib.setdefault("public.glyphOrder", [])
    if name not in order:
        order.append(name)
    return glyph


def main():
    for face in ["Roman", "Italic"]:
        path = ROOT / "sources" / f"Bolex-{face}.ufo"
        font = ufoLib2.Font.open(path)
        made = []
        for letter in LETTERS:
            for base, name in [("f_l", f"f_{letter}"),
                               ("f_f_l", f"f_f_{letter}")]:
                if base in font:
                    if name in font:
                        del font[name]
                    build(font, base, letter, name)
                    made.append(name)
        font.save()
        print(f"{path.relative_to(ROOT)}: {' '.join(made)}")


if __name__ == "__main__":
    main()
