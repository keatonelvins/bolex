#!/usr/bin/env python3
"""Fix glyph spacing bugs inherited from ET Book.

These are errors in individual glyphs' sidebearings that no kerning
table should have to compensate for.  Each fix states its target in
terms of another glyph, so the script is idempotent.  Italic sides are
measured upright (deslanted by the italic angle).

Usage: tools/spacing.py
"""
from pathlib import Path

import numpy as np
import ufoLib2

import outline

ROOT = Path(__file__).resolve().parent.parent


def sidebearings(font, name, tan=None):
    xmin, xmax = outline.bounds(font, name, tan)
    return xmin, font[name].width - xmax


def mean_right(font, name, ys=np.arange(50, 401, 10, dtype=float)):
    """Mean upright distance from ink to advance over the x-height rows."""
    _, right = outline.profile(font, name, ys=ys)
    return float(np.nanmean(font[name].width - right))


def mean_left(font, name, ys=np.arange(50, 401, 10, dtype=float)):
    """Mean upright distance from origin to ink over the x-height rows."""
    left, _ = outline.profile(font, name, ys=ys)
    return float(np.nanmean(left))


def stem_left(font, name, ys=(50, 150, 250, 350)):
    """Mean upright x of the first ink at a few heights (an f's stem)."""
    left, _ = outline.profile(font, name, ys=np.array(ys, dtype=float))
    return float(np.mean(left))


def set_lsb(font, name, lsb, tan=None):
    """Move the outline to the given left sidebearing, keeping the right."""
    xmin, rsb = sidebearings(font, name, tan)
    dx = round(lsb - xmin)
    if dx:
        outline.shift_glyph(font[name], dx)
        font[name].width += dx
    return dx


def set_rsb(font, name, rsb, tan=None):
    _, old = sidebearings(font, name, tan)
    d = round(rsb - old)
    font[name].width += d
    return d


def align_f_ligatures(font, log):
    """The f in fi/fj/fl must start where a plain f starts."""
    target = stem_left(font, "f")
    for name in ["f_i", "f_j", "f_l", "f_f", "f_f_i", "f_f_l"]:
        if name in font and not font[name].components:
            dx = round(target - stem_left(font, name))
            if abs(dx) >= 5:
                outline.shift_glyph(font[name], dx)
                font[name].width += dx
                log(f"{name}: f stem aligned with f ({dx:+d})")


def trim_foot_serif(font, log, name, like, top=45):
    """Shorten ``name``'s right foot serif to ``like``'s reach past its
    stem (measured at y=200), compressing the serif toward the stem."""
    def reach(g):
        _, right = outline.profile(font, g, ys=np.array([10.0, 200.0]))
        return right[1], right[0] - right[1]
    stem, ext = reach(name)
    _, target = reach(like)
    if ext - target < 5:
        return
    k = target / ext
    for contour in font[name].contours:
        for p in contour:
            if p.y < top and p.x > stem:
                p.x = round(stem + (p.x - stem) * k)
    log(f"{name}: right foot serif {ext:.0f} -> {target:.0f} past the stem")


def accent_clearance(font, log, names, gap):
    """Raise the accent of these accented letters (the contours above the
    base letter) so it clears the base's top by at least ``gap``."""
    from fontTools.pens.boundsPen import BoundsPen
    for name, base in names:
        if name not in font or base not in font:
            continue
        pen = BoundsPen(font)
        font[base].draw(pen)
        top = pen.bounds[3]
        marks = []
        for contour in font[name].contours:
            if min(p.y for p in contour) > top - 5:
                marks.append(contour)
        if not marks:
            continue
        bottom = min(p.y for c in marks for p in c)
        dy = round(top + gap - bottom)
        if dy > 0:
            for contour in marks:
                for p in contour:
                    p.y += dy
            log(f"{name}: accent raised {dy}")


def lengthen_emdash(font, log, ink):
    """ET Book's em dash was only 1.27x its en dash, so the two read as
    the same mark in prose.  Stretch its middle to ``ink`` units (about
    1.5x the en dash), keeping the rounded ends and the sidebearings."""
    glyph = font["emdash"]
    b = glyph.getBounds(font)
    d = round(ink - (b.xMax - b.xMin))
    if abs(d) < 3:
        return
    cx = (b.xMin + b.xMax) / 2
    for contour in glyph.contours:
        for p in contour:
            if p.x > cx:
                p.x += d
    glyph.width += d
    log(f"emdash: {b.xMax - b.xMin:.0f} -> {ink} units long")


