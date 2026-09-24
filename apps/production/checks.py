"""Template checks for IGLC papers, with a level per submission stage.

Each check has a code. RULES gives, per stage, what happens when a check finds something:

    reject  must be fixed before the paper is accepted
    warn    should be fixed; the editors may send the paper back
    note    for information
    (absent) not checked at that stage

The levels are set here for now; the submission system will let the admin change them per
conference and stage.
"""

from __future__ import annotations

import re
import zipfile
from dataclasses import dataclass
from xml.etree import ElementTree as ET

from .docx_reader import W, Manuscript, read_manuscript

STAGES = {
    "review": "Full paper for review (anonymous)",
    "camera_ready": "Camera-ready paper",
}
# The editors' upload: the camera-ready rules, and the PDF's layout.
PRODUCTION = "production"
LEVELS = {"reject": "Must be fixed", "warn": "Should be fixed", "note": "For information"}
ORDER = {"reject": 0, "warn": 1, "note": 2}

RULES = {
    # code: {stage: level}
    "not_docx": {"review": "reject", "camera_ready": "reject"},
    "title_missing": {"review": "reject", "camera_ready": "reject"},
    "title_wrong_style": {"review": "warn", "camera_ready": "warn"},
    "title_capitals": {"review": "note", "camera_ready": "warn"},
    "title_long": {"review": "warn", "camera_ready": "warn"},
    "authors_missing": {"review": "reject", "camera_ready": "reject"},
    "author_no_affiliation": {"camera_ready": "reject"},
    "footnote_missing": {"camera_ready": "reject"},
    "author_no_email": {"camera_ready": "warn"},
    "author_no_orcid": {"camera_ready": "warn"},
    "orcid_invalid": {"camera_ready": "warn"},
    "author_title_in_name": {"camera_ready": "warn"},
    "abstract_missing": {"review": "reject", "camera_ready": "reject"},
    "abstract_long": {"review": "warn", "camera_ready": "warn"},
    "keywords_missing": {"review": "reject", "camera_ready": "reject"},
    "keywords_many": {"review": "warn", "camera_ready": "warn"},
    "heading_missing": {"review": "reject", "camera_ready": "reject"},
    "non_template_styles": {"review": "warn", "camera_ready": "warn"},
    "page_setup_changed": {"review": "reject", "camera_ready": "reject"},
    "too_many_pages": {"review": "reject", "camera_ready": "reject"},
    "pdf_not_checked": {"review": "note", "camera_ready": "note"},
    "pdf_unreadable": {"review": "warn", "camera_ready": "warn"},
    # The PDF's layout, for the proceedings (checked when editors upload)
    "pdf_not_from_word": {"production": "reject"},
    "pdf_running_left": {"production": "reject"},
    "reference_space_missing": {"production": "reject"},
    "pdf_missing": {"production": "warn"},
    "not_anonymous": {"review": "reject"},
    "file_properties_names": {"review": "warn"},
    "track_changes_or_comments": {"review": "warn", "camera_ready": "reject"},
}

MAX_PAGES = 12
A4 = (11906, 16838)
MARGIN = 1418  # twips, 2.5 cm
TOLERANCE = 30


@dataclass
class Finding:
    code: str
    level: str
    message: str

    @property
    def level_label(self):
        return LEVELS[self.level]


@dataclass
class CheckResult:
    stage: str
    manuscript: Manuscript
    findings: list[Finding]

    @property
    def passed(self) -> bool:
        return not any(f.level == "reject" for f in self.findings)

    def count(self, level):
        return sum(1 for f in self.findings if f.level == level)


