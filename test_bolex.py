"""One fact about each thing Bolex changes in ET Book, and what the built fonts promise."""

import io
import unicodedata

import pytest
import uharfbuzz as hb
from fontTools.ttLib import TTFont

from bolex import build, config, etbook
from bolex.figures import FIGURES

ROMAN, ITALIC = config.FACES


@pytest.fixture(scope="module", params=config.FACES, ids=str.lower)
def drawn(request):
    """One face as drawn, before it is compiled."""
    return request.param, build.draw(request.param)


@pytest.fixture(scope="module")
def roman():
    return build.draw(ROMAN)


def ink(font, name: str) -> tuple[float, float]:
    """The glyph's sidebearings as drawn: left, right."""
    bounds = font[name].getBounds(font)
    return bounds.xMin, font[name].width - bounds.xMax


def length(font, name: str) -> float:
    bounds = font[name].getBounds(font)
    return bounds.xMax - bounds.xMin


def test_figures_line_up_with_the_capitals_and_are_spaced_one_by_one(roman):
    assert all(roman[name].unicodes == [ord("0") + digit] for digit, name in enumerate(FIGURES))
    assert roman["one"].getBounds(roman).yMax == roman["one.tf"].getBounds(roman).yMax == 640
    assert roman["one"].width < roman["zero"].width  # 1914 doesn't open up around its 1s


def test_tabular_figures_share_one_width_and_one_top(roman):
    for suffix in ("tf", "tosf"):
        assert len({roman[f"{name}.{suffix}"].width for name in FIGURES}) == 1  # ET Book's eight was 25 narrow
    assert {round(roman[f"{name}.tf"].getBounds(roman).yMax) for name in FIGURES} == {640}  # its seven stopped at 624


def test_ae_starts_where_a_does(roman):
    assert ink(roman, "AE")[0] == pytest.approx(ink(roman, "A")[0], abs=1)  # it hung 69 units outside its advance
    assert ink(roman, "ae.sc")[0] == pytest.approx(ink(roman, "a.sc")[0], abs=1)


def test_closing_bracket_mirrors_the_opening_one(roman):
    left, right = ink(roman, "bracketleft")
    assert ink(roman, "bracketright") == pytest.approx((right, left), abs=1)


def test_em_dash_is_half_again_the_en_dash(drawn):
    _, font = drawn
    assert length(font, "emdash") / length(font, "endash") > 1.4  # ET Book's was 1.27: the two read as one mark


def test_accented_letters_are_spaced_like_their_letter(drawn):
    _, font = drawn
    for accented, letter in (("eacute", "e"), ("Zcaron", "Z"), ("Ntilde", "N"), ("odieresis", "o")):
        assert font[accented].width == pytest.approx(font[letter].width, abs=2)  # Ž was 15 units looser than Z


def test_short_f_keeps_its_hook_nearer_its_advance(drawn):
    _, font = drawn
    for short, full in (("f.short", "f"), ("f_f.short", "f_f")):
        assert -ink(font, short)[1] < -ink(font, full)[1] - 50
        assert font[short].width == font[full].width


def test_every_lowercase_letter_has_its_small_cap(roman):
    lowercase = {
        glyph.name
        for glyph in roman
        if "." not in glyph.name and glyph.unicodes and unicodedata.category(chr(glyph.unicodes[0])) == "Ll"
    }
    without = {name for name in lowercase if f"{name}.sc" not in roman}
    assert without == {"germandbls", "dotlessi", "mu", "fi", "fl", "f_f", "f_f_i", "f_f_l"}  # each set another way


def test_italic_has_no_small_caps():
    assert not [glyph.name for glyph in build.draw(ITALIC) if glyph.name.endswith(".sc")]


def test_arrows_and_math_stand_on_the_math_width(drawn):
    _, font = drawn
    assert len({font[name].width for name in ("plus", "minus", "multiply", "divide", "notequal", "lessequal")}) == 1
    assert len({font[name].width for name in ("arrowleft", "arrowup", "arrowright", "arrowdown", "uni21A9")}) == 1


