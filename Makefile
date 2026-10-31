# Bolex build.
#
#   make            build fonts/Bolex-Roman.woff2 and fonts/Bolex-Italic.woff2
#   make sources    regenerate sources/ from an ET Book checkout
#                   (ETBOOK=path/to/et-book, default ../et-book)
#   make specimen   render specimen/index.html to specimen/specimen.png
#
# Python tools run from .venv:  python3 -m venv .venv &&
#   .venv/bin/pip install -r requirements.txt

PY ?= .venv/bin/python
ETBOOK ?= ../et-book
UFOS = sources/Bolex-Roman.ufo sources/Bolex-Italic.ufo

.PHONY: fonts sources clean

fonts: fonts/Bolex-Roman.woff2 fonts/Bolex-Italic.woff2

fonts/Bolex-%.woff2: sources/Bolex-%.ufo $(shell find sources -type f) tools/build.py
	$(PY) tools/build.py $<

sources:
	$(PY) tools/import_etbook.py $(ETBOOK)
	$(PY) tools/spacing.py
	$(PY) tools/ligatures.py
	$(PY) tools/fshort.py
	$(PY) tools/figures.py
	$(PY) tools/glyphs.py
	$(PY) tools/smallcaps.py
	$(PY) tools/features.py
	$(PY) tools/kerning.py

clean:
	rm -rf build
