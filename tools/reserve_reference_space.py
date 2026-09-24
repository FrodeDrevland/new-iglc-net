"""Prepare a Word template or paper for references printed on the PDF (trial for IGLC 35).

- The Title style gets 40 pt space before (was 18 pt), so a first-page reference of up to
  five lines fits above the title.
- The first-page header gets a one-line note instead of the reference.

    python tools/reserve_reference_space.py IN.docx|IN.dotx OUT [--note "text"]
"""

import argparse
import re
import sys
import tempfile
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from apps.production.stamp import RunningText, stamp  # noqa: E402

TITLE_SPACE_BEFORE = 800  # twips (40 pt)
NOTE = "The reference with DOI and page numbers is added here when the proceedings are made."


def set_title_spacing(path: Path, twips: int) -> bool:
    with zipfile.ZipFile(path) as archive:
        contents = {info.filename: archive.read(info.filename) for info in archive.infolist()}
    styles = contents["word/styles.xml"].decode("utf-8")
    match = re.search(r'<w:style [^>]*w:styleId="Title".*?</w:style>', styles, re.S)
    if not match:
        return False
    block = match.group(0)
    if re.search(r"<w:spacing\b[^>]*w:before=", block):
        new = re.sub(r'(<w:spacing\b[^>]*w:before=")\d+"', rf'\g<1>{twips}"', block, count=1)
    elif "<w:spacing" in block:
        new = block.replace("<w:spacing", f'<w:spacing w:before="{twips}"', 1)
    else:
        new = block.replace("<w:pPr>", f'<w:pPr><w:spacing w:before="{twips}"/>', 1)
    contents["word/styles.xml"] = styles.replace(block, new).encode("utf-8")
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in contents.items():
            archive.writestr(name, data)
    return True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("source")
    parser.add_argument("target")
    parser.add_argument("--note", default=NOTE, help='text for the first-page header; " " for an empty line')
    args = parser.parse_args()
    stamp(args.source, args.target, RunningText(header_first=args.note))
    ok = set_title_spacing(Path(args.target), TITLE_SPACE_BEFORE)
    print(f"{args.target}: first-page header replaced; Title spacing {'set' if ok else 'NOT FOUND'}")


if __name__ == "__main__":
    main()
