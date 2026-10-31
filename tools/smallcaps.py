#!/usr/bin/env python3
"""Complete the Roman's small capitals.

ET Book's small caps miss a few letters of the character set (š ž ð),
so ``smcp`` left them lowercase in the middle of a small-cap word.  This
adds them, following ET Book's own construction:

* accents are the lowercase accent glyphs, unscaled, raised ACCENT_RAISE
  units (ET Book's acute/grave/circumflex/dieresis/ring/tilde small caps
  all sit 71-77 units above their lowercase position) and centred on the
  small cap;
* the bar of ð is taken from the capital Ð and mapped onto d.sc.

It also fixes the small-cap punctuation (see ``punctuation``).

Usage: tools/smallcaps.py
"""
import unicodedata
from pathlib import Path

import pathops
import ufoLib2
from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.transformPen import TransformPen

ROOT = Path(__file__).resolve().parent.parent
ACCENT_RAISE = 75

MARKS = {chr(cp): name for cp, name in [
    (0x0301, "acute"), (0x0300, "grave"), (0x0302, "circumflex"),
    (0x0308, "dieresis"), (0x030A, "ring"), (0x0303, "tilde"),
    (0x030C, "caron"), (0x030B, "hungarumlaut"), (0x0304, "macron"),
    (0x0307, "dotaccent"), (0x0306, "breve"),
]}
BAR_FROM_CAPITAL = {"eth.sc": ("d.sc", "Eth", "D")}
MIN_PIECE = 40     # smaller leftovers of capital-minus-base are slivers


def bounds(font, glyph_or_path):
    pen = BoundsPen(font)
    glyph_or_path.draw(pen)
    return pen.bounds


def to_path(font, name, transform=(1, 0, 0, 1, 0, 0)):
    path = pathops.Path()
    font[name].draw(TransformPen(path.getPen(glyphSet=font), transform))
    return path


def new_glyph(font, name, path, width):
    if name in font:
        del font[name]
    glyph = font.newGlyph(name)
    path.draw(glyph.getPen())
    glyph.width = width
    order = font.lib.setdefault("public.glyphOrder", [])
    if name not in order:
        order.append(name)
    return glyph


def accented(font, name, base_sc, mark):
    base = font[base_sc]
    bx0, by0, bx1, by1 = bounds(font, base)
    accent = font[mark]
    dx = (bx0 + bx1) / 2 - accent.width / 2
    path = to_path(font, base_sc)
    path = pathops.op(path, to_path(font, mark,
                                    (1, 0, 0, 1, round(dx), ACCENT_RAISE)),
                      pathops.PathOp.UNION)
    return new_glyph(font, name, path, base.width)


def _pieces(path):
    for contour in path.contours:
        piece = pathops.Path()
        contour.draw(piece.getPen())
        yield piece


def _ink_extent(font, name, y):
    from outline import _SegmentPen
    pen = _SegmentPen(font)
    font[name].draw(pen)
    xs = [x0 + (y - y0) / (y1 - y0) * (x1 - x0)
          for (x0, y0), (x1, y1) in pen.segments
          if (y0 <= y < y1) or (y1 <= y < y0)]
    return min(xs), max(xs)


def bar_from_capital(font, name, base_sc, capital, cap_base):
    """The crossbar of Ð, mapped onto the small cap.  The capital's
    bar is found as its short pieces outside the base letter; the band of
    rows they span is cut from the capital (minus the base letter, minus
    slivers where the two outlines differ slightly) and mapped onto the
    small cap, x anchored on the outer edges at 30% height."""
    cap_h = bounds(font, font["H"])[3]
    sc_h = bounds(font, font["h.sc"])[3]
    s = sc_h / cap_h
    diff = pathops.op(to_path(font, capital), to_path(font, cap_base),
                      pathops.PathOp.DIFFERENCE)
    short = [p.bounds for p in _pieces(diff)
             if p.bounds[3] - p.bounds[1] < 0.3 * cap_h
             and p.bounds[2] - p.bounds[0] > 15]
    y0 = min(b[1] for b in short)
    y1 = max(b[3] for b in short)
    band = pathops.Path()
    pen = band.getPen()
    pen.moveTo((-2000, y0)); pen.lineTo((4000, y0))
    pen.lineTo((4000, y1)); pen.lineTo((-2000, y1)); pen.closePath()
    bar = pathops.op(pathops.op(to_path(font, capital), band,
                                pathops.PathOp.INTERSECTION),
                     to_path(font, cap_base), pathops.PathOp.DIFFERENCE)
    keep = pathops.Path()
    for piece in _pieces(bar):
        x0, _, x1, _ = piece.bounds
        if x1 - x0 >= MIN_PIECE:
            keep = pathops.op(keep, piece, pathops.PathOp.UNION)
    c0, c1 = _ink_extent(font, cap_base, cap_h * 0.3)
    s0, s1 = _ink_extent(font, base_sc, sc_h * 0.3)
    a = (s1 - s0) / (c1 - c0)
    mapped = pathops.Path()
    keep.draw(TransformPen(mapped.getPen(), (a, 0, 0, s, s0 - a * c0, 0)))
    path = pathops.op(to_path(font, base_sc), mapped, pathops.PathOp.UNION)
    return new_glyph(font, name, path, font[base_sc].width)


def punctuation(font, log):
    """ET Book's question.csc was a full-size copy of the question mark,
    and its brace .csc forms were identical to the braces.  Rebuild the
    question mark at the height ratio of exclam.csc to exclam, and drop
    the do-nothing braces."""
    for name in ["braceleft.csc", "braceright.csc"]:
        if name in font:
            del font[name]
            log(f"removed {name} (identical to the brace)")
    if "exclam.csc" in font and "question" in font:
        ratio = bounds(font, font["exclam.csc"])[3] / bounds(font, font["exclam"])[3]
        path = pathops.Path()
        font["question"].draw(TransformPen(path.getPen(),
                                           (ratio, 0, 0, ratio, 0, 0)))
        new_glyph(font, "question.csc", path,
                  round(font["question"].width * ratio))
        log(f"question.csc: question at {ratio:.3f}")
    font.lib["public.glyphOrder"] = [g for g in font.lib.get(
        "public.glyphOrder", []) if g in font]


def main():
    path = ROOT / "sources" / "Bolex-Roman.ufo"
    font = ufoLib2.Font.open(path)
    punctuation(font, lambda m: print(f"  {m}"))
    made = []
    for glyph in list(font):
        name = glyph.name
        if "." in name or not glyph.unicodes or f"{name}.sc" in font:
            continue
        char = chr(glyph.unicodes[0])
        if unicodedata.category(char) != "Ll":
            continue
        sc = f"{name}.sc"
        if sc in BAR_FROM_CAPITAL:
            base_sc, capital, cap_base = BAR_FROM_CAPITAL[sc]
            if all(n in font for n in (base_sc, capital, cap_base)):
                bar_from_capital(font, sc, base_sc, capital, cap_base)
                made.append(sc)
            continue
        parts = unicodedata.normalize("NFD", char)
        if len(parts) != 2 or parts[1] not in MARKS:
            continue
        base = next((g.name for g in font if ord(parts[0]) in g.unicodes),
                    None)
        mark = MARKS[parts[1]]
        if base and f"{base}.sc" in font and mark in font:
            accented(font, sc, f"{base}.sc", mark)
            made.append(sc)
    font.save()
    print(f"{path.relative_to(ROOT)}: added {len(made)} small caps: "
          f"{' '.join(sorted(made))}")


if __name__ == "__main__":
    main()
