"""Read the metadata of an IGLC paper from its Word file, using the template's styles.

Standard library only, so it also runs outside Django (tools, tests, a laptop).

    from apps.production.docx_reader import read_manuscript
    result = read_manuscript("123.docx")
    result.title, result.authors, result.abstract, result.keywords, result.doi, result.issues

The IGLC template marks each part with a paragraph style:

    Title          the paper title
    Authors        "First Author¹, Second Author², & Last Author³" - each name followed by a
                   footnote: "Position, Department, Institution, City, Country, email, orcid.org/…"
    Heading 1      "Abstract", "Keywords", "Introduction", …, "References"
    Text First     the paragraph after a heading (abstract and keywords are one each)
    header (first page)  the citation with pages and DOI, added by the editors

Everything that does not follow this is reported in `issues`, so authors and editors can fix it.
"""

from __future__ import annotations

import re
import unicodedata
import zipfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from xml.etree import ElementTree as ET

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
R = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"

ORCID = re.compile(r"(\d{4}-\d{4}-\d{4}-\d{3}[\dX])")
EMAIL = re.compile(r"[\w.+'-]+@[\w-]+(?:\.[\w-]+)+")
DOI = re.compile(r"10\.24928/(\d{4})/(\d{3,5})")
PAGES = re.compile(r"pp\.\s*(\d+)\s*[-–—]\s*(\d+)")

MANDATORY_HEADINGS = ("abstract", "keywords", "introduction", "references")
# Styles of the template's body text; anything else in the body is reported.
TEMPLATE_STYLES = {
    "title", "authors", "heading 1", "heading 2", "heading 3", "text first", "text running",
    "references", "figure", "figure caption", "table caption", "table body", "table body + left",
    "table heading", "list bullet", "list numbered", "list number", "block quote", "caption",
    "footnote text", "checkgroup", "checkpoint",
}


@dataclass
class ManuscriptAuthor:
    name: str
    first_name: str = ""
    last_name: str = ""
    affiliation: str = ""
    email: str = ""
    orcid: str = ""
    note: str = ""  # the footnote as written


@dataclass
class Manuscript:
    file: str
    title: str = ""
    authors: list[ManuscriptAuthor] = field(default_factory=list)
    abstract: str = ""
    keywords: list[str] = field(default_factory=list)
    headings: list[str] = field(default_factory=list)
    doi: str = ""
    first_page: int | None = None
    last_page: int | None = None
    citation: str = ""
    citation_title: str = ""  # the title as the editors wrote it in the citation header
    track: str = ""
    issues: list[str] = field(default_factory=list)

    def as_dict(self):
        return asdict(self)


# ---------------------------------------------------------------- XML helpers

def _text(element) -> str:
    """Visible text of a paragraph or run: text, tabs and breaks, but not deleted text."""
    parts = []
    for node in element.iter():
        if node.tag == W + "t":
            parts.append(node.text or "")
        elif node.tag in (W + "tab",):
            parts.append(" ")
        elif node.tag in (W + "br", W + "cr"):
            parts.append(" ")
        elif node.tag == W + "noBreakHyphen":
            parts.append("-")
    return "".join(parts)


def _clean(text: str) -> str:
    text = unicodedata.normalize("NFC", text.replace(" ", " ").replace("­", ""))
    return re.sub(r"\s+", " ", text).strip()


def _style_names(archive) -> dict[str, str]:
    try:
        root = ET.fromstring(archive.read("word/styles.xml"))
    except KeyError:
        return {}
    names = {}
    for style in root.iter(W + "style"):
        name = style.find(W + "name")
        names[style.get(W + "styleId")] = (name.get(W + "val") if name is not None else "").lower()
    return names


def _paragraph_style(paragraph, names) -> str:
    style = paragraph.find(f"{W}pPr/{W}pStyle")
    style_id = style.get(W + "val") if style is not None else "Normal"
    return names.get(style_id, style_id.lower())


def _notes(archive, part="word/footnotes.xml") -> dict[str, list[str]]:
    """Footnote id -> its paragraphs."""
    try:
        root = ET.fromstring(archive.read(part))
    except KeyError:
        return {}
    return {note.get(W + "id"): [t for t in (_clean(_text(p)) for p in note.iter(W + "p")) if t]
            for note in root.iter(W + "footnote")}


