"""Check an IGLC paper against the template (the same checks as www.iglc.net).

    python check_paper.py PAPER.docx [--stage review|camera_ready] [--pdf PAPER.pdf] [--json]
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from iglc_check.checks import LEVELS, STAGES, check_paper  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("paper")
    parser.add_argument("--stage", choices=list(STAGES), default="camera_ready")
    parser.add_argument("--pdf")
    parser.add_argument("--json", action="store_true", help="print everything as JSON")
    args = parser.parse_args()

    result = check_paper(args.paper, args.stage, args.pdf)
    m = result.manuscript
    if args.json:
        data = m.as_dict()
        data["stage"], data["passed"] = args.stage, result.passed
        data["findings"] = [{"level": f.level, "code": f.code, "message": f.message} for f in result.findings]
        print(json.dumps(data, ensure_ascii=False, indent=1))
        return

    print(f"IGLC template check – {STAGES[args.stage]}: {'PASSED' if result.passed else 'NOT PASSED'}\n")
    print(f"Title:    {m.title or '(none found)'}")
    for a in m.authors:
        print(f"Author:   {a.name}" + (f" – {a.affiliation}" if a.affiliation else "")
              + (f", {a.email}" if a.email else "") + (f", ORCID {a.orcid}" if a.orcid else ""))
    print(f"Keywords: {', '.join(m.keywords) or '(none found)'}")
    print(f"Abstract: {len(m.abstract.split())} words\n")
    for level, label in LEVELS.items():
        items = [f for f in result.findings if f.level == level]
        if items:
            print(f"{label} ({len(items)}):")
            for f in items:
                print(f"  - {f.message}")
            print()
    if not result.findings:
        print("No problems found.")


if __name__ == "__main__":
    main()
