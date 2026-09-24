"""Checks of the layout of a paper's Word file beyond its metadata (docx_reader.py):
the submission checklist, references in the abstract, empty paragraphs, floating figures,
captions, manual formatting and changed style definitions.

Standard library only, like docx_reader.py.

    findings = layout_checks(path, abstract)    -> [(code, message)]
    snapshot = style_snapshot(path)             -> the template's style settings (for template_styles.json)

The template's checklist ("IGLC Paper Submission Checklist", the last pages) is left out of the
body checks: it has its own look (check boxes in MS Gothic).
"""

from __future__ import annotations

import json
import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
WP = "{http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing}"
M = "{http://schemas.openxmlformats.org/officeDocument/2006/math}"

CHECKLIST_HEADING = "iglc paper submission checklist"
MANUAL_THRESHOLD = 10
STYLES_FILE = Path(__file__).with_name("template_styles.json")

# Citations: (Author, 2020), (Author et al., 2019a; …), Author (2018), [12]
NAME = r"[A-Z][A-Za-z'’\-]+"
CITATION = re.compile(
    rf"\({NAME}(?:\s+(?:et al\.|(?:and|&)\s+{NAME}))?,?\s+(?:19|20)\d{{2}}[a-z]?\b[^()]*\)"  # (Author, 2020)
    rf"|\b{NAME}(?:\s+et al\.|\s+(?:and|&)\s+{NAME})?\s+\((?:19|20)\d{{2}}[a-z]?\)"       # Author (2020)
    r"|\bet al\.|\[\d+(?:\s*[,–-]\s*\d+)*\]")                                         # et al., [12]
# Fonts that are fine to set by hand: symbols, equations, the checklist's boxes
SYMBOL_FONTS = {"symbol", "wingdings", "wingdings 2", "wingdings 3", "cambria math", "ms gothic",
                "segoe ui symbol", "webdings"}
# What a style's definition is compared on
PPR = {"spacing": ("before", "after", "line", "lineRule"), "ind": ("left", "right", "firstLine", "hanging"),
       "jc": ("val",)}
RPR = {"sz": ("val",), "rFonts": ("ascii", "hAnsi"), "b": ("val",), "i": ("val",), "caps": ("val",)}


def _text(element) -> str:
    return "".join(t.text or "" for t in element.iter(W + "t")).strip()


def _style_ids(archive) -> dict[str, str]:
    try:
        root = ET.fromstring(archive.read("word/styles.xml"))
    except KeyError:
        return {}
    names = {}
    for style in root.iter(W + "style"):
        name = style.find(W + "name")
        names[style.get(W + "styleId")] = (name.get(W + "val") if name is not None else "").lower()
    return names


def _style(paragraph, names) -> str:
    style = paragraph.find(f"{W}pPr/{W}pStyle")
    return names.get(style.get(W + "val"), style.get(W + "val").lower()) if style is not None else "normal"


def _has_content(paragraph) -> bool:
    if _text(paragraph):
        return True
    for tag in (W + "drawing", W + "pict", W + "object", M + "oMath", M + "oMathPara", W + "fldChar", W + "sym"):
        if paragraph.find(".//" + tag) is not None:
            return True
    if paragraph.find(f"{W}pPr/{W}sectPr") is not None:
        return True
    return any(br.get(W + "type") in ("page", "column") for br in paragraph.iter(W + "br"))


def _is_figure(paragraph) -> bool:
    return any(paragraph.find(".//" + tag) is not None for tag in (W + "drawing", W + "pict", W + "object"))


def split_checklist(body) -> tuple[list, bool]:
    """The body's elements before the checklist, and whether the checklist is there."""
    elements = list(body)
    for index, element in enumerate(elements):
        if element.tag == W + "p" and _text(element).lower().startswith(CHECKLIST_HEADING):
            return elements[:index], True
    return elements, False


def _short(text: str) -> str:
    return text if len(text) <= 50 else text[:47] + "…"


# ---------------------------------------------------------------- the checks