def _numbered_notes(notes, note_order) -> tuple[dict[int, str], dict[str, int]]:
    """Affiliation texts by the number the reader sees.

    Word numbers footnotes in the order they are referenced, so a footnote's number is its
    position. Authors who share affiliations often put several numbered affiliations in one
    footnote ("3 Professor, …", "4 PhD student, …") and type the numbers after the names, and
    edited files can have a footnote whose text ended up in the one before. So: a paragraph
    that starts with a number is that number's affiliation; an unnumbered first paragraph
    belongs to the footnote's own number; other paragraphs continue the one before.
    Returns number -> text and footnote id -> number.
    """
    by_number, first_number, explicit = {}, {}, set()
    for position, note_id in enumerate(note_order, 1):
        if note_id in first_number:
            continue
        first_number[note_id] = position
        last = None
        for index, paragraph in enumerate(notes.get(note_id, [])):
            match = re.match(r"^(\d{1,2})(?:[\s.)]+|(?=[^\W\d_]))(.*)$", paragraph)
            if match:
                number = int(match.group(1))
                by_number[number], last = match.group(2), number
                explicit.add(number)
            elif index == 0:
                if position not in explicit:
                    by_number[position] = paragraph
                last = position
            elif last is not None:
                by_number[last] += " " + paragraph
    return by_number, first_number


def _header_footer_texts(archive) -> dict[str, str]:
    """Texts of headers and footers by their role: first page, even, default."""
    rels = ET.fromstring(archive.read("word/_rels/document.xml.rels"))
    targets = {rel.get("Id"): "word/" + rel.get("Target").lstrip("/").removeprefix("word/") for rel in rels}
    root = ET.fromstring(archive.read("word/document.xml"))
    found = {}
    for ref in root.iter():
        if ref.tag in (W + "headerReference", W + "footerReference"):
            kind = ("header" if ref.tag == W + "headerReference" else "footer") + "_" + ref.get(W + "type", "default")
            target = targets.get(ref.get(R + "id"))
            if target and kind not in found:
                try:
                    found[kind] = _clean(_text(ET.fromstring(archive.read(target))))
                except KeyError:
                    pass
    return found


# ---------------------------------------------------------------- authors

_SEPARATORS = re.compile(r"^\s*(?:,|&|\band\b|;)\s*|\s*(?:,|&|\band\b|;)\s*$")


def _strip_separators(text: str) -> str:
    previous = None
    while previous != text:
        previous, text = text, _SEPARATORS.sub("", text).strip()
    return text


SUPERSCRIPT_DIGITS = str.maketrans("⁰¹²³⁴⁵⁶⁷⁸⁹", "0123456789")


def _author_tokens(paragraph):
    """The Authors paragraph as a list of ("text", str), ("note", footnote id) and ("number", n).

    A footnote is either a real footnote reference, or - when co-authors share an affiliation -
    its number typed (or cross-referenced) in superscript after the name. Numbers are mapped
    to footnotes by their order in the document, the way Word numbers them.
    """
    tokens = []
    for run in paragraph.iter(W + "r"):
        reference = run.find(W + "footnoteReference")
        if reference is not None:
            tokens.append(("note", reference.get(W + "id")))
            continue
        text = "".join(t.text or "" for t in run.findall(W + "t"))
        if not text:
            continue
        align = run.find(f"{W}rPr/{W}vertAlign")
        superscript = align is not None and align.get(W + "val") == "superscript"
        # Superscript digits typed as characters (¹²³) count as well.
        text = re.sub(r"[⁰¹²³⁴⁵⁶⁷⁸⁹]+", lambda m: "^" + m.group(0).translate(SUPERSCRIPT_DIGITS) + "^", text)
        for part in re.split(r"(\^\d+\^)", text):
            if re.fullmatch(r"\^\d+\^", part):
                superscript_part, part = True, part.strip("^")
            else:
                superscript_part = superscript
            if superscript_part and re.fullmatch(r"[\d,\s]+", part):
                tokens.extend(("number", int(n)) for n in re.findall(r"\d+", part))
                tokens.append(("text", " " if part.strip() == "" else ""))
            elif part:
                # A number typed right after a name without superscript: "Naik2, …"
                for piece in re.split(r"(?<=[^\W\d_])(\d{1,2})(?=\s*(?:,|&|$))", part):
                    if piece.isdigit():
                        tokens.append(("number", int(piece)))
                    elif piece:
                        tokens.append(("text", piece))
    return tokens


