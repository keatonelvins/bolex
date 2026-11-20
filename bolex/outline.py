"""Outline geometry shared by the spacing and kerning tools.

A glyph's *profile* is, for each sampled height y, the x of its leftmost
and rightmost ink.  Italic glyphs are measured upright: the outline is
deslanted by the italic angle first, so a slanted stem reads as a
straight one.
"""

import math

import numpy as np
from fontTools.pens.basePen import BasePen
from fontTools.pens.transformPen import TransformPen

# Heights sampled for every profile, in font units (descender..ascender).
Y_MIN, Y_MAX, Y_STEP = -300, 800, 5
YS = np.arange(Y_MIN, Y_MAX + 1, Y_STEP, dtype=float)


class _SegmentPen(BasePen):
    """Flatten an outline into straight segments."""

    def __init__(self, glyphset=None, steps=16):
        super().__init__(glyphset)
        self.segments = []
        self.steps = steps

    def _moveTo(self, p):
        self._start = self._cur = p

    def _lineTo(self, p):
        self.segments.append((self._cur, p))
        self._cur = p

    def _curveToOne(self, p1, p2, p3):
        p0 = self._cur
        prev = p0
        for i in range(1, self.steps + 1):
            t = i / self.steps
            mt = 1 - t
            x = mt**3 * p0[0] + 3 * mt * mt * t * p1[0] + 3 * mt * t * t * p2[0] + t**3 * p3[0]
            y = mt**3 * p0[1] + 3 * mt * mt * t * p1[1] + 3 * mt * t * t * p2[1] + t**3 * p3[1]
            self.segments.append((prev, (x, y)))
            prev = (x, y)
        self._cur = p3

    def _qCurveToOne(self, p1, p2):
        p0 = self._cur
        c1 = (p0[0] + 2 / 3 * (p1[0] - p0[0]), p0[1] + 2 / 3 * (p1[1] - p0[1]))
        c2 = (p2[0] + 2 / 3 * (p1[0] - p2[0]), p2[1] + 2 / 3 * (p1[1] - p2[1]))
        self._curveToOne(c1, c2, p2)

    def _closePath(self):
        if self._cur != self._start:
            self.segments.append((self._cur, self._start))

    _endPath = _closePath


class CubicPen(BasePen):
    """Forward an outline to ``pen``, turning quadratic segments (which
    pathops can emit) into cubics, so the drawings stay all-cubic."""

    def __init__(self, pen):
        super().__init__(None)
        self.pen = pen

    def _moveTo(self, p):
        self.pen.moveTo(p)

    def _lineTo(self, p):
        self.pen.lineTo(p)

    def _curveToOne(self, p1, p2, p3):
        self.pen.curveTo(p1, p2, p3)

    def _qCurveToOne(self, p1, p2):
        p0 = self._getCurrentPoint()
        c1 = (p0[0] + 2 / 3 * (p1[0] - p0[0]), p0[1] + 2 / 3 * (p1[1] - p0[1]))
        c2 = (p2[0] + 2 / 3 * (p1[0] - p2[0]), p2[1] + 2 / 3 * (p1[1] - p2[1]))
        self.pen.curveTo(c1, c2, p2)

    def _closePath(self):
        self.pen.closePath()

    def _endPath(self):
        self.pen.endPath()


def slant(font):
    """tan of the font's italic angle (positive for a right-leaning italic)."""
    angle = font.info.italicAngle or 0
    return math.tan(math.radians(-angle))


def profile(font, name, tan=None, ys=YS):
    """Return (left, right) arrays of ink extremes per height (NaN = no ink)."""
    if tan is None:
        tan = slant(font)
    pen = _SegmentPen(font)
    font[name].draw(TransformPen(pen, (1, 0, -tan, 1, 0, 0)))
    left = np.full(len(ys), np.nan)
    right = np.full(len(ys), np.nan)
    if not pen.segments:
        return left, right
    seg = np.array([(a[0], a[1], b[0], b[1]) for a, b in pen.segments])
    x0, y0, x1, y1 = seg.T
    for i, y in enumerate(ys):
        hit = ((y0 <= y) & (y < y1)) | ((y1 <= y) & (y < y0))
        if not hit.any():
            continue
        t = (y - y0[hit]) / (y1[hit] - y0[hit])
        xs = x0[hit] + t * (x1[hit] - x0[hit])
        left[i] = xs.min()
        right[i] = xs.max()
    return left, right


def bounds(font, name, tan=None):
    """Upright (deslanted) horizontal ink extent: (xmin, xmax) or None."""
    left, right = profile(font, name, tan)
    if np.all(np.isnan(left)):
        return None
    return float(np.nanmin(left)), float(np.nanmax(right))


def shift_glyph(glyph, dx):
    for contour in glyph.contours:
        for point in contour:
            point.x += dx
    for component in glyph.components:
        t = component.transformation
        component.transformation = (t[0], t[1], t[2], t[3], t[4] + dx, t[5])
    for anchor in glyph.anchors:
        anchor.x += dx


def set_sidebearings(font, name, lsb, rsb, tan=None):
    """Move the outline and set the advance so the upright extents give
    the requested sidebearings."""
    xmin, xmax = bounds(font, name, tan)
    glyph = font[name]
    shift_glyph(glyph, round(lsb - xmin))
    glyph.width = round(lsb) + round(xmax - xmin) + round(rsb)
