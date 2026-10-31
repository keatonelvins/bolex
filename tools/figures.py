#!/usr/bin/env python3
"""Set up the Roman's figures: proportional lining by default.

ET Book's Roman mapped 0-9 to oldstyle figures and kept tabular lining
figures as ``zero.lining`` etc.  Bolex reads better in prose with
proportional lining figures, so the Roman ends up with:

    zero      proportional lining  (default, U+0030 ...)
    zero.tf   tabular lining       (``tnum``; ET Book's ``zero.lining``)
    zero.osf  proportional oldstyle (``onum``; ET Book's ``zero``)

The proportional figures are the tabular drawings respaced: each side's
sidebearing is the average of its tabular value and an optical value
that gives the side the same depth-limited white area as the zero (the
reference round figure, whose tabular spacing is kept).

The Italic keeps ET Book's oldstyle figures as its only figures.

Kerning, glyph order and components follow the renames.  Idempotent.

Usage: tools/figures.py
"""
from pathlib import Path

import numpy as np
import ufoLib2

import outline

ROOT = Path(__file__).resolve().parent.parent
FIGURES = ["zero", "one", "two", "three", "four",
           "five", "six", "seven", "eight", "nine"]
DEPTH = 80          # how far into a figure's side the white area counts
MIN_SIDEBEARING = 12


def rename_glyphs(font, mapping):
    """Rename glyphs (simultaneously) and every reference to them."""
    glyphs = {old: font[old] for old in mapping}
    for old in mapping:
        del font[old]
    for old, new in mapping.items():
        glyph = glyphs[old]
        glyph._name = new
        font.layers.defaultLayer.insertGlyph(glyph, new, overwrite=False,
                                             copy=False)
    for glyph in font:
        for component in glyph.components:
            if component.baseGlyph in mapping:
                component.baseGlyph = mapping[component.baseGlyph]
    kerning = {(mapping.get(l, l), mapping.get(r, r)): v
               for (l, r), v in font.kerning.items()}
    font.kerning.clear()
    font.kerning.update(kerning)
    for group, members in list(font.groups.items()):
        font.groups[group] = [mapping.get(m, m) for m in members]
    order = font.lib.get("public.glyphOrder")
    if order:
        font.lib["public.glyphOrder"] = [mapping.get(n, n) for n in order]


def lining_default(font):
    """zero.lining -> zero.tf (tabular lining), zero -> zero.osf."""
    if "zero.osf" in font:
        return
    unicodes = {n: list(font[n].unicodes) for n in FIGURES}
    mapping = {}
    for n in FIGURES:
        mapping[n] = f"{n}.osf"
        mapping[f"{n}.lining"] = f"{n}.tf"
    rename_glyphs(font, mapping)
    for n in FIGURES:
        font[f"{n}.osf"].unicodes = []
        font[f"{n}.tf"].unicodes = unicodes[n]


def level_tops(font, top=640, floor=560):
    """ET Book's lining 7 topped out at 624 (and the 6, 8 and 9 at
    637-639) against 640 for the rest, so after hinting the 7 rendered a
    whole pixel short at body sizes.  Lift each figure's head (everything
    above ``floor``) to the common top."""
    for n in FIGURES:
        glyph = font[f"{n}.tf"]
        dy = round(top - glyph.getBounds(font).yMax)
        if dy > 0:
            for contour in glyph.contours:
                for p in contour:
                    if p.y > floor:
                        p.y += dy


def tabular_widths(font):
    """ET Book's eight.lining was 25 units narrower than the other
    tabular figures; centre every tabular figure on one common width."""
    width = max(font[f"{n}.tf"].width for n in FIGURES)
    for n in FIGURES:
        glyph = font[f"{n}.tf"]
        if glyph.width != width:
            outline.shift_glyph(glyph, round((width - glyph.width) / 2))
            glyph.width = width


def side_area(edge_offsets):
    """Mean depth-limited white on one side (NaN rows count as DEPTH)."""
    d = np.where(np.isnan(edge_offsets), DEPTH,
                 np.minimum(edge_offsets, DEPTH))
    return float(d.mean())


def proportional(font):
    """Add proportional lining figures as the defaults."""
    if all(n in font and font[n].unicodes for n in FIGURES):
        return
    ys = np.arange(0, 641, 8, dtype=float)
    measured = {}
    for n in FIGURES:
        left, right = outline.profile(font, f"{n}.tf", tan=0, ys=ys)
        xmin, xmax = np.nanmin(left), np.nanmax(right)
        glyph = font[f"{n}.tf"]
        measured[n] = dict(
            lsb=xmin, rsb=glyph.width - xmax,
            area_l=side_area(left - xmin), area_r=side_area(xmax - right))
    ref = measured["zero"]
    target_l = ref["lsb"] + ref["area_l"]
    target_r = ref["rsb"] + ref["area_r"]
    for n in FIGURES:
        m = measured[n]
        lsb = max(MIN_SIDEBEARING, (m["lsb"] + target_l - m["area_l"]) / 2)
        rsb = max(MIN_SIDEBEARING, (m["rsb"] + target_r - m["area_r"]) / 2)
        tab = font[f"{n}.tf"]
        glyph = tab.copy()
        glyph._name = n
        font.layers.defaultLayer.insertGlyph(glyph, n, overwrite=False,
                                             copy=False)
        glyph.unicodes = list(tab.unicodes)
        tab.unicodes = []
        outline.set_sidebearings(font, n, lsb, rsb, tan=0)
    order = font.lib.get("public.glyphOrder", [])
    for n in FIGURES:
        if n not in order and f"{n}.tf" in order:
            order.insert(order.index(f"{n}.tf"), n)


def main():
    path = ROOT / "sources" / "Bolex-Roman.ufo"
    font = ufoLib2.Font.open(path)
    lining_default(font)
    level_tops(font)
    tabular_widths(font)
    proportional(font)
    font.save()
    for n in FIGURES:
        print(f"  {n:6s} proportional {font[n].width:4d}  "
              f"tabular {font[n + '.tf'].width}  "
              f"oldstyle {font[n + '.osf'].width}")


if __name__ == "__main__":
    main()
