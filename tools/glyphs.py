#!/usr/bin/env python3
"""Add the few characters long-form web text needs that ET Book lacked.

Anything missing from a webfont is drawn from a fallback font in the
middle of a line.  ET Book had no thin or narrow no-break spaces, no
non-breaking hyphen, no primes, no superior figures beyond ¹²³ and no
arrows (Markdown footnotes link back with ↩).  Everything here is
assembled from the font's own parts:

* spaces: empty glyphs at the conventional widths;
* hyphen/dash/apostrophe variants and superior figures: components of
  existing glyphs;
* primes, ≈ ≠ ≤ ≥ and arrows: built from the font's own quotesingle,
  asciitilde, equal, slash, less/greater and minus strokes;
* raised dashes, brackets and guillemets for capitals and lining
  figures (``case``);
* a visible .notdef box.

Usage: tools/glyphs.py
"""
import math
from pathlib import Path

import pathops
import ufoLib2
from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.transformPen import TransformPen

import outline

ROOT = Path(__file__).resolve().parent.parent

SPACES = {  # name: (codepoint, width or reference glyph)
    "uni2002": (0x2002, 500),            # en space
    "uni2003": (0x2003, 1000),           # em space
    "uni2007": (0x2007, "figure"),       # figure space
    "uni2008": (0x2008, "period"),       # punctuation space
    "uni2009": (0x2009, 200),            # thin space
    "uni200A": (0x200A, 83),             # hair space
    "uni202F": (0x202F, 200),            # narrow no-break space
}
COMPONENTS = {  # name: (codepoint, base glyph, dy)
    "uni2010": (0x2010, "hyphen", 0), "uni2011": (0x2011, "hyphen", 0),
    "uni02BC": (0x02BC, "quoteright", 0), "uni02BB": (0x02BB, "quoteleft", 0),
}
SUPERIORS = {f"uni207{d}": (0x2070 + d, n)
             for d, n in [(0, "zero"), (4, "four"), (5, "five"), (6, "six"),
                          (7, "seven"), (8, "eight"), (9, "nine")]}
SUPERIORS["uni2070"] = (0x2070, "zero")
# ---------------------------------------------------------------- helpers

def bounds(font, obj):
    pen = BoundsPen(font)
    obj.draw(pen)
    return pen.bounds


def to_path(font, name, transform=(1, 0, 0, 1, 0, 0)):
    path = pathops.Path()
    font[name].draw(TransformPen(path.getPen(glyphSet=font), transform))
    return path


def upright_center(font, name_or_path, tan):
    """Horizontal centre, measured upright (deslanted)."""
    pen = BoundsPen(font)
    target = font[name_or_path] if isinstance(name_or_path, str) else name_or_path
    target.draw(TransformPen(pen, (1, 0, -tan, 1, 0, 0)))
    x0, y0, x1, y1 = pen.bounds
    return (x0 + x1) / 2


def add(font, name, codepoint=None, path=None, width=0, components=()):
    if name in font:
        del font[name]
    glyph = font.newGlyph(name)
    if path is not None:
        path.draw(outline.CubicPen(glyph.getPen()))
    pen = glyph.getPointPen()
    for base, transform in components:
        pen.addComponent(base, transform)
    glyph.width = round(width)
    if codepoint:
        glyph.unicodes = [codepoint]
    order = font.lib.setdefault("public.glyphOrder", [])
    if name not in order:
        order.append(name)
    return glyph


def has_codepoint(font, cp):
    return any(cp in g.unicodes for g in font)


def rect(x0, y0, x1, y1):
    path = pathops.Path()
    pen = path.getPen()
    pen.moveTo((x0, y0)); pen.lineTo((x1, y0))
    pen.lineTo((x1, y1)); pen.lineTo((x0, y1)); pen.closePath()
    return path


def polygon(points):
    path = pathops.Path()
    pen = path.getPen()
    pen.moveTo(points[0])
    for p in points[1:]:
        pen.lineTo(p)
    pen.closePath()
    return path


def union(*paths):
    out = pathops.Path()
    for p in paths:
        out = pathops.op(out, p, pathops.PathOp.UNION)
    return out


def sheared(path, tan, about_y=0):
    out = pathops.Path()
    path.draw(TransformPen(out.getPen(), (1, 0, tan, 1, -tan * about_y, 0)))
    return out