def layout_checks(path, abstract: str = "") -> list[tuple[str, str]]:
    try:
        archive = zipfile.ZipFile(path)
        root = ET.fromstring(archive.read("word/document.xml"))
    except (zipfile.BadZipFile, KeyError, ET.ParseError):
        return []
    names = _style_ids(archive)
    body = root.find(W + "body")
    elements, checklist = split_checklist(body)
    found = []

    found.append(("checklist_present", "The submission checklist is still in the file: remove it before "
                                       "publication") if checklist else
                 ("checklist_missing", "The submission checklist from the end of the template is missing: "
                                       "include it (it does not count towards the page limit)"))

    cited = CITATION.search(abstract or "")
    if cited:
        found.append(("abstract_references", f"The abstract contains a reference (“{_short(cited.group(0))}”): "
                                             "abstracts must not cite other work"))

    # Empty paragraphs between the parts of the body (Word needs none; spacing comes from the styles)
    empty, pending, previous = [], [], ""
    for element in elements:
        if element.tag == W + "p":
            if not _has_content(element):
                pending.append(previous)
                continue
            if not _text(element) and not _is_figure(element):
                continue  # a page break or section break: neither content nor an empty line
            previous = _text(element) or previous
        elif element.tag == W + "tbl":
            previous = "a table"
        else:
            continue
        empty += pending  # empty paragraphs at the very end (before the checklist) are left alone
        pending = []
    if empty:
        where = f" (the first after “{_short(empty[0])}”)" if empty[0] else ""
        found.append(("empty_paragraphs", f"{len(empty)} empty paragraph{'s' if len(empty) > 1 else ''}{where}: "
                                          "delete them; the styles set the space between paragraphs"))

    # Figures must be "In line with text"
    floating = sum(1 for element in elements for _ in element.iter(WP + "anchor"))
    floating += sum(1 for element in elements for shape in element.iter()
                    if shape.tag.endswith("}shape") and "position:absolute" in (shape.get("style") or ""))
    if floating:
        found.append(("figure_floating", f"{floating} picture{'s' if floating > 1 else ''} or drawing object"
                                         f"{'s are' if floating > 1 else ' is'} not placed “In line with text”: "
                                         "figures must be (right-click → Wrap Text → In Line with Text)"))

    # Captions: table captions above their table, figure captions below their figure
    body_items = [e for e in elements if e.tag == W + "tbl" or (e.tag == W + "p" and _has_content(e))]
    table_wrong, figure_wrong, wrong_style = [], [], []
    for index, element in enumerate(body_items):
        if element.tag != W + "p":
            continue
        style = _style(element, names)
        if style not in ("table caption", "figure caption", "caption"):
            continue
        text = _text(element)
        kind = ("table" if text.lower().startswith("table") else
                "figure" if text.lower().startswith(("fig", "image", "photo")) else style.split()[0])
        if style != "caption" and not style.startswith(kind):
            wrong_style.append(text)
        if kind == "table":
            following = body_items[index + 1] if index + 1 < len(body_items) else None
            if following is None or following.tag != W + "tbl":
                table_wrong.append(text)
        elif kind == "figure":
            before = body_items[index - 1] if index else None
            if before is None or not _is_figure(before) and before.tag != W + "tbl":
                figure_wrong.append(text)
    for wrong, message in ((table_wrong, "Table caption not directly above its table"),
                           (figure_wrong, "Figure caption not directly below its figure"),
                           (wrong_style, "Caption in the wrong style (Table caption for tables, Figure caption "
                                         "for figures)")):
        if wrong:
            found.append(("caption_position", f"{message}: “{_short(wrong[0])}”"
                          + (f" and {len(wrong) - 1} more" if len(wrong) > 1 else "")))

    found += _manual_formatting(elements, names, archive)
    found += _changed_styles(path)
    return found


def _effective_styles(archive) -> dict[str, dict[str, str]]:
    """For each paragraph style id: font, size, spacing and indents, following basedOn."""
    try:
        root = ET.fromstring(archive.read("word/styles.xml"))
    except KeyError:
        return {}
    spec = {"rFonts": ("ascii",), "sz": ("val",), **{k: PPR[k] for k in ("spacing", "ind")}}
    default = {}
    for part in (f"{W}docDefaults/{W}rPrDefault/{W}rPr", f"{W}docDefaults/{W}pPrDefault/{W}pPr"):
        default.update(_settings(root.find(part), spec))
    own, parent = {}, {}
    for style in root.iter(W + "style"):
        if style.get(W + "type") != "paragraph":
            continue
        sid = style.get(W + "styleId")
        own[sid] = {**_settings(style.find(W + "pPr"), spec), **_settings(style.find(W + "rPr"), spec)}
        based = style.find(W + "basedOn")
        parent[sid] = based.get(W + "val") if based is not None else None
        if style.get(W + "default") == "1":
            own.setdefault("__default__", {})
            parent["__default__"] = sid

    def resolve(sid, depth=0):
        if sid is None or sid not in own or depth > 20:
            return dict(default)
        return {**resolve(parent.get(sid), depth + 1), **own[sid]}

    return {sid: resolve(sid) for sid in own}


