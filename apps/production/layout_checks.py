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

def layout_checks(path, abstract: str = "", manual_threshold: int = MANUAL_THRESHOLD) -> list[tuple[str, str]]:
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

    found += _body_text_styles(elements, names)
    found += _manual_formatting(elements, names, archive, manual_threshold)
    found += _changed_styles(path)
    return found


BODY_STYLES = {"text first", "text running"}


def _body_text_styles(elements, names) -> list[tuple[str, str]]:
    """Text First for the first body paragraph after anything else (a heading, figure, table,
    list, quote …), Text Running for a body paragraph that follows another one."""
    from .docx_reader import TEMPLATE_STYLES

    first_wrong, running_wrong = [], []
    previous = None  # the style of the previous paragraph with content, "table" for a table
    for element in elements:
        if element.tag == W + "tbl":
            previous = "table"
            continue
        if element.tag != W + "p" or not _has_content(element):
            continue
        if not _text(element) and not _is_figure(element):
            continue  # a page or section break
        style = _style(element, names)
        # After a paragraph in a style that is not the template's (often Normal), the right choice is
        # unclear: that paragraph is reported by the style check instead.
        known = previous is None or previous == "table" or previous in TEMPLATE_STYLES
        if known and previous is not None:
            if style == "text first" and previous in BODY_STYLES:
                first_wrong.append(_text(element))
            elif style == "text running" and previous not in BODY_STYLES:
                running_wrong.append(_text(element))
        previous = style
    if not first_wrong and not running_wrong:
        return []
    parts = []
    if first_wrong:
        parts.append(f"{len(first_wrong)} in Text First that follow{'s' if len(first_wrong) == 1 else ''} another "
                     f"body paragraph (should be Text Running), e.g. “{_short(first_wrong[0])}”")
    if running_wrong:
        parts.append(f"{len(running_wrong)} in Text Running after a heading, figure, table, list or quote "
                     f"(should be Text First), e.g. “{_short(running_wrong[0])}”")
    total = len(first_wrong) + len(running_wrong)
    return [("text_first_running", f"{total} body paragraph{'s' if total > 1 else ''} in the wrong style: "
                                   + "; ".join(parts))]


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


def _manual_formatting(elements, names, archive, threshold=MANUAL_THRESHOLD) -> list[tuple[str, str]]:
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
    fonts, sizes, spacing = (n if n >= threshold else 0 for n in (fonts, sizes, spacing))
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


# ---------------------------------------------------------------- more content checks

A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
R = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
KEYWORDS_FILE = Path(__file__).with_name("iglc_keywords.txt")
CAPTION_STYLES = {"figure caption", "table caption", "caption"}


def _image_size(data: bytes) -> tuple[int, int] | None:
    """Pixel width and height of a PNG, JPEG, GIF or BMP; None for other (vector) formats."""
    import struct

    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return struct.unpack(">II", data[16:24])
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return struct.unpack("<HH", data[6:10])
    if data[:2] == b"BM":
        width, height = struct.unpack("<ii", data[18:26])
        return width, abs(height)
    if data[:2] == b"\xff\xd8":
        i = 2
        while i + 9 < len(data):
            if data[i] != 0xFF:
                i += 1
                continue
            marker = data[i + 1]
            if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
                height, width = struct.unpack(">HH", data[i + 5:i + 9])
                return width, height
            length = struct.unpack(">H", data[i + 2:i + 4])[0]
            i += 2 + length
    return None


def image_resolution(path, elements, min_dpi: int) -> list[tuple[str, str]]:
    """Pictures whose pixels are too few for the size they are shown at."""
    try:
        archive = zipfile.ZipFile(path)
        rels = ET.fromstring(archive.read("word/_rels/document.xml.rels"))
    except (KeyError, zipfile.BadZipFile, ET.ParseError):
        return []
    targets = {rel.get("Id"): rel.get("Target") for rel in rels}
    low = []
    for element in elements:
        for drawing in element.iter(W + "drawing"):
            extent = drawing.find(f".//{WP}extent")
            blip = drawing.find(f".//{A}blip")
            if extent is None or blip is None:
                continue
            target = targets.get(blip.get(R + "embed"), "")
            name = "word/" + target.lstrip("/").removeprefix("word/") if target else ""
            try:
                size = _image_size(archive.read(name))
            except KeyError:
                continue
            if not size:
                continue  # a vector format
            inches = int(extent.get("cx", 0)) / 914400
            if inches > 0.5:
                dpi = size[0] / inches
                if dpi < min_dpi:
                    low.append(round(dpi))
    if not low:
        return []
    return [("image_resolution", f"{len(low)} picture{'s have' if len(low) > 1 else ' has'} too low a resolution for "
                                 f"the size shown (lowest {min(low)} pixels per inch; at least {min_dpi} needed): "
                                 "insert the original image, or a larger export of it")]


def _numbers(text: str) -> set[int]:
    """'2, 3 and 5–7' -> {2, 3, 5, 6, 7}."""
    found = set()
    for start, end in re.findall(r"(\d+)(?:\s*[–-]\s*(\d+))?", text):
        a, b = int(start), int(end or start)
        if b >= a and b - a < 50:
            found.update(range(a, b + 1))
    return found