def orcid_checksum_ok(orcid: str) -> bool:
    """ISO 7064 11,2 check digit, as used by ORCID."""
    digits = orcid.replace("-", "")
    total = 0
    for char in digits[:-1]:
        total = (total + int(char)) * 2
    check = (12 - total % 11) % 11
    return digits[-1] == ("X" if check == 10 else str(check))


def split_name(name: str) -> tuple[str, str]:
    """First and last name. Multi-word last names are left to the author check."""
    parts = name.split()
    if len(parts) < 2:
        return "", name
    return " ".join(parts[:-1]), parts[-1]


def parse_affiliation(note: str) -> dict:
    orcid = ORCID.search(note)
    email = EMAIL.search(note)
    rest = note
    for match in (orcid, email):
        if match:
            rest = rest.replace(match.group(0), "")
    rest = re.sub(r"(https?://)?(www\.)?orcid\.org/?", "", rest, flags=re.I)
    rest = re.sub(r"\b(e-?mail|orcid)\s*:?", "", rest, flags=re.I)
    rest = re.sub(r"\s*,(\s*,)+", ",", rest)
    return {
        "affiliation": rest.strip(" ,;.") ,
        "email": email.group(0).rstrip(".") if email else "",
        "orcid": orcid.group(1) if orcid else "",
    }


def _read_authors(paragraphs, notes, note_order, issues) -> list[ManuscriptAuthor]:
    by_number, first_number = _numbered_notes(notes, note_order)
    authors, current, pending_text = [], [], ""
    for paragraph in paragraphs:
        for kind, value in _author_tokens(paragraph):
            if kind == "text":
                pending_text += value
            else:
                value = first_number.get(value) if kind == "note" else value
                name = _clean(_strip_separators(_clean(pending_text)))
                pending_text = ""
                if name:
                    current.append([name, [value]])
                elif current and value not in current[-1][1]:
                    current[-1][1].append(value)  # more than one note on one name
        pending_text += ", "
    rest = _strip_separators(_clean(pending_text))
    for name in filter(None, (_clean(n) for n in re.split(r",|&|\band\b", rest))):
        current.append([name, []])
        issues.append(f"Author “{name}” has no footnote with affiliation")

    for name, note_ids in current:
        name = re.sub(r"[\d*†‡§]+$", "", name).strip()
        missing = [n for n in note_ids if n not in by_number]
        if missing:
            issues.append(f"{name} refers to footnote {', '.join(map(str, missing))}, which does not exist")
        note = " / ".join(by_number[n] for n in note_ids if n in by_number).strip()
        first, last = split_name(name)
        author = ManuscriptAuthor(name=name, first_name=first, last_name=last, note=note, **parse_affiliation(note))
        if note and not author.email:
            issues.append(f"No email address in the footnote of {name}")
        if note and not author.orcid:
            if re.search(r"orcid", note, re.I):
                issues.append(f"The ORCID of {name} is not a valid ORCID iD")
            else:
                issues.append(f"No ORCID in the footnote of {name}")
        elif author.orcid and not orcid_checksum_ok(author.orcid):
            issues.append(f"The ORCID of {name} ({author.orcid}) has a wrong check digit")
        if re.search(r"\b(dr|prof|phd)\b\.?", name, re.I):
            issues.append(f"Author name “{name}” includes a title")
        authors.append(author)
    return authors


# ---------------------------------------------------------------- main

