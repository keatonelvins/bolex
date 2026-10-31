#!/usr/bin/env python3
"""Generate kerning for the Bolex sources.

ET Book shipped with ~100 hand-made pairs in the Roman (capitals T V W Y
A R U before lowercase) and 10 in the Italic.  This script measures every
relevant pair with the geometric model in tools/kernmodel.py, blends in
the designers' values where they exist (ET Book's, and ETbb's: Michael
Sharpe's thorough re-kerning of the same outlines), applies hand
overrides, guards against collisions, and writes compact class kerning (base-letter groups
plus exceptions where an accent or tail changes a pair) to each UFO's
groups.plist and kerning.plist.

Inputs (all under sources/kerning/):
    etbook-<face>.txt     ET Book's original pairs
    etbb-<face>.txt       Michael Sharpe's ETbb pairs, scaled to Bolex
                          (tools/etbb_kerning.py); together the
                          designers' opinion, blended 50/50 with the
                          model, which also smooths their noise
    overrides-<face>.txt  final say: "LEFT RIGHT VALUE" per line.  The
                          named pair gets VALUE and every pair in the same
                          two kerning groups moves by the same amount
                          (accented forms follow their base letter)

Usage: tools/kerning.py [roman|italic ...]
"""
import sys
import unicodedata
from collections import defaultdict
from pathlib import Path

import ufoLib2

import kernmodel as km
from kernmodel import (CAP, DASH, FIGURE, LOWER, LOWPUNCT, OLDSTYLE, PUNCT,
                       QUOTE, SMALLCAP)

ROOT = Path(__file__).resolve().parent.parent
KERN_DIR = ROOT / "sources" / "kerning"

# Model: depth of white counted beyond each side's outermost point, and the
# share of the extra (or missing) white that kerning compensates.  Fitted
# on the hand kerning of EB Garamond (capital-capital: area 0.26, closest
# 0.26; capital-lowercase: 0.41, 0.27) and checked against ET Book's own
# pairs.  One setting is used everywhere, a little above the regression
# (which is pulled toward zero by the many pairs designers leave
# unkerned), so that categories differ only by geometry.
AREA_DEPTH = 200
CLOSEST_DEPTH = 400
AREA_WEIGHT = 0.25
CLOSEST_WEIGHT = 0.35

THRESHOLD = 15       # smaller kerns are invisible at text sizes
ROUND_TO = 5
MAX_NEGATIVE = -150
MIN_CLEARANCE = 25   # closest approach of the outlines after kerning
CONTACT = 20         # closer than this unkerned counts as touching
DESIGNER_WEIGHT = 0.5
EXCEPTION_TOLERANCE = 10  # members within this of their group's value share it

# Per category pair: scale applied to the model (0 = not kerned).
# Lowercase-lowercase spacing was drawn with care in ET Book; only strong
# interactions (r. v, y, f') pass the threshold at half strength.
SCALE = defaultdict(float, {
    (CAP, CAP): 1.0, (CAP, LOWER): 1.0,
    (LOWER, LOWER): 0.5,
    (CAP, LOWPUNCT): 1.0, (CAP, PUNCT): 0.8, (CAP, QUOTE): 0.8,
    (LOWPUNCT, CAP): 0.4, (PUNCT, CAP): 0.8, (QUOTE, CAP): 0.8,
    # Dashes sit in the middle of open shapes (C, e, L): kerning them by
    # the white they leave would pull them into the counter.  The model
    # leaves them alone (as ETbb and fbb do); the open capitals T Y V W L
    # are set by hand in the overrides.
    # Quotes beside lowercase are left to the spacing (and the collision
    # guard): measured only where both have ink, a quote sees the stem of
    # an ascender (d b h k) rather than the bowl or shoulder below it.
    (LOWER, LOWPUNCT): 0.7, (LOWER, PUNCT): 0.6,
    (LOWPUNCT, LOWER): 0.7, (PUNCT, LOWER): 0.6,
    (SMALLCAP, SMALLCAP): 1.0, (CAP, SMALLCAP): 0.8,
    (SMALLCAP, LOWPUNCT): 0.8, (SMALLCAP, PUNCT): 0.6,
    (SMALLCAP, QUOTE): 0.6, (LOWPUNCT, SMALLCAP): 0.4,
    (PUNCT, SMALLCAP): 0.6, (QUOTE, SMALLCAP): 0.6,
    (FIGURE, FIGURE): 0.6, (FIGURE, LOWPUNCT): 0.6, (LOWPUNCT, FIGURE): 0.6,
    (FIGURE, PUNCT): 0.5, (PUNCT, FIGURE): 0.5,
    (OLDSTYLE, OLDSTYLE): 0.6, (OLDSTYLE, LOWPUNCT): 0.6,
    (LOWPUNCT, OLDSTYLE): 0.6,
})

