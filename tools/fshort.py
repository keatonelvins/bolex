#!/usr/bin/env python3
"""Add f.short and f_f.short: an f whose hook stops near its advance.

The Roman f's hook overhangs its advance by ~120 units, so before ) ] } ? ! ' " and tall accents it collides, and the
kerning needed to clear it leaves a hole at the baseline.  f.short pulls
the hook's terminal back by SHORTEN units: the terminal keeps its shape
and the arch between stem and terminal is drawn in proportionally.
``calt`` (tools/features.py) uses it before those characters.

Usage: tools/fshort.py
"""
from pathlib import Path

import ufoLib2

import outline

ROOT = Path(__file__).resolve().parent.parent
# Roman only: the italic hook curls back on itself and cannot be pulled
# in this way; its few collisions (f) f] f}) are kerned instead.
SHORTEN = {"Roman": 80}
HOOK_FLOOR = 560      # only the hook (above the crossbar) is touched
TERMINAL = 80         # the last ~80 units of the hook move as a whole


def shorten(font, src, dst, delta):
    tan = outline.slant(font)
    glyph = font[src].copy()
    hook = [p for c in glyph.contours for p in c if p.y > HOOK_FLOOR]
    upright = lambda p: p.x - p.y * tan
    x_max = max(upright(p) for p in hook)
    # The arch starts at the stem: the leftmost hook point at its top.
    x_start = min(upright(p) for p in hook if p.y > HOOK_FLOOR + 100)
    x_term = x_max - TERMINAL
    for p in hook:
        u = upright(p)
        t = min(1.0, max(0.0, (u - x_start) / (x_term - x_start)))
        t = t * t * (3 - 2 * t)                       # smoothstep
        # Fade in over the 40 units above the floor so nothing kinks.
        fade = min(1.0, (p.y - HOOK_FLOOR) / 40)
        p.x = round(p.x - delta * t * fade)
    glyph._name = dst
    if dst in font:
        del font[dst]
    font.layers.defaultLayer.insertGlyph(glyph, dst, copy=False)
    font[dst].unicodes = []
    order = font.lib.setdefault("public.glyphOrder", [])
    if dst not in order:
        order.append(dst)


def main():
    for face, delta in SHORTEN.items():
        path = ROOT / "sources" / f"Bolex-{face}.ufo"
        font = ufoLib2.Font.open(path)
        shorten(font, "f", "f.short", delta)
        if "f_f" in font:
            shorten(font, "f_f", "f_f.short", delta)
        font.save()
        print(f"{path.relative_to(ROOT)}: f.short, f_f.short (-{delta})")


if __name__ == "__main__":
    main()