def roman(font, log):
    # AE's left foot hung 69 units outside its advance (lsb -56 vs A 13),
    # colliding with the preceding letter; the same in the small cap.
    for ae, a in [("AE", "A"), ("ae.sc", "a.sc")]:
        a_lsb, _ = sidebearings(font, a)
        dx = set_lsb(font, ae, a_lsb)
        if dx:
            log(f"{ae}: left sidebearing = {a}'s ({dx:+d})")
    # The closing bracket sat 34 units left of centre in its advance
    # (inner sidebearing 32 vs the opening bracket's 65): mirror [.
    lsb, rsb = sidebearings(font, "bracketleft", tan=0)
    r_lsb, r_rsb = sidebearings(font, "bracketright", tan=0)
    if abs(r_lsb - rsb) > 2 or abs(r_rsb - lsb) > 2:
        set_lsb(font, "bracketright", rsb, tan=0)
        set_rsb(font, "bracketright", lsb, tan=0)
        log(f"bracketright: sidebearings {r_lsb:.0f}/{r_rsb:.0f} -> "
            f"{rsb:.0f}/{lsb:.0f} (mirror of bracketleft)")
    # B and E: serifs 30 units longer than H's left their stems ~30 units
    # looser than H's; take back half (the serif tips must not crowd).
    # N: right side 10 looser than H.  m: right side looser than n.
    for name, side, target in [("B", "lsb", 6), ("E", "lsb", 8),
                               ("N", "rsb", 19)]:
        lsb, rsb = sidebearings(font, name)
        current = lsb if side == "lsb" else rsb
        if abs(current - target) > 2:
            (set_lsb if side == "lsb" else set_rsb)(font, name, target)
            log(f"{name}: {side} {current:.0f} -> {target}")
    # m's right foot serif reached 24 units further than n's, so matching
    # m's stem spacing to n's (below) would push that serif into the next
    # letter's.
    trim_foot_serif(font, log, "m", like="n")
    d = round(mean_right(font, "n") - mean_right(font, "m"))
    if abs(d) >= 5:
        font["m"].width += d
        log(f"m: right side matched to n ({d:+d})")
    # Acute, grave and circumflex sat only 22-35 units above the serif tops
    # of i, u and n (eacute and oacute have ~42), so í ú touched the stem
    # once hinted.  The capital tildes were as close.
    accent_clearance(font, log, [
        ("iacute", "dotlessi"), ("igrave", "dotlessi"),
        ("icircumflex", "dotlessi"), ("uacute", "u"), ("ugrave", "u"),
        ("ucircumflex", "u"), ("ntilde", "n")], gap=45)
    accent_clearance(font, log, [
        ("Atilde", "A"), ("Ntilde", "N"), ("Otilde", "O")], gap=35)
    # The period's right sidebearing was 20 (its left 65): with lining
    # figures a decimal point sat against the next digit (1.25), and
    # run-in abbreviations were lopsided (a.m., Ph.D.).
    lsb, rsb = sidebearings(font, "period", tan=0)
    if rsb < 45:
        set_rsb(font, "period", 50, tan=0)
        log(f"period: right sidebearing {rsb:.0f} -> 50")
    lengthen_emdash(font, log, 820)
    align_f_ligatures(font, log)