def figure_table_citations(elements, names) -> list[tuple[str, str]]:
    """Every numbered figure and table mentioned in the text."""
    captions = {"figure": set(), "table": set()}
    text = []
    for element in elements:
        for paragraph in element.iter(W + "p"):
            content = _text(paragraph)
            if not content:
                continue
            style = _style(paragraph, names)
            label = re.match(r"(fig(?:ure)?|table)\.?\s*(\d+)", content, re.I)
            if style in CAPTION_STYLES and label:
                captions["table" if label.group(1).lower() == "table" else "figure"].add(int(label.group(2)))
            else:
                text.append(content)
    body = " ".join(text)
    mentioned = {"figure": set(), "table": set()}
    series = r"((?:\d+(?:\s*[–-]\s*\d+)?)(?:\s*(?:,|and|&)\s*\d+(?:\s*[–-]\s*\d+)?)*)"
    for word, numbers in re.findall(rf"\b(Fig(?:ure)?s?\.?|Tables?)\s+{series}", body, re.I):
        mentioned["table" if word.lower().startswith("table") else "figure"] |= _numbers(numbers)
    missing = [f"{kind.title()} {n}" for kind in ("figure", "table") for n in sorted(captions[kind] - mentioned[kind])]
    if not missing:
        return []
    return [("figure_table_not_cited", f"Not mentioned in the text: {', '.join(missing[:6])}"
                                       + (f" and {len(missing) - 6} more" if len(missing) > 6 else "")
                                       + " (refer to every figure and table before it appears)")]


def _surname(entry: str) -> str:
    import unicodedata

    first = re.split(r"[,(]|\s+[A-Z]\.", entry, maxsplit=1)[0]  # "Elf, M." and "Elf M." -> Elf
    plain = unicodedata.normalize("NFKD", first).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z ]", "", plain.lower()).strip()


def reference_list(elements, names) -> list[tuple[str, str]]:
    """The reference list: in the References style and in alphabetical order."""
    entries, inside, wrong_style = [], False, 0
    for element in elements:
        if element.tag != W + "p":
            continue
        content, style = _text(element), _style(element, names)
        if style == "heading 1":
            if inside:
                break
            inside = content.lower().rstrip(":. ") == "references"
            continue
        if inside and content:
            entries.append(content)
            if style != "references":
                wrong_style += 1
    found = []
    if wrong_style:
        found.append(("references_style", f"{wrong_style} entr{'ies' if wrong_style > 1 else 'y'} in the reference list "
                                          "not in the References style"))
    names_in_order = [_surname(e) for e in entries]
    for index in range(1, len(names_in_order)):
        if names_in_order[index] and names_in_order[index - 1] and names_in_order[index] < names_in_order[index - 1]:
            found.append(("references_order", f"The reference list is not in alphabetical order: "
                                              f"“{_short(entries[index])}” comes after “{_short(entries[index - 1])}”"))
            break
    return found


def _normal(term: str) -> str:
    term = term.lower().replace("®", "").replace("-", " ")
    term = re.sub(r"is(ation|e|ed|ing)\b", r"iz\1", term)  # organisation -> organization
    return re.sub(r"\s+", " ", term).strip(" .")


def suggested_keywords() -> set[str]:
    terms = set()
    try:
        lines = KEYWORDS_FILE.read_text(encoding="utf-8").splitlines()
    except OSError:
        return terms
    for line in lines:
        if not line.strip() or line.startswith("#"):
            continue
        for part in re.split(r"[/,]", line):
            base = re.sub(r"\s*\(([^)]*)\)", "", part)
            terms.add(_normal(base))
            for inner in re.findall(r"\(([^)]*)\)", part):
                terms.add(_normal(inner))                                      # (IPD)
                terms.add(_normal(re.sub(r"\(([^)]*)\)", r"\1", part)))        # target cost(ing)
    terms.discard("")
    return terms


def keywords_from_list(keywords: list[str], minimum: int) -> list[tuple[str, str]]:
    if not keywords or minimum <= 0:
        return []
    listed = suggested_keywords()
    if not listed:
        return []
    matched = [k for k in keywords if _normal(re.sub(r"\s*\(([^)]*)\)", "", k)) in listed
               or any(_normal(inner) in listed for inner in re.findall(r"\(([^)]*)\)", k))]
    if len(matched) >= minimum:
        return []
    return [("keywords_not_from_list", f"{len(matched)} of the keywords {'is' if len(matched) == 1 else 'are'} from the "
                                       f"list of suggested IGLC keywords (at least {minimum} asked for)")]


def long_paragraphs(elements, names, limit: int) -> list[tuple[str, str]]:
    long = []
    for element in elements:
        if element.tag != W + "p" or _style(element, names) not in BODY_STYLES:
            continue
        words = len(_text(element).split())
        if words > limit:
            long.append((words, _text(element)))
    if not long:
        return []
    longest = max(long)
    return [("long_paragraphs", f"{len(long)} paragraph{'s' if len(long) > 1 else ''} over {limit} words (longest "
                                f"{longest[0]}: “{_short(longest[1])}”): split into shorter paragraphs")]


def content_checks(path, keywords: list[str], limits: dict) -> list[tuple[str, str]]:
    """The checks above, on the paper's body (the checklist left out)."""
    try:
        archive = zipfile.ZipFile(path)
        root = ET.fromstring(archive.read("word/document.xml"))
    except (zipfile.BadZipFile, KeyError, ET.ParseError):
        return []
    names = _style_ids(archive)
    elements, _ = split_checklist(root.find(W + "body"))
    return (image_resolution(path, elements, limits.get("min_image_dpi", 200))
            + figure_table_citations(elements, names)
            + reference_list(elements, names)
            + keywords_from_list(keywords, limits.get("keywords_from_list", 3))
            + long_paragraphs(elements, names, limits.get("paragraph_words", 250)))
