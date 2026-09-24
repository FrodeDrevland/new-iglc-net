"""Try the dxpdf converter (pip install dxpdf) on a folder of papers.

Converts every .docx in FOLDER to PDF with dxpdf, counts the pages, and compares them with
the page counts Word gave (pages.csv from tools/word_batch.ps1, or the page ranges in a
read_manuscripts --json file).

    pip install dxpdf
    python tools/try_dxpdf.py _reports/iglc34-stamped --out _reports/iglc34-dxpdf --word _reports/iglc34-pdf/pages.csv
"""

import argparse
import csv
import json
import re
import time
from pathlib import Path

import dxpdf


def pdf_pages(path: Path) -> int:
    data = path.read_bytes()
    counts = re.findall(rb"/Type\s*/Pages\b[^>]*?/Count\s+(\d+)", data, re.S)
    if counts:
        return max(int(c) for c in counts)
    return len(re.findall(rb"/Type\s*/Page[^s]", data))


def word_pages(source: str) -> dict:
    path = Path(source)
    if path.suffix == ".csv":
        with path.open(encoding="utf-8-sig") as handle:
            return {row["file"]: int(row["pages"]) for row in csv.DictReader(handle)}
    return {r["file"]: r["last_page"] - r["first_page"] + 1
            for r in json.loads(path.read_text(encoding="utf-8")) if r.get("first_page")}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("folder")
    parser.add_argument("--out", required=True)
    parser.add_argument("--word", required=True, help="pages.csv from word_batch.ps1, or read_manuscripts JSON")
    args = parser.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    expected = word_pages(args.word)
    rows, same, failed, started = [], 0, 0, time.time()
    for docx in sorted(Path(args.folder).glob("*.docx"), key=lambda p: int(re.sub(r"\D", "", p.stem) or 0)):
        target = out / (docx.stem + ".pdf")
        try:
            dxpdf.convert_file(str(docx), str(target))
            pages = pdf_pages(target)
            note = ""
        except Exception as error:  # noqa: BLE001 - report and carry on
            pages, note = None, f"{type(error).__name__}: {error}"
            failed += 1
        word = expected.get(docx.name)
        same += pages is not None and pages == word
        rows.append({"file": docx.name, "word": word, "dxpdf": pages, "difference": (pages - word) if pages and word else "", "error": note})
        print(f"{docx.name:10} Word {word!s:>3}  dxpdf {pages!s:>3}  {note}")

    with (out / "comparison.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    print(f"\n{len(rows)} papers in {time.time() - started:.0f} s: same page count as Word for {same}, "
          f"different for {len(rows) - same - failed}, failed {failed}. Details in {out / 'comparison.csv'}")


if __name__ == "__main__":
    main()
