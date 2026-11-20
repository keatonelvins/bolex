"""Write each face's OpenType features from its glyph set.

The OpenType features are derived from glyph-name conventions, so they
can never drift out of sync with the glyphs:

* ``f_f``, ``f_i``, ... ligatures             -> ``liga``
* ``x.sc`` small capitals, ``x.csc`` punctuation -> ``smcp`` / ``c2sc``
* ``zero`` (lining, default) / ``zero.osf``     -> ``onum`` / ``lnum``
* ``zero.tf`` tabular lining                    -> ``tnum`` / ``pnum``
* ``zero.num`` / ``zero.den``                   -> ``frac`` / ``numr`` / ``dnom``

ufo2ft writes the ``kern`` feature from the font's kerning (kerning.py)
at build time.
"""

import unicodedata

from . import kernmodel as km

FIGURES = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine"]

# Longest first so that "ffi" wins over "ff".
LIGATURES = [
    ("f f i", "f_f_i"),
    ("f f l", "f_f_l"),
    ("f f b", "f_f_b"),
    ("f f h", "f_f_h"),
    ("f f k", "f_f_k"),
    ("f f", "f_f"),
    ("f i", "f_i"),
    ("f j", "f_j"),
    ("f l", "f_l"),
    ("f b", "f_b"),
    ("f h", "f_h"),
    ("f k", "f_k"),
]


def _class(name, glyphs):
    return f"@{name} = [{' '.join(glyphs)}];"


def _have(font, names):
    return all(n in font for n in names)


