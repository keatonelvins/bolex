#!/usr/bin/env python3
"""Import the Roman and Italic masters from an ET Book checkout.

This is a one-time, reproducible import: it reads the UFOs from
keaton-elv/et-book (``ufo/ETBook-Roman.ufo`` and ``ufo/ETBook-Italic.ufo``)
and writes clean ``sources/Bolex-Roman.ufo`` and ``sources/Bolex-Italic.ufo``.
Everything after the import (figures, small caps, kerning) is done by the
other scripts in ``tools/`` against the Bolex sources.

What the import does:

* drops Glyphs.app-specific lib keys and glyph libs;
* repairs malformed contours (a line segment preceded by an off-curve
  point, found in the Italic ``dcroat`` and ``f_j``) by reading them as the
  quadratic curves they were meant to be;
* maps glyphs that were missing their code points (no-break space,
  superior figures);
* renames the family to Bolex and sets the metadata ufo2ft needs to build
  correct name/OS/2/hhea/post tables directly (so no post-processing step);
* converts the kerning from hand-written ``feature kern`` blocks into
  ``kerning.plist``, so ufo2ft builds the kern feature;
* keeps only the Western European character set (``CHARSET``) and drops
  the Central European letters, extra fractions and florin that the
  et-book fork had added, along with their small caps;
* drops the Bold, Semibold, Display Italic and Expert faces entirely.

Usage: tools/import_etbook.py PATH/TO/et-book
"""
import re
import sys
from pathlib import Path

import ufoLib2
from fontTools.pens.pointPen import AbstractPointPen

ROOT = Path(__file__).resolve().parent.parent
SOURCES = ROOT / "sources"

FACES = {
    "Roman": dict(
        style="Roman", style_map="regular", ps="Bolex-Roman",
        italic_angle=0, src_kerning="features.fea",
        copyright_year="2002"),
    "Italic": dict(
        style="Italic", style_map="italic", ps="Bolex-Italic",
        italic_angle=-11.8, src_kerning="kerning.fea",
        copyright_year="2004"),
}

# Western European: ASCII, Latin-1, the Windows-1252 additions (Œ œ Š š
# Ž ž Ÿ € ‰ ‹ › ...), dotless i, the spacing accents, the fraction slash,
# minus and the fi/fl presentation forms.  tools/glyphs.py adds a few
# typographic extras on top (spaces, primes, arrows, superiors).
CHARSET = (set(range(0x20, 0x7F)) | set(range(0xA0, 0x100)) | {
    0x0131, 0x0152, 0x0153, 0x0160, 0x0161, 0x0178, 0x017D, 0x017E,
    0x02C6, 0x02C7, 0x02D8, 0x02D9, 0x02DA, 0x02DB, 0x02DC, 0x02DD,
    0x2013, 0x2014, 0x2018, 0x2019, 0x201A, 0x201C, 0x201D, 0x201E,
    0x2020, 0x2021, 0x2022, 0x2026, 0x2030, 0x2039, 0x203A, 0x2044,
    0x20AC, 0x2122, 0x2212, 0xFB01, 0xFB02,
}) - {0x00AD}   # soft hyphen: browsers handle it without a glyph

# Glyphs that shipped without a code point in ET Book.
MISSING_UNICODES = {
    "uni00A0": 0x00A0,
    "onesuperior": 0x00B9,
    "twosuperior": 0x00B2,
    "threesuperior": 0x00B3,
}

# Family-wide vertical metrics, shared so that the line box and baseline
# do not move when roman and italic are mixed.  ET Book's 736/-264 plus a
# 200-unit line gap, with the gap folded into the ascender and descender:
# line-height: normal stays 1.2 and the baseline sits in the same place at
# any explicit line-height, but inline backgrounds and clipped headings
# now cover accents and descenders.  (Win metrics are set at build time
# from the glyphs' real extents.)
VERTICAL = dict(
    unitsPerEm=1000,
    ascender=836,
    descender=-364,
    openTypeHheaAscender=836,
    openTypeHheaDescender=-364,
    openTypeHheaLineGap=0,
    openTypeOS2TypoAscender=836,
    openTypeOS2TypoDescender=-364,
    openTypeOS2TypoLineGap=0,
)


class _FixPointPen(AbstractPointPen):
    """Record contours, turning ``offcurve* line`` into proper curves."""

    def __init__(self):
        self.contours = []
        self.components = []

    def beginPath(self, identifier=None, **kwargs):
        self._pts = []

    def addPoint(self, pt, segmentType=None, smooth=False, name=None,
                 identifier=None, **kwargs):
        self._pts.append([pt, segmentType, smooth])

    def endPath(self):
        self.contours.append(self._pts)

    def addComponent(self, glyphName, transformation, identifier=None,
                     **kwargs):
        self.components.append((glyphName, transformation))


def _repair(contour):
    """Return contour with every ``offcurve line`` read as a quadratic."""
    n = len(contour)
    out = []
    for i, (pt, seg, smooth) in enumerate(contour):
        out.append([pt, seg, smooth])
    changed = True
    while changed:
        changed = False
        n = len(out)
        for i in range(n):
            pt, seg, smooth = out[i]
            prev = out[i - 1]
            if seg == "line" and prev[1] is None:
                # Count the run of off-curves before this point.
                run = 0
                while out[(i - 1 - run) % n][1] is None:
                    run += 1
                if run == 1:
                    # Quadratic (p0, q, p2) -> cubic by degree elevation.
                    p0 = out[(i - 2) % n][0]
                    q = prev[0]
                    p2 = pt
                    c1 = (p0[0] + 2 / 3 * (q[0] - p0[0]),
                          p0[1] + 2 / 3 * (q[1] - p0[1]))
                    c2 = (p2[0] + 2 / 3 * (q[0] - p2[0]),
                          p2[1] + 2 / 3 * (q[1] - p2[1]))
                    c1 = (round(c1[0]), round(c1[1]))
                    c2 = (round(c2[0]), round(c2[1]))
                    out[(i - 1) % n] = [c1, None, False]
                    out.insert(i, [c2, None, False])
                    out[i + 1][1] = "curve"
                else:
                    out[i][1] = "curve"
                changed = True
                break
    return out


