"""Draw bolex.svg, the specimen, from the built fonts: uv run python -m bolex.specimen"""

import uharfbuzz as hb
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.ttLib import TTFont

from . import config

PAPER, INK, MUTED = "#fbfbfa", "#111110", "#8a8a85"
WIDTH, MARGIN = 1200, 60
MEASURE = WIDTH - 2 * MARGIN
TEXT = 24  # the text size
COLUMN = 600  # the reading column, set flush with the right margin

ROMAN, ITALIC = config.FACES
BODY = (
    "The Bolex H16 is a 16 mm film camera, made by Paillard in Sainte-Croix, Switzerland, from 1935. It runs on a "
    "spring: one full wind drives about 28 seconds of film at 24 frames a second, and a 100-foot spool lasts just "
    "under three minutes. It needs no battery, and three lenses ride on a turret at its front. Maya Deren shot "
    "_Meshes of the Afternoon_ on one in 1943, and it has been the camera of film schools and the avant-garde "
    "ever since."
)
ALPHABET = ("ABCDEFGHIJKLM", "NOPQRSTUVWXYZ", "abcdefghijklmnopqrs", "tuvwxyz0123456789")
SMALL_CAPS = {"smcp": True, "c2sc": True}


class Sheet:
    """An SVG page set in Bolex's own outlines, so it needs no font to view."""

    def __init__(self) -> None:
        self.fonts, self.shapers = {}, {}
        for face in config.FACES:
            path = config.FONTS / f"{config.FAMILY}-{face}.ttf"
            self.fonts[face] = TTFont(path)
            self.shapers[face] = hb.Font(hb.Face(hb.Blob.from_file_path(str(path))))
        self.paths: dict[str, str] = {}
        self.lines: list[str] = []

    def shape(self, text: str, face: str, features: dict) -> tuple[list[tuple[int, float]], float]:
        """The glyphs the face sets for `text`, each with its place on the line, and the line's length in ems."""
        buffer = hb.Buffer()
        buffer.add_str(text)
        buffer.guess_segment_properties()
        hb.shape(self.shapers[face], buffer, features)
        placed, x = [], 0
        for info, position in zip(buffer.glyph_infos, buffer.glyph_positions):
            placed.append((info.codepoint, x + position.x_offset))
            x += position.x_advance
        return placed, x / 1000

    def length(self, text: str, face: str = ROMAN, **features: bool) -> float:
        return self.shape(text, face, features)[1]

    def line(self, text, x, y, size, face=ROMAN, fill=INK, **features: bool) -> float:
        """Set one line with its baseline at (x, y). Returns where it ends."""
        font = self.fonts[face]
        glyphs, order = font.getGlyphSet(), font.getGlyphOrder()
        placed, length = self.shape(text, face, features)
        uses = []
        for glyph, at in placed:
            name = order[glyph]
            if (key := f"{face}-{glyph}") not in self.paths:
                pen = SVGPathPen(glyphs)
                glyphs[name].draw(pen)
                self.paths[key] = pen.getCommands()
            if self.paths[key]:
                uses.append(f'<use href="#{key}" x="{at:g}"/>')
        scale = size / 1000
        self.lines.append(
            f'<g transform="translate({x:g} {y:g}) scale({scale:g} {-scale:g})" fill="{fill}">{"".join(uses)}</g>'
        )
        return x + length * size

    def paragraph(self, text: str, x: float, y: float, size: float, width: float, leading: float) -> float:
        """Set ragged-right text, with _words like these_ in the Italic. Returns the last baseline."""
        words, face = [], ROMAN
        for word in text.split():
            if word.startswith("_"):
                face = ITALIC
            words.append((word.strip("_"), face))
            if word.rstrip(".,").endswith("_"):
                face = ROMAN
        space = self.length(" ") * size
        at = x
        for index, (word, face) in enumerate(words):
            if at > x and at + self.length(word, face) * size > x + width:
                at, y = x, y + leading
            at = self.line(word, at, y, size, face) + space
        return y

    def save(self, height: float) -> None:
        paths = "".join(f'<path id="{key}" d="{d}"/>' for key, d in self.paths.items() if d)
        (config.ROOT / "bolex.svg").write_text(
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {WIDTH} {height:g}" width="{WIDTH}" height="{height:g}">'
            f'<rect width="100%" height="100%" fill="{PAPER}"/><defs>{paths}</defs>{"".join(self.lines)}</svg>\n'
        )


def main() -> None:
    sheet = Sheet()
    right = WIDTH - MARGIN

    def filling(text: str, face: str = ROMAN, **features: bool) -> float:
        """The size at which `text` fills the measure."""
        return MEASURE / sheet.length(text, face, **features)

    def label(left: str, end: str, y: float) -> None:
        sheet.line(left, MARGIN, y, TEXT, fill=MUTED, **SMALL_CAPS)
        sheet.line(end, right - sheet.length(end, **SMALL_CAPS) * TEXT, y, TEXT, fill=MUTED, **SMALL_CAPS)

    def sample(text: str, y: float, face: str = ROMAN, **features: bool) -> float:
        """A line that fills the measure, under the baseline `y`. Returns its own baseline."""
        size = filling(text, face, **features)
        y += size * 0.95
        sheet.line(text, MARGIN, y, size, face, **features)
        return y

    y = 150 + filling(config.FAMILY) * 0.66
    sheet.line(config.FAMILY, MARGIN, y, filling(config.FAMILY))

    y += 150
    sheet.line("A book face", MARGIN, y, TEXT)
    y = sheet.paragraph(BODY, right - COLUMN, y, TEXT, COLUMN, TEXT * 1.45)

    y += 110
    size = filling(max(ALPHABET, key=sheet.length))
    for row in ALPHABET:
        y += size * 1.2
        sheet.line(row, MARGIN, y, size)

    y += 190
    label("Roman", "400", y)
    y = sample("Sainte-Croix, 1935", y)

    y += 130
    label("Italic", "400", y)
    y = sample("Meshes of the Afternoon", y, ITALIC)

    y += 130
    label("Small capitals", "In the Roman", y)
    y = sample("Wound by hand, 24 frames", y, **SMALL_CAPS)

    y += 130
    label("Figures", "Lining and oldstyle", y)
    gutter = 60
    size = (MEASURE - gutter) / 2 / sheet.length("0123456789", onum=True)
    y += size * 1.05
    sheet.line("0123456789", MARGIN, y, size)
    sheet.line("0123456789", right - sheet.length("0123456789", onum=True) * size, y, size, onum=True)

    font = sheet.fonts[ROMAN]
    glyphs, shown = font.getGlyphSet(), {}
    for code, name in sorted(font.getBestCmap().items()):
        if not chr(code).isspace() and glyphs[name].width and code < 0xFB00:
            shown.setdefault(name, chr(code))  # each glyph once, the ligatures' own code points aside
    characters = list(shown.values())
    y += 190
    label("Glyphs", str(len(characters)), y)
    columns = 24
    cell = MEASURE / columns
    size = cell * 0.56
    y += 20
    for start in range(0, len(characters), columns):
        y += cell * 0.95
        for column, character in enumerate(characters[start : start + columns]):
            middle = MARGIN + (column + 0.5) * cell
            sheet.line(character, middle - sheet.length(character) * size / 2, y, size)

    sheet.save(y + 150)


if __name__ == "__main__":
    main()