def moved(path, dx=0, dy=0):
    out = pathops.Path()
    path.draw(TransformPen(out.getPen(), (1, 0, 0, 1, dx, dy)))
    return out


# ------------------------------------------------------------ the glyphs

def spaces(font):
    for name, (cp, width) in SPACES.items():
        if has_codepoint(font, cp):
            continue
        if width == "figure":
            width = font["zero.tf" if "zero.tf" in font else "zero"].width
        elif isinstance(width, str):
            width = font[width].width
        add(font, name, cp, width=width)


def components(font):
    for name, (cp, base, dy) in COMPONENTS.items():
        if not has_codepoint(font, cp) and base in font:
            add(font, name, cp, width=font[base].width,
                components=[(base, (1, 0, 0, 1, 0, dy))])
    # Figure dash: the en dash on the figure width.
    if not has_codepoint(font, 0x2012) and "endash" in font:
        fig = font["zero.tf" if "zero.tf" in font else "zero"].width
        w = font["endash"].width
        add(font, "uni2012", 0x2012, width=fig,
            components=[("endash", (1, 0, 0, 1, round((fig - w) / 2), 0))])
        # The dash is drawn with its own sidebearings; scale it to fit.
        x0, _, x1, _ = bounds(font, font["endash"])
        if x1 - x0 > fig - 40:
            s = (fig - 60) / (x1 - x0)
            font["uni2012"].components[0].transformation = (
                s, 0, 0, 1, round(30 - x0 * s), 0)


def borrow_numerators(font, roman):
    """The Italic has no numerator/superior figures of its own: use the
    Roman's, sloped to the italic angle (at superior size the difference
    from drawn italic figures is invisible)."""
    tan = outline.slant(font)
    for fig in ["zero", "one", "two", "three", "four", "five", "six",
                "seven", "eight", "nine"]:
        name = f"{fig}.num"
        if name in font or name not in roman:
            continue
        path = pathops.Path()
        roman[name].draw(TransformPen(path.getPen(), (1, 0, tan, 1, 0, 0)))
        add(font, name, path=path, width=roman[name].width)


def superiors(font):
    """All ten superior figures from the numerators, so ¹ and ⁴ match
    (ET Book's own ¹²³ were drawn smaller and narrower)."""
    if "zero.num" not in font:
        return
    for name, fig in [("onesuperior", "one"), ("twosuperior", "two"),
                      ("threesuperior", "three")]:
        glyph = font[name]
        if glyph.contours:
            glyph.clearContours()
            glyph.getPointPen().addComponent(f"{fig}.num", (1, 0, 0, 1, 0, 0))
            glyph.width = font[f"{fig}.num"].width
    for name, (cp, fig) in SUPERIORS.items():
        if not has_codepoint(font, cp):
            add(font, name, cp, width=font[f"{fig}.num"].width,
                components=[(f"{fig}.num", (1, 0, 0, 1, 0, 0))])


def primes(font, log):
    """′ ″ : the straight quote, sloped like a prime."""
    if has_codepoint(font, 0x2032) or "quotesingle" not in font:
        return
    q = to_path(font, "quotesingle")
    x0, y0, x1, y1 = q.bounds
    p = sheared(q, 0.32, about_y=y0)
    px0, _, px1, _ = p.bounds
    side = min(x0, 50)          # the italic quote sits far right in its box
    p = moved(p, side - px0)
    width = round(px1 - px0 + 2 * side)
    add(font, "uni2032", 0x2032, path=p, width=width)
    gap = round((px1 - px0) * 0.35)
    add(font, "uni2033", 0x2033,
        path=union(p, moved(p, round(px1 - px0) + gap)),
        width=width + round(px1 - px0) + gap)
    log("uni2032 uni2033: primes")