LOWPUNCT_NAMES = {"period", "comma", "colon", "semicolon", "ellipsis"}
DASH_NAMES = {"hyphen", "endash", "emdash"}
QUOTE_NAMES = {"quoteleft", "quoteright", "quotedblleft", "quotedblright",
               "quotesingle", "quotedbl"}
PUNCT_NAMES = {"parenleft", "parenright", "bracketleft", "bracketright",
               "braceleft", "braceright", "question", "exclam",
               "questiondown", "exclamdown", "slash", "backslash",
               "ampersand", "asterisk", "guillemotleft", "guillemotright",
               "guilsinglleft", "guilsinglright", "quotesinglbase",
               "quotedblbase", "dagger", "daggerdbl"}
NOT_KERNED = {"mu"}   # a symbol that happens to be a letter
# Code points that share another glyph's role.
ALIASES = {"uni2010": "hyphen", "uni2011": "hyphen", "uni2012": "hyphen.case",
           "uni02BB": "quoteleft", "uni02BC": "quoteright"}
FIGURES = ["zero", "one", "two", "three", "four",
           "five", "six", "seven", "eight", "nine"]

# Glyphs whose sides follow another letter's group (left side, right side).
SPECIAL_SIDES = {
    "AE": ("A", "E"), "OE": ("O", "E"), "ae": ("a", "e"), "oe": ("o", "e"),
    "Oslash": ("O", "O"), "oslash": ("o", "o"), "Eth": ("Eth", "D"),
    "Thorn": ("H", "Thorn"), "thorn": ("thorn", "p"), "eth": ("eth", "o"),
    "germandbls": ("germandbls", "germandbls"), "dotlessi": ("i", "i"),
    "f_f": ("f", "f"), "f_i": ("f", "i"), "f_l": ("f", "l"), "f_j": ("f", "j"),
    "f_f_i": ("f", "i"), "f_f_l": ("f", "l"), "fi": ("f", "i"),
    "fl": ("f", "l"), "f_b": ("f", "b"), "f_h": ("f", "h"), "f_k": ("f", "k"),
    "f_f_b": ("f", "b"), "f_f_h": ("f", "h"), "f_f_k": ("f", "k"),
    "f.short": ("f", "f.short"), "f_f.short": ("f", "f.short"),
}


def category(font, name):
    if name in SPECIAL_SIDES:
        return LOWER
    if name.endswith(".sc"):
        return SMALLCAP
    if name.endswith(".osf"):
        return OLDSTYLE
    if name.endswith(".case"):                 # raised to capital height
        return DASH if name[:-5] in DASH_NAMES else PUNCT
    if name.endswith(".csc"):
        return category(font, name[:-4])
    if name in ALIASES:
        return category(font, ALIASES[name])
    if "." in name:
        return None                 # .tf, .num, .den, .frac ...
    if name in FIGURES:
        return FIGURE
    if name in LOWPUNCT_NAMES:
        return LOWPUNCT
    if name in DASH_NAMES:
        return DASH
    if name in QUOTE_NAMES:
        return QUOTE
    if name in PUNCT_NAMES:
        return PUNCT
    if name in SPECIAL_SIDES and name[0].islower():
        return LOWER
    if name in NOT_KERNED:
        return None
    glyph = font[name]
    if not glyph.unicodes:
        return None
    kind = unicodedata.category(chr(glyph.unicodes[0]))
    if kind == "Lu":
        return CAP
    if kind == "Ll":
        return LOWER
    return None


