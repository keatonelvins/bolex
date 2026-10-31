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
            if abs(dx) >= 10:
                outline.shift_glyph(font[name], dx)
                font[name].width += dx
                log(f"{name}: f stem aligned with f ({dx:+d})")


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
    d = round(mean_right(font, "n") - mean_right(font, "m"))
    if abs(d) >= 5:
        font["m"].width += d
        log(f"m: right side matched to n ({d:+d})")
    align_f_ligatures(font, log)


def italic(font, log):
    align_f_ligatures(font, log)
    # m ends in the same exit stroke as n, but its right side was ~30
    # units looser at every height.
    d = round(mean_right(font, "n") - mean_right(font, "m"))
    if abs(d) >= 5:
        font["m"].width += d
        log(f"m: right side matched to n ({d:+d})")
    # Opening quotes sat ~60 units closer to a following capital than in
    # the Roman (the slant tucks them into the cap's top-left serif);
    # open them up by 40 on the right.
    for name, target in [("quoteleft", 119), ("quotedblleft", 115)]:
        _, rsb = sidebearings(font, name)
        if rsb < target - 2:
            set_rsb(font, name, target)
            log(f"{name}: right sidebearing {rsb:.0f} -> {target}")
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
        sync_composites(font, log)
        font.save()


if __name__ == "__main__":
    main()