@pytest.fixture(scope="module", params=config.FACES, ids=str.lower)
def built(request) -> tuple[str, TTFont]:
    return request.param, build.compile_ttf(request.param)


@pytest.fixture(scope="module")
def typed(built):
    """Type a line in the built face: the glyphs it sets and the line's length."""
    _, ttf = built
    data = io.BytesIO()
    ttf.save(data)
    font = hb.Font(hb.Face(data.getvalue()))

    def type_(text: str, **features: bool) -> tuple[list[int], int]:
        buffer = hb.Buffer()
        buffer.add_str(text)
        buffer.guess_segment_properties()
        hb.shape(font, buffer, features)
        return [info.codepoint for info in buffer.glyph_infos], sum(pos.x_advance for pos in buffer.glyph_positions)

    return type_


def test_f_joins_what_its_hook_would_hit(typed):
    for letters in ("fi", "fl", "fj", "fb", "fh", "fk", "ffi", "ffl", "ffb", "ffh", "ffk"):
        glyphs, _ = typed(letters + "a")
        assert len(glyphs) == 2, letters
    assert typed("ﬃ")[0] == typed("ffi")[0]


def test_f_is_short_at_the_end_of_a_word(typed):
    (full, _), _ = typed("fa")
    (short, _), _ = typed("f)")
    assert short != full
    assert typed("of")[0][1] == typed("(of)")[0][2] == typed("f?")[0][0] == short
    assert typed("after")[0][1] == full


def test_kerns_capitals_and_punctuation(typed):
    for pair in ("AV", "LT", "PA", "To", "T.", "V,", "“A", "L’"):  # ET Book kerned only the fourth
        assert typed(pair)[1] < typed(pair, kern=False)[1], pair
    assert typed("nn")[1] == typed("nn", kern=False)[1]


def test_accented_letters_kern_with_their_letter_and_no_tighter(typed):
    def kern(pair: str) -> int:
        return typed(pair)[1] - typed(pair, kern=False)[1]

    assert kern("Te") <= kern("Té") < 0 and kern("Va") <= kern("Vä") < 0  # ET Book kerned no accented letter
    assert kern("Éa") == kern("Ea") and kern("ñ.") == kern("n.")


def test_raises_punctuation_for_capitals(typed):
    plain, _ = typed("(A-B)")
    raised, _ = typed("(A-B)", case=True)
    assert [a != b for a, b in zip(plain, raised)] == [True, False, True, False, True]


def test_sets_footnote_figures_as_superiors(typed):
    assert typed("x12", sups=True)[1] == typed("x¹²")[1] < typed("x12")[1]


def test_roman_raises_a_dash_between_figures(built, typed):
    face, _ = built
    (dash,), _ = typed("–")
    (raised,), _ = typed("–", case=True)
    assert typed("a–b")[0][1] == dash
    assert typed("1914–1918")[0][4] == (raised if face == ROMAN else dash)  # the Italic's figures are oldstyle


def test_roman_figures_have_three_more_forms(built, typed):
    face, _ = built
    lining, length = typed("1914")
    forms = {tuple(typed("1914", **{feature: True})[0]) for feature in ("onum", "tnum")} | {tuple(lining)}
    assert len(forms) == (3 if face == ROMAN else 1)
    if face == ROMAN:
        assert typed("1111", tnum=True)[1] == typed("4096", tnum=True)[1] > typed("1111")[1]


def test_roman_small_caps_take_no_ligatures_and_bring_oldstyle_figures(built, typed):
    face, _ = built
    if face == ITALIC:
        assert typed("office", smcp=True) == typed("office")
        return
    small, _ = typed("office", smcp=True)
    assert len(small) == 6 and not set(small) & set(typed("o f i c e")[0])  # ET Book set a lowercase ffi here
    assert len(typed("straße", smcp=True)[0]) == 7
    assert typed("WWII 1945", smcp=True, c2sc=True)[0][5:] == typed("1945", onum=True)[0]