def _parse_pairs(fea_text):
    pairs = {}
    for m in re.finditer(r"^\s*pos(?:ition)?\s+\\?(\S+)\s+\\?(\S+)\s+(-?\d+)\s*;",
                         fea_text, re.M):
        left, right, value = m.group(1), m.group(2), int(m.group(3))
        pairs[(left, right)] = value
    return pairs


def _kern_block(fea_text):
    m = re.search(r"feature kern \{(.*?)\} kern;", fea_text, re.S)
    return m.group(1) if m else ""


def import_face(etbook, face):
    spec = FACES[face]
    src = etbook / "ufo" / f"ETBook-{face}.ufo"
    font = ufoLib2.Font.open(src, lazy=False, validate=False)

    # --- outlines -------------------------------------------------------
    for glyph in font:
        pen = _FixPointPen()
        glyph.drawPoints(pen)
        repaired = [_repair(c) for c in pen.contours]
        if repaired != pen.contours:
            print(f"  {face}: repaired contour structure in {glyph.name}")
            glyph.clearContours()
            ppen = glyph.getPointPen()
            for contour in repaired:
                ppen.beginPath()
                for pt, seg, smooth in contour:
                    ppen.addPoint(pt, segmentType=seg, smooth=smooth)
                ppen.endPath()
        glyph.lib.clear()
        glyph.guidelines = []

    for name, uni in MISSING_UNICODES.items():
        if name in font and not font[name].unicodes:
            font[name].unicodes = [uni]

    # --- character set -------------------------------------------------
    dropped = {g.name for g in font
               if g.unicodes and not set(g.unicodes) & CHARSET}
    # Unencoded variants (x.sc ...) go with their base glyph.
    dropped |= {g.name for g in font if not g.unicodes and "." in g.name
                and g.name.split(".")[0] in dropped}
    for name in dropped:
        del font[name]
    print(f"  {face}: dropped {len(dropped)} glyphs outside the character set")

    # --- kerning --------------------------------------------------------
    fea_path = src / spec["src_kerning"]
    pairs = _parse_pairs(_kern_block(fea_path.read_text()))
    font.kerning.clear()
    for (left, right), value in sorted(pairs.items()):
        if "space" in (left, right):
            continue  # kerning against the space breaks justification
        if left not in font or right not in font:
            continue
        font.kerning[(left, right)] = value

    # --- features (rewritten later by tools/features.py) ---------------
    font.features.text = ""

    # --- lib ------------------------------------------------------------
    order = font.lib.get("public.glyphOrder", [])
    ps_names = font.lib.get("public.postscriptNames", {})
    font.lib.clear()
    font.lib["public.glyphOrder"] = [g for g in order if g in font]
    if ps_names:
        font.lib["public.postscriptNames"] = ps_names

    # --- info -----------------------------------------------------------
    old = font.info
    info = ufoLib2.objects.Info()
    info.familyName = "Bolex"
    info.styleName = spec["style"]
    info.styleMapFamilyName = "Bolex"
    info.styleMapStyleName = spec["style_map"]
    info.postscriptFontName = spec["ps"]
    info.postscriptFullName = f"Bolex {spec['style']}"
    info.versionMajor = 1
    info.versionMinor = 0
    info.openTypeHeadCreated = "2026/10/31 00:00:00"   # reproducible builds
    info.copyright = (
        f"ET Bembo designed for Edward Tufte / Graphics Press (c) "
        f"{spec['copyright_year']} Dmitry Krasny / Deka Design. "
        "Bolex modifications (c) 2026 Keaton Elvins."
    )
    info.openTypeNameLicense = (
        "MIT License. See https://github.com/keatonelvins/bolex")
    info.openTypeNameLicenseURL = "https://opensource.org/license/mit"
    info.openTypeNameDesigner = (
        "Dmitry Krasny, Bonnie Scranton, Edward Tufte")
    info.openTypeNameDescription = (
        "Bolex is a clean, minimal cut of ET Book (ET Bembo) for long-form "
        "reading on the web.")
    info.openTypeOS2WeightClass = 400
    info.openTypeOS2WidthClass = 5
    info.openTypeOS2Type = []          # fsType 0: installable embedding
    info.openTypeOS2Selection = [7]    # USE_TYPO_METRICS
    info.italicAngle = spec["italic_angle"]
    info.postscriptUnderlinePosition = old.postscriptUnderlinePosition
    info.postscriptUnderlineThickness = old.postscriptUnderlineThickness
    for key, value in VERTICAL.items():
        setattr(info, key, value)
    # x-height and cap height measured from the outlines.
    from fontTools.pens.boundsPen import BoundsPen

    def top(name):
        bp = BoundsPen(font)
        font[name].draw(bp)
        return round(bp.bounds[3])
    info.xHeight = top("x")
    info.capHeight = top("H")
    font.info = info

    dst = SOURCES / f"Bolex-{face}.ufo"
    font.save(dst, overwrite=True, validate=True)
    print(f"wrote {dst.relative_to(ROOT)}: {len(font)} glyphs, "
          f"{len(font.kerning)} kerning pairs")


def main():
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    etbook = Path(sys.argv[1])
    SOURCES.mkdir(exist_ok=True)
    for face in FACES:
        import_face(etbook, face)


if __name__ == "__main__":
    main()