def math_signs(font, log):
    """≈ ≠ ≤ ≥ from the font's own math signs, on the math width."""
    w = font["minus"].width
    mx0, my0, mx1, my1 = bounds(font, font["minus"])
    axis = (my0 + my1) / 2
    stroke = my1 - my0
    if not has_codepoint(font, 0x2248) and "asciitilde" in font:
        # Two tildes at 85%, as far apart as the bars of "=".
        t = pathops.Path()
        font["asciitilde"].draw(TransformPen(t.getPen(),
                                             (0.85, 0, 0, 0.85, 0, 0)))
        tx0, ty0, tx1, ty1 = t.bounds
        dx = (w - (tx1 - tx0)) / 2 - tx0
        ex0, ey0, ex1, ey1 = bounds(font, font["equal"])
        gap = (ey1 - ey0) - stroke
        cy = (ty0 + ty1) / 2
        path = union(moved(t, dx, axis - cy + gap / 2),
                     moved(t, dx, axis - cy - gap / 2))
        add(font, "approxequal", 0x2248, path=path, width=w)
    if not has_codepoint(font, 0x2260) and "equal" in font:
        eq = to_path(font, "equal")
        ex0, ey0, ex1, ey1 = eq.bounds
        sl = to_path(font, "slash")
        sx0, sy0, sx1, sy1 = sl.bounds
        s = (ey1 - ey0 + 2 * stroke * 2.2) / (sy1 - sy0)
        sl2 = pathops.Path()
        sl.draw(TransformPen(sl2.getPen(), (s, 0, 0, s, 0, 0)))
        bx0, by0, bx1, by1 = sl2.bounds
        sl2 = moved(sl2, (ex0 + ex1) / 2 - (bx0 + bx1) / 2,
                    (ey0 + ey1) / 2 - (by0 + by1) / 2)
        add(font, "notequal", 0x2260, path=union(eq, sl2), width=w)
    for name, cp, src in [("lessequal", 0x2264, "less"),
                          ("greaterequal", 0x2265, "greater")]:
        if has_codepoint(font, cp) or src not in font:
            continue
        g = to_path(font, src)
        gx0, gy0, gx1, gy1 = g.bounds
        s = 0.86
        g2 = pathops.Path()
        g.draw(TransformPen(g2.getPen(), (1, 0, 0, s, 0, 0)))
        hx0, hy0, hx1, hy1 = g2.bounds
        bar_y0 = gy0
        g2 = moved(g2, 0, bar_y0 + stroke * 2.2 - hy0)
        bar = rect(gx0, bar_y0, gx1, bar_y0 + stroke)
        add(font, name, cp, path=union(g2, bar), width=w)
    log("approxequal notequal lessequal greaterequal")


def arrows(font, log):
    """← ↑ → ↓ ↔ ↩ on the math axis, drawn with the minus' stroke."""
    if has_codepoint(font, 0x2192):
        return
    w = font["minus"].width + 160
    mx0, my0, mx1, my1 = bounds(font, font["minus"])
    axis = (my0 + my1) / 2
    t = (my1 - my0) * 0.9                 # shaft stroke
    side = mx0
    head_len, head_half = 170, 150

    def head(tip_x, direction):
        """A chevron-shaped arrowhead pointing in +x (1) or -x (-1)."""
        back = tip_x - direction * head_len
        inner = tip_x - direction * head_len * 0.72
        return polygon([(tip_x, axis), (back, axis + head_half),
                        (back + direction * t * 0.6, axis + head_half - t * 0.5),
                        (inner, axis),
                        (back + direction * t * 0.6, axis - head_half + t * 0.5),
                        (back, axis - head_half)])

    x0, x1 = side, w - side
    right = union(rect(x0, axis - t / 2, x1 - head_len * 0.5, axis + t / 2),
                  head(x1, 1))
    left = union(rect(x0 + head_len * 0.5, axis - t / 2, x1, axis + t / 2),
                 head(x0, -1))
    both = union(rect(x0 + head_len * 0.5, axis - t / 2,
                      x1 - head_len * 0.5, axis + t / 2),
                 head(x0, -1), head(x1, 1))

    def rotated(path, cx, cy, angle):
        out = pathops.Path()
        c, s = math_cos_sin(angle)
        path.draw(TransformPen(out.getPen(), (c, s, -s, c,
                                              cx - c * cx + s * cy,
                                              cy - s * cx - c * cy)))
        return out

    cx = w / 2
    up = rotated(right, cx, axis, 90)
    down = rotated(right, cx, axis, -90)

    # ↩: a left arrow whose tail hooks up and back over the shaft.
    r_out = 120
    r_in = r_out - t
    hook_cx = x1 - r_out
    axis = axis + 30                      # sit the hook on the x-height band
    low = axis - r_out + t / 2            # shaft centre line, lower run
    circle_out = _circle(hook_cx, axis, r_out)
    circle_in = _circle(hook_cx, axis, r_in)
    arc = pathops.op(pathops.op(circle_out, circle_in,
                                pathops.PathOp.DIFFERENCE),
                     rect(hook_cx, axis - r_out - 1, x1 + 1, axis + r_out + 1),
                     pathops.PathOp.INTERSECTION)
    lower = rect(x0 + head_len * 0.5, low - t / 2, hook_cx + 1, low + t / 2)
    upper = rect(hook_cx - 110, axis + r_out - t, hook_cx + 1, axis + r_out)
    lower_head = moved(head(x0, -1), 0, low - axis)
    hook = union(arc, lower, upper, lower_head)

    for name, cp, path in [("arrowleft", 0x2190, left), ("arrowup", 0x2191, up),
                           ("arrowright", 0x2192, right),
                           ("arrowdown", 0x2193, down),
                           ("arrowboth", 0x2194, both), ("uni21A9", 0x21A9, hook)]:
        add(font, name, cp, path=path, width=w)   # upright, like the math
    log("arrows: ← ↑ → ↓ ↔ ↩")