def build(font):
    lines = [
        "languagesystem DFLT dflt;",
        "languagesystem latn dflt;",
        "",
    ]

    lf = FIGURES
    osf = [f"{n}.osf" for n in FIGURES]
    tf = [f"{n}.tf" for n in FIGURES]
    tosf = [f"{n}.tosf" for n in FIGURES]
    num = [f"{n}.num" for n in FIGURES]
    den = [f"{n}.den" for n in FIGURES]
    has_osf, has_tf = _have(font, osf), _have(font, tf)
    has_tosf = _have(font, tosf)
    has_frac = _have(font, num + den) and "fraction" in font

    lines.append(_class("lf", lf))
    if has_osf:
        lines.append(_class("osf", osf))
    if has_tf:
        lines.append(_class("tf", tf))
    if has_tosf:
        lines.append(_class("tosf", tosf))
    if has_frac:
        lines.append(_class("num", num))
        lines.append(_class("den", den))
    lines.append("")

    # Small caps come first in the lookup list, so that liga and calt see
    # f.sc rather than f (no lowercase ffi inside a small-cap word).
    # Superior figures (footnote markers) are the numerators.
    if _have(font, num):
        sups_from = ["@lf"] + (["@osf"] if has_osf else []) + (["@tf"] if has_tf else [])
        lines.append(_class("sups_num", num))
        lines.append("feature sups {")
        lines += [f"    sub {c} by @sups_num;" for c in sups_from]
        lines += ["} sups;", ""]

    sc = sorted(g.name for g in font if g.name.endswith(".sc"))
    if sc:
        lower = [n[:-3] for n in sc if n[:-3] in font]
        upper_map = []
        for n in sc:
            base = n[:-3]
            if base not in font:
                continue
            for u in font[base].unicodes:
                up = chr(u).upper()
                if len(up) == 1 and up != chr(u):
                    cap = _glyph_for(font, ord(up))
                    if cap:
                        upper_map.append((cap, n))
        csc = sorted(g.name for g in font if g.name.endswith(".csc") and g.name[:-4] in font)
        lines.append("feature smcp {")
        lines += [f"    sub {b} by {b}.sc;" for b in lower]
        if "germandbls" in font and "s.sc" in font:
            lines.append("    sub germandbls by s.sc s.sc;")
        if "dotlessi" in font and "i.sc" in font:
            lines.append("    sub dotlessi by i.sc;")
        for lig, parts in [
            ("fi", "f.sc i.sc"),
            ("fl", "f.sc l.sc"),
            ("f_f", "f.sc f.sc"),
            ("f_f_i", "f.sc f.sc i.sc"),
            ("f_f_l", "f.sc f.sc l.sc"),
        ]:
            if lig in font:
                lines.append(f"    sub {lig} by {parts};")
        lines += ["} smcp;", ""]
        # c2sc also brings in the small-cap punctuation and, in an
        # all-small-caps run, oldstyle figures (which match small-cap
        # height; lining figures stand a third taller).
        lines.append("feature c2sc {")
        if "Idotaccent" in font and "i.sc" in font:
            upper_map.append(("Idotaccent", "i.sc"))
        lines += [f"    sub {cap} by {s};" for cap, s in sorted(upper_map)]
        lines += [f"    sub {n[:-4]} by {n};" for n in csc]
        if has_osf:
            lines.append("    sub @lf by @osf;")
        lines += ["} c2sc;", ""]

    ligs = [(seq, lig) for seq, lig in LIGATURES if lig in font]
    if ligs:
        lines.append("feature liga {")
        lines += [f"    sub {seq} by {lig};" for seq, lig in ligs]
        lines += ["} liga;", ""]

    if has_osf:
        lines.append("feature onum {")
        lines.append("    sub @lf by @osf;")
        if has_tf and has_tosf:
            lines.append("    sub @tf by @tosf;")
        lines += ["} onum;", ""]
        lines.append("feature lnum {")
        lines.append("    sub @osf by @lf;")
        if has_tf and has_tosf:
            lines.append("    sub @tosf by @tf;")
        lines += ["} lnum;", ""]
    if has_tf:
        lines.append("feature tnum {")
        lines.append("    sub @lf by @tf;")
        if has_osf and has_tosf:
            lines.append("    sub @osf by @tosf;")
        lines += ["} tnum;", ""]
        lines.append("feature pnum {")
        lines.append("    sub @tf by @lf;")
        if has_osf and has_tosf:
            lines.append("    sub @tosf by @osf;")
        lines += ["} pnum;", ""]

    # calt, after liga and the figure features:
    # * f.short (fshort.py) before whatever the full hook would hit
    #   (ff) becomes f_f.short ));
    # * a hyphen or en dash between lining figures is raised to the
    #   figures' centre (1914-1918, 9-5).
    calt = []
    if "f.short" in font:
        # f.short wherever the full hook would collide, and at the end of
        # every word: before punctuation, a space, or the end of a run
        # (a footnote <sup>, an <em>, roman punctuation after an italic
        # word), which no rule can see across.  Before any other letter
        # the f keeps its full hook.
        after = set(short_f_contexts(font))
        letters = sorted(g.name for g in font if _is_letter(g) and g.name not in after)
        lines.append(f"@f_full_before = [{' '.join(letters)}];")
        fs = ["f"] + (["f_f"] if "f_f.short" in font else [])
        for f in fs:
            calt.append(f"    ignore sub {f}' @f_full_before;")
        for f in fs:
            calt.append(f"    sub {f}' by {f}.short;")
    figs = "[@lf" + (" @tf" if has_tf else "") + "]"
    if "endash.case" in font and _have(font, FIGURES) and "zero.osf" in font:
        calt.append(f"    sub {figs} [hyphen endash]' {figs} by [hyphen.case endash.case];")
    if calt:
        lines += ["", "feature calt {"] + calt + ["} calt;", ""]

    # case: punctuation raised for capitals and lining figures.
    case = sorted(g.name for g in font if g.name.endswith(".case") and g.name[:-5] in font)
    if case:
        lines.append("feature case {")
        lines += [f"    sub {n[:-5]} by {n};" for n in case]
        lines += ["} case;", ""]

    if has_frac:
        figure_classes = (
            ["@lf"] + (["@osf"] if has_osf else []) + (["@tf"] if has_tf else []) + (["@tosf"] if has_tosf else [])
        )
        anyfig = " ".join(figure_classes)
        lines.append("feature numr {")
        lines += [f"    sub {c} by @num;" for c in figure_classes]
        lines += ["} numr;", "", "feature dnom {"]
        lines += [f"    sub {c} by @den;" for c in figure_classes]
        lines += ["} dnom;", ""]
        # Only figures on either side of a slash become a fraction: "3 1/2"
        # keeps its 3, and "1984" stays a year.
        slash = "fraction.frac" if "fraction.frac" in font else "fraction"
        lines += [
            "feature frac {",
            "    lookup FRAC_SLASH {",
            f"        sub [{anyfig} @num] [slash fraction]' [{anyfig} @den] by {slash};",
            "    } FRAC_SLASH;",
            "    lookup FRAC_NUMR {",
        ]
        lines += [f"        rsub {c}' [{slash} @num] by @num;" for c in figure_classes]
        lines += ["    } FRAC_NUMR;", "    lookup FRAC_DNOM {"]
        lines += [f"        sub [{slash} @den] {c}' by @den;" for c in figure_classes]
        lines += ["    } FRAC_DNOM;", "} frac;", ""]
        inferiors = [f"uni208{d}" for d in range(10)]
        if _have(font, inferiors):
            lines.append(_class("inf", inferiors))
            for tag in ["subs", "sinf"]:
                lines.append(f"feature {tag} {{")
                lines += [f"    sub {c} by @inf;" for c in figure_classes]
                lines += [f"}} {tag};", ""]

    return "\n".join(lines).rstrip() + "\n"


def _is_letter(glyph):
    if glyph.name.startswith("f_") or glyph.name.endswith(".sc"):
        return True
    return any(unicodedata.category(chr(u)).startswith("L") for u in glyph.unicodes)


def short_f_contexts(font):
    """Glyphs the f's hook comes within 25 units of, where f.short clears
    them by at least 20 more."""
    names = [g.name for g in font if g.unicodes and g.name not in ("f",)]
    sides = km.Sides(font, names + ["f", "f.short"])
    after = []
    for name in sorted(names):
        full = km.clearance(sides, "f", name)
        short = km.clearance(sides, "f.short", name)
        if full is not None and full < 25 and short is not None and short >= full + 20:
            after.append(name)
    return after


def _glyph_for(font, codepoint):
    for g in font:
        if codepoint in g.unicodes:
            return g.name
    return None
