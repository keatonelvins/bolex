"""The faces, the names, and where ET Book comes from."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FONTS = ROOT / "fonts"

# ET Book's Roman and Italic, copied in from a fork of dpk/et-book (its LICENSE beside them).
ET_BOOK = ROOT / "et-book"

FAMILY = "Bolex"
VERSION = (1, 0)
RELEASED = "2026/11/20 00:00:00"  # stamped in place of the build time, so a build repeats exactly
REPOSITORY = "https://github.com/keatonelvins/bolex"
FACES = ("Roman", "Italic")