def math_cos_sin(angle):
    a = math.radians(angle)
    return round(math.cos(a), 6), round(math.sin(a), 6)


def _circle(cx, cy, r, k=0.5523):
    path = pathops.Path()
    pen = path.getPen()
    pen.moveTo((cx + r, cy))
    pen.curveTo((cx + r, cy + k * r), (cx + k * r, cy + r), (cx, cy + r))
    pen.curveTo((cx - k * r, cy + r), (cx - r, cy + k * r), (cx - r, cy))
    pen.curveTo((cx - r, cy - k * r), (cx - k * r, cy - r), (cx, cy - r))
    pen.curveTo((cx + k * r, cy - r), (cx + r, cy - k * r), (cx + r, cy))
    pen.closePath()
    return path


# Raised forms for capitals and lining figures ("case"), and for dashes
# between figures (calt): dashes centred on the capitals/figures, brackets
# and guillemets nudged up.
CASE_SHIFT = {
    "Roman": {"dash": 80, "bracket": 60, "guillemet": 90},
    "Italic": {"dash": 95, "bracket": 60, "guillemet": 90},
}
CASE_GLYPHS = {
    "dash": ["hyphen", "endash", "emdash"],
    "bracket": ["parenleft", "parenright", "bracketleft", "bracketright",
                "braceleft", "braceright"],
    "guillemet": ["guillemotleft", "guillemotright", "guilsinglleft",
                  "guilsinglright"],
}


def case_forms(font, face):
    tan = outline.slant(font)
    for kind, names in CASE_GLYPHS.items():
        dy = CASE_SHIFT[face][kind]
        for name in names:
            if name in font:
                add(font, f"{name}.case", width=font[name].width,
                    components=[(name, (1, 0, 0, 1, round(dy * tan), dy))])


def notdef(font):
    """A visible box, so a missing character is obvious in testing."""
    cap = font.info.capHeight
    w = 500
    box = pathops.op(rect(50, 0, w - 50, cap), rect(100, 50, w - 100, cap - 50),
                     pathops.PathOp.DIFFERENCE)
    glyph = font[".notdef"]
    glyph.clearContours()
    box.draw(glyph.getPen())
    glyph.width = w


def math_widths(font, log):
    """× and ÷ were one unit wider than + − = < >."""
    w = font["plus"].width
    for name in ["multiply", "divide"]:
        if name in font and font[name].width != w:
            d = w - font[name].width
            outline.shift_glyph(font[name], round(d / 2))
            font[name].width = w
            log(f"{name}: width {w}")


def main():
    for face in ["Roman", "Italic"]:
        path = ROOT / "sources" / f"Bolex-{face}.ufo"
        font = ufoLib2.Font.open(path)
        before = len(font)
        log = lambda msg, face=face: print(f"  {face}: {msg}")
        spaces(font)
        components(font)
        if face == "Italic":
            borrow_numerators(font, ufoLib2.Font.open(
                ROOT / "sources" / "Bolex-Roman.ufo"))
        superiors(font)
        primes(font, log)
        math_signs(font, log)
        arrows(font, log)
        case_forms(font, face)
        notdef(font)
        math_widths(font, log)
        font.save()
        print(f"{path.relative_to(ROOT)}: {len(font) - before} glyphs added")


if __name__ == "__main__":
    main()
