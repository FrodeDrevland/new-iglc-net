"""Template checks for IGLC papers, with a level per submission stage.

Each check has a code. RULES gives, per stage, what happens when a check finds something:

    reject  must be fixed before the paper is accepted
    warn    should be fixed; the editors may send the paper back
    note    for information
    (absent) not checked at that stage

The levels and limits here are the defaults. On the site they can be changed in the back
office (Settings → Paper check rules / Paper check limits, apps/production/check_config.py);
the authors' skill ZIP carries the site's current settings as check_rules.json.
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
    "orcid_invalid": {"camera_ready": "reject"},  # Crossref refuses the record
    "orcid_duplicate": {"camera_ready": "reject"},  # Crossref refuses the record
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
    # Word's own PDF export can lay out a paper differently from Word's screen (seen on IGLC 34)
    "pdf_pages_differ": {"review": "note", "camera_ready": "warn", "production": "reject"},
    # The PDF's layout, for the proceedings (checked when editors upload)
    "pdf_not_from_word": {"production": "reject"},
    "pdf_running_left": {"production": "reject"},
    "reference_space_missing": {"production": "reject"},
    "pdf_missing": {"production": "warn"},
    "not_anonymous": {"review": "reject"},
    "file_properties_names": {"review": "warn"},
    "track_changes_or_comments": {"review": "warn", "camera_ready": "reject"},
    # Layout (layout_checks.py). "off" switches a check off for a stage.
    "checklist_missing": {"review": "warn", "camera_ready": "warn", "production": "off"},
    "checklist_present": {"production": "reject"},
    "abstract_references": {"review": "warn", "camera_ready": "warn"},
    "empty_paragraphs": {"review": "note", "camera_ready": "warn", "production": "note"},
    "figure_floating": {"review": "warn", "camera_ready": "warn"},
    "caption_position": {"review": "warn", "camera_ready": "warn"},
    "manual_formatting": {"review": "note", "camera_ready": "warn", "production": "note"},
    "styles_changed": {"review": "note", "camera_ready": "warn", "production": "note"},
    "text_first_running": {"review": "note", "camera_ready": "warn", "production": "warn"},
    "image_resolution": {"review": "note", "camera_ready": "warn", "production": "warn"},
    "figure_table_not_cited": {"review": "warn", "camera_ready": "warn", "production": "note"},
    "references_style": {"review": "note", "camera_ready": "warn", "production": "warn"},
    "references_order": {"review": "warn", "camera_ready": "warn", "production": "warn"},
    "keywords_not_from_list": {"review": "note", "camera_ready": "note", "production": "off"},
    "long_paragraphs": {"review": "note", "camera_ready": "note", "production": "off"},
}

MAX_PAGES = 12
# Numbers the checks use; the site's settings override them (configuration()).
LIMITS = {"max_pages": MAX_PAGES, "title_chars": 90, "abstract_words": 200, "keywords": 5,
          "manual_formatting": 10, "min_image_dpi": 200, "paragraph_words": 250, "keywords_from_list": 3}
LEVEL_CHOICES = ("off", "note", "warn", "reject")
# What each check looks for, for the admin page and the documentation.
RULE_LABELS = {
    "not_docx": "The file is not a readable Word (.docx) file",
    "title_missing": "No paragraph in the Title style",
    "title_wrong_style": "The title is in another style than Title",
    "title_capitals": "The title is typed in capitals",
    "title_long": "The title is longer than the limit (characters)",
    "authors_missing": "No paragraph in the Authors style",
    "author_no_affiliation": "An author has no footnote with affiliation",
    "footnote_missing": "An author refers to a footnote that does not exist",
    "author_no_email": "No email address in an author's footnote",
    "author_no_orcid": "No ORCID iD in an author's footnote",
    "orcid_invalid": "An ORCID iD is not valid",
    "orcid_duplicate": "The same ORCID iD given for two authors",
    "author_title_in_name": "An author name includes a title (Dr, Prof …)",
    "abstract_missing": "No Abstract heading",
    "abstract_long": "The abstract is longer than the limit (words)",
    "keywords_missing": "No Keywords heading",
    "keywords_many": "More keywords than the limit",
    "heading_missing": "A mandatory heading (Introduction, References) is missing",
    "non_template_styles": "Paragraphs in styles that are not the template's",
    "page_setup_changed": "Page size or margins differ from the template",
    "too_many_pages": "More pages than the limit (the checklist not counted)",
    "pdf_not_checked": "No PDF uploaded, so the pages were not counted",
    "pdf_unreadable": "The PDF could not be read",
    "pdf_pages_differ": "The PDF has another number of pages than Word counts",
    "pdf_not_from_word": "The PDF was not made by Word (no marked headers/footers)",
    "pdf_running_left": "Text left in the header or footer area of the PDF",
    "reference_space_missing": "No room for the reference above the title on page 1",
    "pdf_missing": "No PDF with the Word file (editors' upload)",
    "not_anonymous": "Author names or emails in a paper under review",
    "file_properties_names": "Names in the file properties of a paper under review",
    "track_changes_or_comments": "Tracked changes or comments in the file",
    "checklist_missing": "The submission checklist is missing",
    "checklist_present": "The submission checklist is still in the file",
    "abstract_references": "References cited in the abstract",
    "empty_paragraphs": "Empty paragraphs between paragraphs",
    "figure_floating": "Figures not placed “In line with text”",
    "caption_position": "Captions not above tables / below figures, or in the wrong style",
    "manual_formatting": "Formatting set by hand (reported from the limit upwards)",
    "styles_changed": "Style definitions differ from the current template",
    "text_first_running": "Body paragraphs in the wrong one of Text First / Text Running",
    "image_resolution": "Pictures with too low a resolution for their size",
    "figure_table_not_cited": "Figures or tables not mentioned in the text",
    "references_style": "Reference list entries not in the References style",
    "references_order": "Reference list not in alphabetical order",
    "keywords_not_from_list": "Too few keywords from the suggested IGLC list",
    "long_paragraphs": "Paragraphs longer than the limit (words)",
}


def default_rules() -> dict[str, dict[str, str]]:
    """Every check with an explicit level for every stage (the editors' upload falls back to the
    camera-ready level, as in RULES)."""
    out = {}
    for code in RULE_LABELS:
        rule = RULES.get(code, {})
        out[code] = {stage: rule.get(stage) or "off" for stage in ("review", "camera_ready")}
        out[code][PRODUCTION] = rule.get(PRODUCTION) or rule.get("camera_ready") or "off"
    return out


def configuration() -> tuple[dict, dict]:
    """(rules, limits) in force: the site's settings, else check_rules.json next to this file
    (the authors' skill), else the defaults here."""
    rules, limits = default_rules(), dict(LIMITS)
    try:
        import json
        from pathlib import Path

        saved = json.loads((Path(__file__).with_name("check_rules.json")).read_text())
        for code, levels in saved.get("rules", {}).items():
            rules.setdefault(code, {}).update(levels)
        limits.update(saved.get("limits", {}))
    except (OSError, ValueError):
        pass
    try:
        from .check_config import load

        site_rules, site_limits = load()
        for code, levels in site_rules.items():
            rules.setdefault(code, {}).update(levels)
        limits.update(site_limits)
    except Exception:  # noqa: BLE001 - outside Django, or no database: the defaults
        pass
    return rules, limits
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


def _page_checks(pdf, stage=None, max_pages: int = MAX_PAGES) -> list[tuple[str, str]]:
    """The page count can only be known from Word's own layout, so from a PDF made by Word."""
    if pdf is None and stage == PRODUCTION:
        return [("pdf_missing", "No PDF yet: upload the PDF made by Word together with the Word file")]
    if pdf is None:
        return [("pdf_not_checked", f"The number of pages was not checked (maximum {max_pages}). "
                                    "Upload a PDF of the paper, saved from Word, to check it.")]
    try:
        from pypdf import PdfReader

        from .layout_checks import checklist_pages

        reader = PdfReader(pdf)
        pages = len(reader.pages) - checklist_pages(reader)  # the checklist does not count
    except Exception:  # noqa: BLE001 - any unreadable PDF
        return [("pdf_unreadable", "The PDF could not be read, so the number of pages was not checked")]
    if pages > max_pages:
        return [("too_many_pages", f"The paper has {pages} pages without the checklist (maximum {max_pages})")]
    return []


def word_page_count(path) -> int | None:
    """The number of pages Word counted when it last saved the file (docProps/app.xml)."""
    try:
        with zipfile.ZipFile(path) as archive:
            xml = archive.read("docProps/app.xml").decode("utf-8", "replace")
    except (KeyError, zipfile.BadZipFile, OSError):
        return None
    match = re.search(r"<(?:\w+:)?Pages>(\d+)</(?:\w+:)?Pages>", xml)
    return int(match.group(1)) if match else None


def _pages_differ(path, pdf_bytes) -> list[tuple[str, str]]:
    import io

    from pypdf import PdfReader

    word = word_page_count(path)
    try:
        pdf = len(PdfReader(io.BytesIO(pdf_bytes)).pages)
    except Exception:  # noqa: BLE001 - reported by the page check
        return []
    if word and word > 1 and word != pdf:  # Word does not always store its count (then it says 1)
        return [("pdf_pages_differ", f"The PDF has {pdf} pages, but Word counts {word}: the PDF was laid out "
                                     "differently from the Word file. Adjust the paper so both agree (for example "
                                     "tighten the text before the extra page break) and save the PDF again")]
    return []


def _layout_checks(pdf_bytes) -> list[tuple[str, str]]:
    import io

    from .pdf_running import layout_findings, strip_running

    try:
        writer, removed = strip_running(io.BytesIO(pdf_bytes))
    except Exception:  # noqa: BLE001 - reported by the page check already
        return []
    return layout_findings(writer, removed)


def check_paper(path, stage: str = "camera_ready", pdf=None, rules=None, limits=None) -> CheckResult:
    """Check a Word file (and optionally the PDF Word made of it) for a stage. The rules and
    limits default to the configured ones (configuration())."""
    import io
    from pathlib import Path

    pdf_bytes = None
    if pdf is not None:
        pdf_bytes = Path(pdf).read_bytes() if isinstance(pdf, (str, Path)) else pdf.read()
    if rules is None or limits is None:
        configured_rules, configured_limits = configuration()
        rules = configured_rules if rules is None else rules
        limits = configured_limits if limits is None else limits
    limits = {**LIMITS, **limits}
    manuscript = read_manuscript(path, limits)
    from .layout_checks import content_checks, layout_checks

    raw = (list(zip(manuscript.issues.codes, manuscript.issues)) + _extra_checks(path, manuscript)
           + layout_checks(path, manuscript.abstract, limits["manual_formatting"])
           + content_checks(path, manuscript.keywords, limits)
           + _page_checks(io.BytesIO(pdf_bytes) if pdf_bytes else None, stage, limits["max_pages"]))
    if pdf_bytes:
        raw += _pages_differ(path, pdf_bytes)
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
        rule = rules.get(code, {})
        level = rule.get(stage) or (rule.get("camera_ready") if stage == PRODUCTION else None)
        if level and level != "off":
            findings.append(Finding(code, level, message))
    findings.sort(key=lambda f: ORDER[f.level])
    return CheckResult(stage, manuscript, findings)