def test_roman_fraction_takes_only_the_figures_beside_its_slash(built, typed):
    face, _ = built
    if face == ITALIC:
        return
    glyphs, _ = typed("3 1/2", frac=True)
    assert glyphs[:2] == typed("3 ")[0] and not set(glyphs[2:]) & set(typed("1/2")[0])
    assert typed("1984", frac=True) == typed("1984")


def test_faces_share_one_line(built):
    _, ttf = built
    os2, hhea = ttf["OS/2"], ttf["hhea"]
    assert (hhea.ascent, hhea.descent, hhea.lineGap) == (836, -364, 0)  # line-height: normal is 1.2
    assert (os2.sTypoAscender, os2.sTypoDescender, os2.sTypoLineGap) == (836, -364, 0)
    assert os2.fsSelection & 1 << 7  # and every browser reads it from the typo metrics
    assert (os2.usWinAscent, os2.usWinDescent) == build.win_metrics()


def test_windows_clips_no_glyph(built):
    _, ttf = built
    drawn = [glyph for glyph in map(ttf["glyf"].get, ttf.getGlyphOrder()) if glyph.numberOfContours]
    assert max(glyph.yMax for glyph in drawn) < ttf["OS/2"].usWinAscent
    assert min(glyph.yMin for glyph in drawn) > -ttf["OS/2"].usWinDescent


TYPED_PAGE = (
    "In the summer of 1914 the Western Front ran 440 miles. “Typography,” Tufte wrote, “exists to honor content.” "
    "Œuvre, Ångström, façade, Šumava, Žižek, straße, ¿qué? — 9 a.m.–5 p.m. · 3½ × 2″ ≈ 7′ · €5 ± 10‰ ¹²³⁴ ← ↑ → ↓ ↔ ↩ "
    "† ‡ § ¶ © ® ™ … ‹ › « » ‘ ’ ‚ „ ʻ ʼ ﬀ ﬁ ﬂ ﬃ ﬄ"
)
SPACES = "        "  # no-break, en, em, figure, punctuation, thin, hair, narrow


def test_types_a_page(built):
    _, ttf = built
    cmap = ttf.getBestCmap()
    assert not {character for character in TYPED_PAGE + SPACES if character != " " and ord(character) not in cmap}
    assert 0x2011 in cmap and 0x2012 in cmap  # the non-breaking hyphen and the figure dash


def test_has_every_character_it_promises(built):
    _, ttf = built
    cmap = ttf.getBestCmap()
    assert not {chr(code) for code in etbook.CHARSET - set(cmap)}
    assert 0x00AD not in cmap  # the browser draws the soft hyphen
    assert 0x0141 not in cmap and 0x0192 not in cmap  # Central European letters and the florin are left behind


def test_both_faces_type_the_same_characters():
    roman, italic = (set(build.compile_ttf(face).getBestCmap()) for face in config.FACES)
    assert roman == italic


def test_names_its_face(built):
    face, ttf = built
    name = ttf["name"]
    assert name.getBestFamilyName() == config.FAMILY
    assert name.getDebugName(1) == config.FAMILY  # one family of two, so <i> finds the Italic
    assert name.getDebugName(2) == {ROMAN: "Regular", ITALIC: "Italic"}[face]
    assert name.getDebugName(3) == f"1.000;{config.FAMILY}-{face}"
    assert ttf["OS/2"].usWeightClass == 400
    assert bool(ttf["head"].macStyle & 2) == (face == ITALIC) == (ttf["post"].italicAngle < 0)
    assert ttf["OS/2"].fsType == 0
    assert "MIT License" in name.getDebugName(13)
    assert all(holder in name.getDebugName(0) for holder in ("Dmitry Krasny", "Edward Tufte", "Keaton Elvins"))


def test_builds_the_same_twice():  # last: it draws both faces from ET Book again
    def files() -> list[bytes]:
        saved = []
        for face in config.FACES:
            build.compile_ttf(face).save(file := io.BytesIO())
            saved.append(file.getvalue())
        return saved

    first = files()
    build.draw.cache_clear()
    build.win_metrics.cache_clear()
    assert files() == first
