"""Add f.short and f_f.short: an f whose hook stops nearer its advance.

The f's hook overhangs its advance by ~120 units in the Roman and ~160 in
the Italic, so before ) ] } ? ! ' " and tall accents it collides, and the
kerning needed to clear it leaves a hole at the baseline.

* Roman: the hook's terminal is pulled back SHORTEN units, keeping its
  shape; the arch between stem and terminal is drawn in proportionally.
* Italic: its hook curls back on itself, so instead the part of the hook
  right of the stem is narrowed (HOOK_SCALE), which keeps every curve.

``calt`` (features.py) uses f.short before those characters and,
in the Italic, at the end of every word: an italic word is usually
followed by roman punctuation, (<em>of</em>) or <em>staff</em>'s, and
kerning cannot act across the two fonts.
"""

import numpy as np

from . import outline

SHORTEN = {"Roman": 80}
HOOK_SCALE = {"Italic": 0.4}
HOOK_FLOOR = 560  # only the hook (above the crossbar) is touched
TERMINAL = 80  # the last ~80 units of the hook move as a whole


def shorten(font, src, dst, delta):
    """Pull the (last) hook's terminal back by ``delta``: points past the
    stem shift left by a smoothstep of their distance from it, and each
    off-curve point moves with its on-curve point so tangents stay
    smooth."""
    tan = outline.slant(font)
    glyph = font[src].copy()
    # The last stem's left edge, just above the floor: nothing left of it
    # (the first f of ff) moves.
    _, right = outline.profile(font, src, tan, ys=np.array([HOOK_FLOOR + 10.0]))
    hook = [p for c in glyph.contours for p in c if p.y > HOOK_FLOOR]
    upright = lambda p: p.x - p.y * tan
    x_max = max(upright(p) for p in hook)
    x_start = float(right[0]) - 60
    x_term = x_max - TERMINAL

    def shift(p):
        if p.y <= HOOK_FLOOR:
            return 0
        t = min(1.0, max(0.0, (upright(p) - x_start) / (x_term - x_start)))
        t = t * t * (3 - 2 * t)  # smoothstep
        fade = min(1.0, (p.y - HOOK_FLOOR) / 40)
        return -delta * t * fade

    for contour in glyph.contours:
        pts = list(contour)
        n = len(pts)
        on = [shift(p) if p.type else None for p in pts]
        dxs = []
        for i, p in enumerate(pts):
            if p.type:
                dxs.append(on[i])
            else:
                # An off-curve handle belongs to the on-curve point it
                # touches: the previous one if that is on-curve, else the
                # next.
                prev = pts[i - 1]
                dxs.append(on[i - 1] if prev.type else on[(i + 1) % n])
        for p, dx in zip(pts, dxs):
            p.x = round(p.x + (dx or 0))
    _insert(font, glyph, dst)


def narrow(font, src, dst, scale):
    """Narrow the hook right of the (last) stem; fade in over 60 units
    above the floor so the stem is untouched."""
    tan = outline.slant(font)
    glyph = font[src].copy()
    _, right = outline.profile(font, src, tan, ys=np.array([HOOK_FLOOR + 10.0]))
    pivot = float(right[0])
    for contour in glyph.contours:
        for p in contour:
            if p.y <= HOOK_FLOOR:
                continue
            u = p.x - p.y * tan
            if u <= pivot:
                continue
            s = 1 - (1 - scale) * min(1.0, (p.y - HOOK_FLOOR) / 60)
            p.x = round(pivot + (u - pivot) * s + p.y * tan)
    _insert(font, glyph, dst)


def overhang(font, name):
    b = font[name].getBounds(font)
    return b.xMax - font[name].width


def _insert(font, glyph, dst):
    glyph._name = dst
    if dst in font:
        del font[dst]
    font.layers.defaultLayer.insertGlyph(glyph, dst, copy=False)
    font[dst].unicodes = []
    order = font.lib.setdefault("public.glyphOrder", [])
    if dst not in order:
        order.append(dst)


def add(font, face):
    for src, dst in [("f", "f.short"), ("f_f", "f_f.short")]:
        if face in SHORTEN:
            shorten(font, src, dst, SHORTEN[face])
        elif src == "f":
            narrow(font, src, dst, HOOK_SCALE[face])
        else:
            # ff's hook overhangs further than f's: narrow it until its
            # overhang matches f.short's.
            target = overhang(font, "f.short")
            scale = HOOK_SCALE[face]
            narrow(font, src, dst, scale)
            while overhang(font, dst) > target + 3 and scale > 0.05:
                scale -= 0.02
                narrow(font, src, dst, scale)