def _manual_formatting(elements, names, archive) -> list[tuple[str, str]]:
    """Font, size, spacing and indents set by hand to something else than the style says."""
    effective = _effective_styles(archive)
    default_id = next((sid for sid, name in names.items() if name == "normal"), "Normal")
    fonts, sizes, spacing = 0, 0, 0
    for element in elements:
        for paragraph in element.iter(W + "p"):
            if _style(paragraph, names) in ("figure", "footnote text"):
                continue
            style_ref = paragraph.find(f"{W}pPr/{W}pStyle")
            style = effective.get(style_ref.get(W + "val") if style_ref is not None else default_id, {})
            ppr = paragraph.find(W + "pPr")
            if ppr is not None and _text(paragraph):
                here = _settings(ppr, {k: PPR[k] for k in ("spacing", "ind")})
                if any(style.get(key, "0") != value and not (value == "0" and key not in style)
                       for key, value in here.items()):
                    spacing += 1
            for run in paragraph.iter(W + "r"):
                rpr = run.find(W + "rPr")
                if rpr is None or not "".join(t.text or "" for t in run.iter(W + "t")).strip():
                    continue
                font = rpr.find(W + "rFonts")
                if font is not None:
                    face = font.get(W + "ascii") or font.get(W + "hAnsi")
                    if face and face.lower() not in SYMBOL_FONTS and face != style.get("rFonts.ascii"):
                        fonts += 1
                size = rpr.find(W + "sz")
                if size is not None and size.get(W + "val") != style.get("sz.val", "20"):
                    sizes += 1
    # A few are left alone (a symbol, a superscript size); many mean the styles were not used
    fonts, sizes, spacing = (n if n >= MANUAL_THRESHOLD else 0 for n in (fonts, sizes, spacing))
    parts = []
    if fonts:
        parts.append(f"the font of {fonts} piece{'s' if fonts > 1 else ''} of text")
    if sizes:
        parts.append(f"the font size of {sizes} piece{'s' if sizes > 1 else ''} of text")
    if spacing:
        parts.append(f"the spacing or indent of {spacing} paragraph{'s' if spacing > 1 else ''}")
    if not parts:
        return []
    return [("manual_formatting", "Formatting set by hand instead of by the template's styles: "
                                  + ", ".join(parts) + " (select the text and press Ctrl+Space, or Ctrl+Q for "
                                  "paragraph settings)")]


# ---------------------------------------------------------------- style definitions

TOGGLES = {"b", "i", "caps"}
# The styles of the paper's text (not Word's own, such as comments or headers)
COMPARED_STYLES = {"normal", "title", "authors", "heading 1", "heading 2", "heading 3", "text first",
                   "text running", "references", "figure", "figure caption", "table caption", "table body",
                   "table body + left", "table heading", "list bullet", "list numbered", "block quote",
                   "footnote text"}


def _settings(element, spec) -> dict[str, str]:
    out = {}
    if element is None:
        return out
    for tag, attrs in spec.items():
        child = element.find(W + tag)
        if child is None:
            continue
        for attr in attrs:
            value = child.get(W + attr)
            if value is None and tag in TOGGLES:
                value = "on"
            if value is not None:
                out[f"{tag}.{attr}"] = value
    return out


def style_snapshot(path) -> dict:
    """The template's settings for each paragraph style, by style name, and the default font."""
    archive = zipfile.ZipFile(path)
    root = ET.fromstring(archive.read("word/styles.xml"))
    styles = {}
    for style in root.iter(W + "style"):
        if style.get(W + "type") != "paragraph":
            continue
        name = style.find(W + "name")
        settings = {**_settings(style.find(W + "pPr"), PPR), **_settings(style.find(W + "rPr"), RPR)}
        styles[(name.get(W + "val") if name is not None else "").lower()] = settings
    default = root.find(f"{W}docDefaults/{W}rPrDefault/{W}rPr")
    return {"defaults": _settings(default, RPR), "styles": styles}


def _changed_styles(path) -> list[tuple[str, str]]:
    try:
        reference = json.loads(STYLES_FILE.read_text())
    except (OSError, ValueError):
        return []
    try:
        mine = style_snapshot(path)
    except (KeyError, ET.ParseError, zipfile.BadZipFile):
        return []
    changed = []
    if mine["defaults"] != reference["defaults"]:
        changed.append("the default font")
    for name, settings in reference["styles"].items():
        if name not in COMPARED_STYLES:
            continue
        theirs = mine["styles"].get(name)
        if theirs is not None and theirs != settings:
            changed.append(f"“{name.title()}”")
    if not changed:
        return []
    return [("styles_changed", "Style definitions differ from the IGLC 35 template: " + ", ".join(changed[:8])
             + (f" and {len(changed) - 8} more" if len(changed) > 8 else "")
             + " (start from the current template, or copy its styles with the Organizer)")]


# ---------------------------------------------------------------- the PDF

def checklist_pages(reader) -> int:
    """How many pages at the end of a PDF (pypdf reader) are the submission checklist."""
    for index, page in enumerate(reader.pages):
        try:
            text = page.extract_text() or ""
        except Exception:  # noqa: BLE001 - an unreadable page
            continue
        position = text.lower().find(CHECKLIST_HEADING)
        if position < 0:
            continue
        before = re.sub(r"\s+", " ", text[:position]).strip()
        # The heading at the top of its page (under the running header): that page is the checklist's
        starts_page = len(before) < 150
        return len(reader.pages) - index - (0 if starts_page else 1)
    return 0