def _extra_checks(path, manuscript) -> list[tuple[str, str]]:
    found = []
    try:
        archive = zipfile.ZipFile(path)
        xml = archive.read("word/document.xml").decode("utf-8")
    except (zipfile.BadZipFile, KeyError):
        return found

    # Page size and margins of every section
    for size in re.findall(r"<w:pgSz\b[^>]*>", xml):
        w, h = (int(re.search(rf'w:{k}="(\d+)"', size).group(1)) for k in ("w", "h"))
        if abs(w - A4[0]) > TOLERANCE or abs(h - A4[1]) > TOLERANCE:
            if not (abs(w - A4[1]) <= TOLERANCE and abs(h - A4[0]) <= TOLERANCE):  # landscape A4 is fine
                found.append(("page_setup_changed", "The page size is not A4"))
                break
    for margins in re.findall(r"<w:pgMar\b[^>]*>", xml):
        values = {k: int(v) for k, v in re.findall(r'w:(top|bottom|left|right)="(-?\d+)"', margins)}
        if any(abs(v - MARGIN) > TOLERANCE for v in values.values()):
            found.append(("page_setup_changed", "The page margins differ from the template (2.5 cm on all sides)"))
            break

    if "<w:ins " in xml or "<w:del " in xml or "word/comments.xml" in archive.namelist() and "<w:commentReference" in xml:
        found.append(("track_changes_or_comments", "The file contains tracked changes or comments: accept or reject them and delete the comments"))

    # Anonymity (review stage)
    author_text = " ".join(a.name for a in manuscript.authors)
    if manuscript.authors and not re.search(r"x{3,}|anonym|author", author_text, re.I):
        found.append(("not_anonymous", "The author names are not anonymised (use XXXX until the paper is accepted)"))
    if any(a.email for a in manuscript.authors):
        found.append(("not_anonymous", "The author footnotes contain email addresses"))
    try:
        core = archive.read("docProps/core.xml").decode("utf-8")
        names = [n for n in re.findall(r"<(?:dc:creator|cp:lastModifiedBy)>([^<]+)<", core) if n.strip()]
        if names:
            found.append(("file_properties_names", "The file properties contain the name(s) " + ", ".join(sorted(set(names)))
                          + " (File → Info → Inspect document → Remove all)"))
    except KeyError:
        pass
    return found


def _page_checks(pdf, stage=None) -> list[tuple[str, str]]:
    """The page count can only be known from Word's own layout, so from a PDF made by Word."""
    if pdf is None and stage == PRODUCTION:
        return [("pdf_missing", "No PDF yet: upload the PDF made by Word together with the Word file")]
    if pdf is None:
        return [("pdf_not_checked", f"The number of pages was not checked (maximum {MAX_PAGES}). "
                                    "Upload a PDF of the paper, saved from Word, to check it.")]
    try:
        from pypdf import PdfReader

        pages = len(PdfReader(pdf).pages)
    except Exception:  # noqa: BLE001 - any unreadable PDF
        return [("pdf_unreadable", "The PDF could not be read, so the number of pages was not checked")]
    if pages > MAX_PAGES:
        return [("too_many_pages", f"The paper has {pages} pages (maximum {MAX_PAGES})")]
    return []


def _layout_checks(pdf_bytes) -> list[tuple[str, str]]:
    import io

    from .pdf_running import layout_findings, strip_running

    try:
        writer, removed = strip_running(io.BytesIO(pdf_bytes))
    except Exception:  # noqa: BLE001 - reported by the page check already
        return []
    return layout_findings(writer, removed)


def check_paper(path, stage: str = "camera_ready", pdf=None) -> CheckResult:
    """Check a Word file (and optionally the PDF Word made of it) for a stage."""
    import io
    from pathlib import Path

    pdf_bytes = None
    if pdf is not None:
        pdf_bytes = Path(pdf).read_bytes() if isinstance(pdf, (str, Path)) else pdf.read()
    manuscript = read_manuscript(path)
    raw = (list(zip(manuscript.issues.codes, manuscript.issues)) + _extra_checks(path, manuscript)
           + _page_checks(io.BytesIO(pdf_bytes) if pdf_bytes else None, stage))
    if stage == PRODUCTION and pdf_bytes:
        raw += _layout_checks(pdf_bytes)
    # One line per kind of missing author detail, not one per author
    grouped, merged = {}, []
    for code, message in raw:
        if code in ("author_no_email", "author_no_orcid"):
            grouped.setdefault(code, []).append(message.rsplit(" of ", 1)[-1])
        else:
            merged.append((code, message))
    labels = {"author_no_email": "No email address in the footnote of", "author_no_orcid": "No ORCID in the footnote of"}
    merged += [(code, f"{labels[code]} {', '.join(names)}") for code, names in grouped.items()]
    raw = merged
    findings = []
    for code, message in raw:
        rule = RULES.get(code, {})
        level = rule.get(stage) or (rule.get("camera_ready") if stage == PRODUCTION else None)
        if level:
            findings.append(Finding(code, level, message))
    findings.sort(key=lambda f: ORDER[f.level])
    return CheckResult(stage, manuscript, findings)
