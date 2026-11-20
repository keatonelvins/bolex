"""Extract Michael Sharpe's ETbb kerning as a reference for Bolex.

ETbb (CTAN package ``etbb``, MIT licence, like ET Book) is ET Book with
hand-revised kerning and spacing, its outlines scaled by about 1.033.
This shapes every pair of Bolex's letters and punctuation (and small
caps, through ``smcp``) in ETbb with kerning on and off, scales the
difference to Bolex's size, and writes the non-zero pairs as Bolex glyph
names to kerning/etbb-<face>.txt.  kerning.py treats them,
like ET Book's own pairs, as a designer's opinion to blend with its
model.  Figures are left out: ETbb's default figures are tabular.

Only needed to take the pairs again: uv run python -m bolex.etbb PATH/TO/etbb/opentype
"""

import sys
import unicodedata
from pathlib import Path

import uharfbuzz as hb
from fontTools.pens.boundsPen import BoundsPen
from fontTools.ttLib import TTFont

from . import build

FILES = {"Roman": "ETbb-Regular.otf", "Italic": "ETbb-Italic.otf"}
MIN_KERN = 10


class Shaper:
    def __init__(self, path):
        self.font = hb.Font(hb.Face(hb.Blob.from_file_path(str(path))))
        self.tt = TTFont(path)

    def kern(self, text, features):
        def run(kern):
            buf = hb.Buffer()
            buf.add_str(text)
            buf.guess_segment_properties()
            hb.shape(self.font, buf, dict(features, kern=kern))
            return ([g.codepoint for g in buf.glyph_infos], sum(p.x_advance for p in buf.glyph_positions))

        glyphs, on = run(True)
        glyphs_off, off = run(False)
        if glyphs != glyphs_off or len(glyphs) != 2:
            return None
        return on - off

    def cap_height(self):
        """Measured: ETbb's OS/2 sCapHeight was not scaled with its
        outlines."""
        gs = self.tt.getGlyphSet()
        pen = BoundsPen(gs)
        gs[self.tt.getBestCmap()[ord("H")]].draw(pen)
        return pen.bounds[3]


def candidates(font):
    """(Bolex glyph name, text, features) for letters, small caps and
    punctuation.  The ff ffi ffl ligatures are left to the model."""
    out = []
    for glyph in font:
        if not glyph.unicodes or "." in glyph.name or glyph.name.startswith("f_"):
            continue
        char = chr(glyph.unicodes[0])
        kind = unicodedata.category(char)
        if kind[0] == "L" or kind[0] == "P" or char in "–—":
            out.append((glyph.name, char, {}))
            if kind == "Ll" and f"{glyph.name}.sc" in font:
                out.append((f"{glyph.name}.sc", char, {"smcp": True}))
    return out


def main(etbb_dir):
    for face, filename in FILES.items():
        etbb = Shaper(Path(etbb_dir) / filename)
        font = build.draw(face)
        scale = font["H"].getBounds(font).yMax / etbb.cap_height()
        glyphs = candidates(font)
        pairs = {}
        for left, a, fa in glyphs:
            for right, b, fb in glyphs:
                if fa != fb and not (fb and left[0].isupper()):
                    continue  # small cap only after small cap/capital
                k = etbb.kern(a + b, fa or fb)
                if k and abs(k * scale) >= MIN_KERN:
                    pairs[(left, right)] = int(5 * round(k * scale / 5))
        lines = [
            f"# Kerning from ETbb {face} (Michael Sharpe, CTAN 'etbb', MIT",
            "# licence), scaled to Bolex units by bolex/etbb.py.",
            "# Format: LEFT RIGHT VALUE",
            "",
        ]
        lines += [f"{l} {r} {v}" for (l, r), v in sorted(pairs.items())]
        out = Path(__file__).parent / "kerning" / f"etbb-{face.lower()}.txt"
        out.write_text("\n".join(lines) + "\n")
        print(f"{out.name}: {len(pairs)} pairs (scale {scale:.4f})")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    main(sys.argv[1])
