"""Make the web fonts for iglc.net from the Google Fonts downloads.

1. On fonts.google.com, open "Source Serif 4" and "Source Sans 3" and use "Get font" > "Download all".
2. Put the two zip files in the inventory folder (or anywhere) and run:

       .venv\\Scripts\\python -m pip install fonttools brotli
       .venv\\Scripts\\python tools\\build_fonts.py inventory\\Source_Serif_4.zip inventory\\Source_Sans_3.zip

The script takes the variable fonts from the zips, keeps the Latin characters used in names and
titles from around the world (including Nordic, Central European and Vietnamese letters), and writes
compressed WOFF2 files and the licence to static/fonts/. Both families use the SIL Open Font License,
which allows this.
"""

from __future__ import annotations

import io
import sys
import zipfile
from pathlib import Path

from fontTools import subset
from fontTools.ttLib import TTFont

try:
    import brotli  # noqa: F401  (needed for WOFF2)
    FLAVOR = "woff2"
except ImportError:  # WOFF is a little larger but needs nothing extra
    FLAVOR = "woff"

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "static" / "fonts"

# file name in the zip -> file name on the site
WANTED = {
    "SourceSerif4-VariableFont_opsz,wght.ttf": "source-serif-4-var.woff2",
    "SourceSerif4-Italic-VariableFont_opsz,wght.ttf": "source-serif-4-italic-var.woff2",
    "SourceSans3-VariableFont_wght.ttf": "source-sans-3-var.woff2",
    "SourceSans3-Italic-VariableFont_wght.ttf": "source-sans-3-italic-var.woff2",
}

# Basic Latin, Latin-1, Latin Extended A and B, IPA, extended additional (Vietnamese and more),
# general punctuation, currency, letterlike symbols, arrows, maths operators used in text.
UNICODES = (
    "U+0000-024F,U+0250-02FF,U+0300-036F,U+1E00-1EFF,U+2000-206F,U+20A0-20CF,U+2100-214F,"
    "U+2190-21FF,U+2212,U+2215,U+2248,U+2260,U+2264,U+2265,U+FB01,U+FB02"
)


def _fonts_in(paths):
    for path in map(Path, paths):
        if path.suffix.lower() == ".zip":
            with zipfile.ZipFile(path) as archive:
                for name in archive.namelist():
                    base = name.rsplit("/", 1)[-1]
                    if base in WANTED or base == "OFL.txt":
                        yield base, archive.read(name), path.stem
        else:
            for file in path.rglob("*"):
                if file.name in WANTED or file.name == "OFL.txt":
                    yield file.name, file.read_bytes(), path.name


def build(paths) -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    done = set()
    for name, data, source in _fonts_in(paths):
        if name == "OFL.txt":
            family = "source-serif-4" if "serif" in source.lower() else "source-sans-3"
            (OUT / f"{family}-OFL.txt").write_bytes(data)
            continue
        font = TTFont(io.BytesIO(data))
        options = subset.Options()
        options.flavor = FLAVOR
        options.layout_features = ["*"]
        options.name_IDs = ["*"]
        options.notdef_outline = True
        subsetter = subset.Subsetter(options)
        subsetter.populate(unicodes=subset.parse_unicodes(UNICODES))
        subsetter.subset(font)
        target = OUT / WANTED[name].replace(".woff2", f".{FLAVOR}")
        font.flavor = FLAVOR
        font.save(target)
        done.add(name)
        print(f"{target.relative_to(ROOT)}  {target.stat().st_size // 1024} KB")
    missing = set(WANTED) - done
    if missing:
        print("Not found in the downloads:", ", ".join(sorted(missing)))
        return 1
    return 0


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(2)
    sys.exit(build(sys.argv[1:]))