def read_manuscript(path) -> Manuscript:
    path = Path(path)
    result = Manuscript(file=path.name)
    issues = result.issues
    try:
        archive = zipfile.ZipFile(path)
        root = ET.fromstring(archive.read("word/document.xml"))
    except (zipfile.BadZipFile, KeyError) as error:
        issues.append(f"Not a readable Word (.docx) file: {error}")
        return result

    names = _style_names(archive)
    notes = _notes(archive)
    body = root.find(W + "body")
    paragraphs = [(p, _paragraph_style(p, names), _clean(_text(p))) for p in body.iter(W + "p")]
    top_level = {id(p) for p in body.findall(W + "p")}

    note_order = [ref.get(W + "id") for ref in body.iter(W + "footnoteReference")]
    title = [text for p, style, text in paragraphs if style == "title" and text]
    author_paragraphs = [p for p, style, text in paragraphs if style == "authors" and text]
    if not title:
        # Often the title is typed in the Authors style: then it is the first of two such paragraphs.
        first = next(((p, style, text) for p, style, text in paragraphs if text), None)
        if first and first[1] != "heading 1" and first[0].find(f".//{W}footnoteReference") is None:
            title = [first[2]]
            if first[0] in author_paragraphs:
                author_paragraphs.remove(first[0])
            issues.append(f"The title is in the “{first[1]}” style, not the Title style")
        else:
            issues.append("No paragraph with the Title style")
    result.title = " ".join(title)

    if author_paragraphs:
        result.authors = _read_authors(author_paragraphs, notes, note_order, issues)
    else:
        issues.append("No paragraph with the Authors style")

    # Sections by Heading 1
    sections, current = {}, None
    for p, style, text in paragraphs:
        if style == "heading 1":
            current = text.lower().rstrip(":. ")
            sections.setdefault(current, [])
            result.headings.append(text)
        elif current and text and id(p) in top_level:
            sections[current].append((style, text))

    abstract = sections.get("abstract")
    if abstract:
        result.abstract = " ".join(text for _, text in abstract)
        words = len(result.abstract.split())
        if words > 200:
            issues.append(f"Abstract has {words} words (maximum 200)")
    else:
        issues.append("No “Abstract” heading (Heading 1)")

    keywords = sections.get("keywords")
    if keywords:
        line = " ".join(text for _, text in keywords)
        result.keywords = [k.strip(" .") for k in re.split(r"[;,]", line) if k.strip(" .")]
        if len(result.keywords) > 5:
            issues.append(f"{len(result.keywords)} keywords (maximum five)")
    else:
        issues.append("No “Keywords” heading (Heading 1)")

    for heading in MANDATORY_HEADINGS[2:]:
        if heading not in sections:
            issues.append(f"No “{heading.capitalize()}” heading (Heading 1)")

    letters = [c for c in result.title if c.isalpha()]
    if letters and sum(c.isupper() for c in letters) / len(letters) > 0.8:
        issues.append("The title is typed in capitals (the Title style adds capitals itself)")
    if len(result.title) > 90:
        issues.append(f"Title has {len(result.title)} characters (maximum 90)")

    # Styles outside the template
    stray = {}
    for p, style, text in paragraphs:
        if text and style not in TEMPLATE_STYLES and not style.startswith(("toc", "bibliography")):
            stray[style] = stray.get(style, 0) + 1
    for style, count in sorted(stray.items(), key=lambda item: -item[1]):
        issues.append(f"{count} paragraph{'s' if count > 1 else ''} in style “{style}”, which is not a template style")

    # Editors' header and footer: citation, DOI, pages, track
    texts = _header_footer_texts(archive)
    citation = texts.get("header_first", "")
    result.citation = citation
    doi = DOI.search(citation) or DOI.search(" ".join(texts.values()))
    if doi:
        result.doi = doi.group(0)
    cited_title = re.search(r"\(\d{4}\)\.\s*(.+?)\.?\s+In [A-Z]\.", citation)
    if cited_title:
        result.citation_title = cited_title.group(1).strip()
    pages = PAGES.search(citation)
    if pages:
        result.first_page, result.last_page = int(pages.group(1)), int(pages.group(2))
    result.track = re.sub(r"\d+$", "", texts.get("footer_first", "") or texts.get("footer_default", "")).strip()
    return result


if __name__ == "__main__":  # python -m apps.production.docx_reader file.docx
    import json
    import sys

    for name in sys.argv[1:]:
        print(json.dumps(read_manuscript(name).as_dict(), ensure_ascii=False, indent=1))