def italic(font, log):
    lengthen_emdash(font, log, 800)
    align_f_ligatures(font, log)
    # m ends in the same exit stroke as n, but its right side was ~30
    # units looser at every height.
    d = round(mean_right(font, "n") - mean_right(font, "m"))
    if abs(d) >= 5:
        font["m"].width += d
        log(f"m: right side matched to n ({d:+d})")
    d = round(mean_left(font, "n") - mean_left(font, "m"))
    if abs(d) >= 5:
        outline.shift_glyph(font["m"], d)
        font["m"].width += d
        log(f"m: left side matched to n ({d:+d})")
    # Opening quotes: the ink sat ~60 units too far right in the advance,
    # into the top-left of a following capital.  Move it left, keeping the
    # advance (lsb as drawn: 191 -> 131, 204 -> 144).
    for name, target in [("quoteleft", 131), ("quotedblleft", 144)]:
        lsb, _ = sidebearings(font, name, tan=0)
        if abs(lsb - target) > 2:
            outline.shift_glyph(font[name], round(target - lsb))
            log(f"{name}: ink moved left {lsb:.0f} -> {target}")
    # The period sat loose on both sides (81/74 vs the Roman's 65/20),
    # which opened every sentence end.
    lsb, rsb = sidebearings(font, "period", tan=0)
    if lsb > 60:
        set_lsb(font, "period", lsb - 25, tan=0)
        set_rsb(font, "period", rsb - 30, tan=0)
        log(f"period: sidebearings {lsb:.0f}/{rsb:.0f} -> "
            f"{lsb - 25:.0f}/{rsb - 30:.0f}")
    # Guillemets: single ones had ~98-unit sidebearings, doubles were
    # lopsided.  Space them like the Roman's, 35 a side (measured on the
    # outline as drawn: a chevron has no upright stem to measure from).
    for name in ["guilsinglleft", "guilsinglright",
                 "guillemotleft", "guillemotright"]:
        lsb, rsb = sidebearings(font, name, tan=0)
        if abs(lsb - 35) > 2 or abs(rsb - 35) > 2:
            set_lsb(font, name, 35, tan=0)
            set_rsb(font, name, 35, tan=0)
            log(f"{name}: sidebearings {lsb:.0f}/{rsb:.0f} -> 35/35")


def accented_follow_base(font, log):
    """Accented letters are separate outlines in ET Book, so their
    spacing drifts from the base letter's (Ž 15 units looser than Z, Ý
    13) and a fix to E or N doesn't reach É or Ñ.  Measure both over the
    base letter's own rows and give the accented letter the base's
    sidebearings."""
    import unicodedata
    by_codepoint = {u: g.name for g in font for u in g.unicodes}
    for glyph in list(font):
        stem, _, suffix = glyph.name.partition(".")
        if suffix not in ("", "sc") or stem not in font \
                or not font[stem].unicodes:
            continue
        parts = unicodedata.normalize("NFD", chr(font[stem].unicodes[0]))
        if len(parts) < 2 or ord(parts[0]) not in by_codepoint:
            continue
        base = by_codepoint[ord(parts[0])] + (f".{suffix}" if suffix else "")
        if base not in font or base == glyph.name:
            continue
        b = font[base].getBounds(font)
        ys = np.arange(max(b.yMin, 0) + 10, b.yMax - 10, 5, dtype=float)
        bl, br = outline.profile(font, base, ys=ys)
        al, ar = outline.profile(font, glyph.name, ys=ys)
        if np.all(np.isnan(al)):
            continue
        dx = round(np.nanmin(bl) - np.nanmin(al))
        width = round(np.nanmax(ar) + dx + font[base].width - np.nanmax(br))
        if abs(dx) >= 3 or abs(width - glyph.width) >= 3:
            outline.shift_glyph(glyph, dx)
            log(f"{glyph.name}: spaced like {base} "
                f"(shift {dx:+d}, width {glyph.width} -> {width})")
            glyph.width = width


def sync_composites(font, log):
    """Composites that are a single unshifted component (fi = f_i) keep
    their base's advance."""
    for glyph in font:
        if len(glyph.components) == 1 and not glyph.contours:
            c = glyph.components[0]
            if tuple(c.transformation) == (1, 0, 0, 1, 0, 0):
                w = font[c.baseGlyph].width
                if glyph.width != w:
                    glyph.width = w
                    log(f"{glyph.name}: advance follows {c.baseGlyph}")


def main():
    for face, fix in [("Roman", roman), ("Italic", italic)]:
        path = ROOT / "sources" / f"Bolex-{face}.ufo"
        font = ufoLib2.Font.open(path)
        log = lambda msg, face=face: print(f"  {face}: {msg}")
        fix(font, log)
        accented_follow_base(font, log)
        sync_composites(font, log)
        font.save()


if __name__ == "__main__":
    main()