def base_letter(font, name):
    """Group key per side: (left side, right side)."""
    if name in SPECIAL_SIDES:
        return SPECIAL_SIDES[name]
    stem, dot, suffix = name.partition(".")
    if stem in SPECIAL_SIDES:
        left, right = SPECIAL_SIDES[stem]
    else:
        left = right = stem
        if stem in font and font[stem].unicodes:
            decomposed = unicodedata.normalize("NFD", chr(font[stem].unicodes[0]))
            base = decomposed[0]
            for g in font:
                if ord(base) in g.unicodes:
                    left = right = g.name
                    break
    if suffix:
        left, right = f"{left}.{suffix}", f"{right}.{suffix}"
    return left, right


def names_sc(kerner):
    return [n for n, c in kerner.cats.items() if c == SMALLCAP]


def capital_of(font, sc_name):
    """The capital a small cap stands for (a.sc -> A, ae.sc -> AE)."""
    base = sc_name[:-3]
    if base not in font or not font[base].unicodes:
        return None
    up = chr(font[base].unicodes[0]).upper()
    if len(up) != 1:
        return None
    for g in font:
        if ord(up) in g.unicodes:
            return g.name
    return None


def designer_pairs(face):
    """ET Book's own pairs and Michael Sharpe's ETbb pairs (scaled to
    Bolex); where both kern a pair, their mean."""
    sources = [read_pairs(KERN_DIR / f"{name}-{face}.txt")
               for name in ("etbook", "etbb")]
    merged = {}
    for pair in set().union(*sources):
        values = [src[pair] for src in sources if pair in src]
        merged[pair] = sum(values) / len(values)
    return merged


def read_pairs(path):
    pairs = {}
    if not path.exists():
        return pairs
    for line in path.read_text().splitlines():
        line = line.split("#", 1)[0].strip()
        if line:
            left, right, value = line.split()
            pairs[(left, right)] = int(value)
    return pairs


class Kerner:
    def __init__(self, font):
        self.font = font
        self.cats = {}
        for g in font:
            c = category(font, g.name)
            if c and g.name in font:
                self.cats[g.name] = c
        homes = {km.HOME[c] for c in self.cats.values() if km.HOME[c] in font}
        self.sides = km.Sides(font, set(self.cats) | homes)
        self._cache = {}

    def height(self, name):
        from fontTools.pens.boundsPen import BoundsPen
        pen = BoundsPen(self.font)
        self.font[name].draw(pen)
        return pen.bounds[3]

    def home(self, name):
        h = km.HOME[self.cats[name]]
        return h if h in self.font else "H"

    def model(self, left, right):
        """Raw model kern (before scale/threshold) or None."""
        hl, hr = self.home(left), self.home(right)
        xa = km.interaction(km.area, self.sides, left, right, hl, hr,
                            AREA_DEPTH)
        xm = km.interaction(km.closest, self.sides, left, right, hl, hr,
                            CLOSEST_DEPTH)
        if xa is None or xm is None:
            return None
        return -(AREA_WEIGHT * xa + CLOSEST_WEIGHT * xm)

    def pair(self, left, right, designer=None):
        scale = SCALE[(self.cats[left], self.cats[right])]
        value = 0.0
        if scale:
            raw = self.model(left, right)
            if raw is not None:
                # The model only closes pairs up; opening is the collision
                # guard's job (positive model values come from short
                # glyphs measured against tall neighbours).
                value = min(0.0, scale * raw)
        if designer is not None:
            value = DESIGNER_WEIGHT * designer + (1 - DESIGNER_WEIGHT) * value
        value = max(MAX_NEGATIVE, value)
        if abs(value) < THRESHOLD:
            value = 0
        return self.guard(left, right, int(ROUND_TO * round(value / ROUND_TO)))

    def guard(self, left, right, value):
        """Keep the outlines apart.  A pair that touches or nearly touches
        unkerned (closer than CONTACT) is opened to MIN_CLEARANCE; any
        other pair may be kerned no closer than MIN_CLEARANCE or its own
        unkerned clearance, whichever is smaller (serifs that sit close
        by design are left alone).  Steps of 5 units."""
        natural = km.clearance(self.sides, left, right, 0)
        if natural is None:
            return value
        target = MIN_CLEARANCE if natural < CONTACT \
            else min(MIN_CLEARANCE, natural)
        clear = km.clearance(self.sides, left, right, value)
        while clear is not None and clear < target and value < 300:
            value += ROUND_TO
            clear = km.clearance(self.sides, left, right, value)
        return value


