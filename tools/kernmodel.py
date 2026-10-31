"""A small geometric model of how much a pair of glyphs needs kerning.

For a pair L R, at every height where *both* glyphs have ink, take the
horizontal white between L's right edge and R's left edge, each side's
depth capped some distance beyond that side's outermost point (an open
side or a deep counter reads as open, not as infinitely far).  Two
numbers describe the pair:

* ``area``: the mean of those gaps (how much white sits between them in
  the rows they share), and
* ``closest``: the smallest gap (where they come nearest).

Neither number means anything on its own -- an ``o`` is rounder than an
``n`` and is spaced for it.  So each glyph side is also measured against
a neutral partner in its own home context (``H`` for capitals, ``n`` for
lowercase, ``h.sc`` for small capitals, the zero for figures), and only
the *interaction* is kept:

    X(L, R) = f(L, R) - f(refL, refR) - [f(L, home) - f(home, home)]
                                      - [f(home, R) - f(home, home)]

so the designer's sidebearings are taken as correct and a pair is kerned
only when its two shapes leave more (or less) white together than their
spacing alone implies: the cave under a T's arm above an x-height
letter, two parallel diagonals in AV, a period beside a V's open foot.

The kern is a linear combination of the two interaction terms with
coefficients per *category* (capital-lowercase, punctuation-capital,
...), fitted on the hand kerning of well-kerned Garalde typefaces and
checked against ET Book's original pairs; see tools/kerning.py.
"""
import numpy as np

import outline

# Character categories, by the role a glyph plays in a pair.
CAP, LOWER, SMALLCAP, FIGURE, OLDSTYLE, PUNCT, QUOTE, LOWPUNCT = (
    "cap", "lower", "smallcap", "figure", "oldstyle", "punct", "quote",
    "lowpunct")

# Neutral partner per category: (as the left glyph, as the right glyph).
HOME = {
    CAP: "H", LOWER: "n", SMALLCAP: "h.sc", FIGURE: "zero",
    OLDSTYLE: "zero.osf", LOWPUNCT: "n", PUNCT: "H", QUOTE: "H",
}


# Serifs are thin horizontal protrusions; the eye spaces stems, not serif
# tips.  Each side profile is "closed" over SERIF_ROWS units of height
# (narrow valleys filled in), but by at most SERIF_DEPTH units so long
# arms and terminals (T, E, F, r, f) keep their reach.
SERIF_ROWS = 60
SERIF_DEPTH = 100


def _close(d, rows=SERIF_ROWS, depth=SERIF_DEPTH):
    k = max(1, int(round(rows / outline.Y_STEP / 2)))
    ink = ~np.isnan(d)
    if not ink.any():
        return d
    filled = np.where(ink, d, np.inf)
    n = len(d)
    dil = np.array([np.max(filled[max(0, i - k):i + k + 1]) for i in range(n)])
    clo = np.array([np.min(dil[max(0, i - k):i + k + 1]) for i in range(n)])
    out = np.where(ink, np.minimum(np.maximum(d, clo), d + depth), np.nan)
    return out


class Sides:
    """Per-glyph side profiles for one font."""

    def __init__(self, font, names, tan=None):
        self.tan = outline.slant(font) if tan is None else tan
        self.left = {}    # origin -> ink, per row (NaN where no ink)
        self.right = {}   # ink -> advance, per row
        self.left_raw = {}
        self.right_raw = {}
        for name in names:
            lft, rgt = outline.profile(font, name, self.tan)
            self.left_raw[name] = lft
            self.right_raw[name] = font[name].width - rgt
            self.left[name] = _close(self.left_raw[name])
            self.right[name] = _close(self.right_raw[name])

    def capped(self, name, side, depth):
        d = self.left[name] if side == "left" else self.right[name]
        if np.all(np.isnan(d)):
            return d
        return np.minimum(d, np.nanmin(d) + depth)


def _rows(sides, left, right, depth):
    a = sides.capped(left, "right", depth)
    b = sides.capped(right, "left", depth)
    both = ~np.isnan(a) & ~np.isnan(b)
    return a[both] + b[both]


def area(sides, left, right, depth):
    g = _rows(sides, left, right, depth)
    return float(g.mean()) if len(g) else None


def closest(sides, left, right, depth=10000):
    g = _rows(sides, left, right, depth)
    return float(g.min()) if len(g) else None


def interaction(fn, sides, left, right, home_left, home_right, depth):
    """fn(L,R) relative to what L's and R's spacing implies."""
    terms = [
        fn(sides, left, right, depth),
        fn(sides, home_left, home_right, depth),
        fn(sides, left, home_left, depth),
        fn(sides, home_left, home_left, depth),
        fn(sides, home_right, right, depth),
        fn(sides, home_right, home_right, depth),
    ]
    if any(t is None for t in terms):
        return None
    lr, ref, lh, hh, hr, rr = terms
    return lr - ref - (lh - hh) - (hr - rr)


def clearance(sides, left, right, kern=0.0, window=60):
    """Approximate 2D distance between the two outlines, after ``kern``.

    Compares L's right edge at each height with R's left edge at heights
    up to ``window`` units away: a horizontal gap dx at a vertical offset
    dy is sqrt(dx^2 + dy^2) apart, and overlapping columns at different
    heights are dy apart.  Same-row overlap gives a negative distance.
    """
    a = sides.right_raw[left]
    b = sides.left_raw[right]
    if np.all(np.isnan(a)) or np.all(np.isnan(b)):
        return None
    if np.nanmin(a) + np.nanmin(b) + kern >= window:
        return float(np.nanmin(a) + np.nanmin(b) + kern)   # far apart
    k = int(round(window / outline.Y_STEP))
    best = None
    for shift in range(-k, k + 1):
        if shift >= 0:
            aa, bb = a[shift:], b[:len(b) - shift]
        else:
            aa, bb = a[:shift], b[-shift:]
        both = ~np.isnan(aa) & ~np.isnan(bb)
        if not both.any():
            continue
        dx = aa[both] + bb[both] + kern
        dy = abs(shift) * outline.Y_STEP
        if dy == 0:
            d = dx
        else:
            d = np.where(dx > 0, np.sqrt(dx * dx + dy * dy), dy)
        m = float(d.min())
        best = m if best is None else min(best, m)
    return best