def kernable_pairs(kerner):
    """Every pair of kernable glyphs.  Pairs whose categories have no model
    scale (punctuation-punctuation, ...) still get the collision guard."""
    names = sorted(kerner.cats)
    for left in names:
        for right in names:
            yield left, right


def build(face):
    path = ROOT / "sources" / f"Bolex-{face.capitalize()}.ufo"
    font = ufoLib2.Font.open(path)
    designer = designer_pairs(face)
    overrides = read_pairs(KERN_DIR / f"overrides-{face}.txt")
    kerner = Kerner(font)

    # 1. Every pair, glyph by glyph.
    values = {}
    for left, right in kernable_pairs(kerner):
        v = kerner.pair(left, right, designer.get((left, right)))
        if v:
            values[(left, right)] = v

    # 2. Groups by base letter.
    kern1, kern2 = defaultdict(list), defaultdict(list)
    for name in kerner.cats:
        left_key, right_key = base_letter(font, name)
        kern1[right_key].append(name)   # glyph on the left: its right side
        kern2[left_key].append(name)    # glyph on the right: its left side
    kern1 = {k: sorted(v) for k, v in kern1.items() if len(v) > 1 and k in v}
    kern2 = {k: sorted(v) for k, v in kern2.items() if len(v) > 1 and k in v}
    g1 = {m: k for k, v in kern1.items() for m in v}
    g2 = {m: k for k, v in kern2.items() for m in v}

    # 3. Overrides: set the named pair, and move every pair of the same
    #    two groups by the same amount (re-checking collisions), so
    #    accented forms stay consistent with their base letter.
    for (left, right), target in overrides.items():
        delta = target - values.get((left, right), 0)
        lefts = kern1.get(g1.get(left), [left]) if left in g1 else [left]
        rights = kern2.get(g2.get(right), [right]) if right in g2 else [right]
        for m1 in lefts:
            for m2 in rights:
                if (m1, m2) == (left, right):
                    v = target
                else:
                    v = kerner.guard(m1, m2, values.get((m1, m2), 0) + delta)
                if v:
                    values[(m1, m2)] = v
                else:
                    values.pop((m1, m2), None)

    # Small caps are capitals drawn smaller: kern a pair of them like the
    # same two capitals, scaled by the small-cap/cap height ratio.
    if "h.sc" in font:
        ratio = kerner.height("h.sc") / kerner.height("H")
        for m1 in names_sc(kerner):
            for m2 in names_sc(kerner):
                c1, c2 = capital_of(font, m1), capital_of(font, m2)
                cap_value = values.get((c1, c2), 0) if c1 and c2 else 0
                if cap_value:
                    v = int(ROUND_TO * round(ratio * cap_value / ROUND_TO))
                    v = kerner.guard(m1, m2, v)
                    if v:
                        values[(m1, m2)] = v
                    else:
                        values.pop((m1, m2), None)

    def side1(n):
        return f"public.kern1.{g1[n]}" if n in g1 else n

    def side2(n):
        return f"public.kern2.{g2[n]}" if n in g2 else n

    # 4. Class pairs from the base glyphs; exceptions for members whose
    #    own value differs from their group's.
    kerning = {}
    group_value = {}
    for (left, right), v in values.items():
        if g1.get(left, left) == left and g2.get(right, right) == right:
            key = (side1(left), side2(right))
            group_value[key] = v
            kerning[key] = v
    exceptions = 0
    names = sorted(kerner.cats)
    for left in names:
        for right in names:
            key = (side1(left), side2(right))
            expected = group_value.get(key, 0)
            actual = values.get((left, right), 0)
            if abs(actual - expected) > EXCEPTION_TOLERANCE:
                kerning[(left, right)] = actual
                exceptions += 1

    font.groups.clear()
    for k, v in kern1.items():
        font.groups[f"public.kern1.{k}"] = v
    for k, v in kern2.items():
        font.groups[f"public.kern2.{k}"] = v
    font.kerning.clear()
    font.kerning.update(kerning)
    font.save()
    print(f"{path.relative_to(ROOT)}: {len(values)} kerned glyph pairs -> "
          f"{len(font.kerning)} kerning entries ({exceptions} exceptions), "
          f"{len(kern1)}+{len(kern2)} groups")
    return kerner, values


def main(faces):
    for face in faces or ["roman", "italic"]:
        build(face)


if __name__ == "__main__":
    main(sys.argv[1:])
