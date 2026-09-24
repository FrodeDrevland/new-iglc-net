"""Write the running headers and footers of an IGLC paper and set its first page number.

Standard library only. The editors used to type these by hand in every paper:

    header, first page   the full reference with pages and DOI
    header, even pages   the paper title
    header, odd pages    the authors
    footer, first/odd    the track, and the page number
    footer, even pages   "Proceedings IGLC34, 22–26 June 2026, Singapore", and the page number

`stamp()` replaces the text in those parts and keeps everything else: paragraph and run
formatting, tabs and the PAGE field. The page numbering starts at `first_page`.
"""

from __future__ import annotations

import copy
import re
import shutil
import tempfile
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from xml.etree import ElementTree as ET

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
HYPERLINK_TYPE = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink"
W = "{%s}" % W_NS
R = "{%s}" % R_NS

# Keep the prefixes Word expects when the XML is written back.
_NAMESPACES = {
    "wpc": "http://schemas.microsoft.com/office/word/2010/wordprocessingCanvas",
    "cx": "http://schemas.microsoft.com/office/drawing/2014/chartex",
    "mc": "http://schemas.openxmlformats.org/markup-compatibility/2006",
    "o": "urn:schemas-microsoft-com:office:office",
    "r": R_NS,
    "m": "http://schemas.openxmlformats.org/officeDocument/2006/math",
    "v": "urn:schemas-microsoft-com:vml",
    "wp14": "http://schemas.microsoft.com/office/word/2010/wordprocessingDrawing",
    "wp": "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing",
    "w10": "urn:schemas-microsoft-com:office:word",
    "w": W_NS,
    "w14": "http://schemas.microsoft.com/office/word/2010/wordml",
    "w15": "http://schemas.microsoft.com/office/word/2012/wordml",
    "w16se": "http://schemas.microsoft.com/office/word/2015/wordml/symex",
    "w16cid": "http://schemas.microsoft.com/office/word/2016/wordml/cid",
    "w16": "http://schemas.microsoft.com/office/word/2018/wordml",
    "w16cex": "http://schemas.microsoft.com/office/word/2018/wordml/cex",
    "w16sdtdh": "http://schemas.microsoft.com/office/word/2020/wordml/sdtdatahash",
    "w16sdtfl": "http://schemas.microsoft.com/office/word/2024/wordml/sdtformatlock",
    "w16du": "http://schemas.microsoft.com/office/word/2023/wordml/word16du",
    "wpg": "http://schemas.microsoft.com/office/word/2010/wordprocessingGroup",
    "wpi": "http://schemas.microsoft.com/office/word/2010/wordprocessingInk",
    "wne": "http://schemas.microsoft.com/office/word/2006/wordml",
    "wps": "http://schemas.microsoft.com/office/word/2010/wordprocessingShape",
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "pic": "http://schemas.openxmlformats.org/drawingml/2006/picture",
}
for _prefix, _uri in _NAMESPACES.items():
    ET.register_namespace(_prefix, _uri)
ET.register_namespace("", PKG_NS)  # .rels parts must use the default namespace


@dataclass
class Segment:
    text: str
    italic: bool = False
    link: str = ""  # a URL makes the segment a hyperlink


@dataclass
class RunningText:
    """What goes in each header and footer. Each is a list of segments (or a plain string)."""

    header_first: list = field(default_factory=list)
    header_odd: list = field(default_factory=list)
    header_even: list = field(default_factory=list)
    footer_first: list = field(default_factory=list)
    footer_odd: list = field(default_factory=list)
    footer_even: list = field(default_factory=list)


def _segments(value) -> list[Segment]:
    if isinstance(value, str):
        return [Segment(value)] if value else []
    return [s if isinstance(s, Segment) else Segment(*s) for s in value]


# ---------------------------------------------------------------- XML editing

def _field_runs(paragraph) -> set:
    """Runs that belong to a field (PAGE etc.), which must be kept."""
    keep, depth = set(), 0
    for run in paragraph.iter(W + "r"):
        char = run.find(W + "fldChar")
        if char is not None and char.get(W + "fldCharType") == "begin":
            depth += 1
        if depth:
            keep.add(run)
        if char is not None and char.get(W + "fldCharType") == "end":
            depth = max(0, depth - 1)
    return keep


def _parents(root) -> dict:
    return {child: parent for parent in root.iter() for child in parent}


def _is_text_run(run) -> bool:
    return any(child.tag in (W + "t", W + "delText", W + "sym") for child in run)


def _new_run(template_rpr, segment: Segment):
    run = ET.Element(W + "r")
    rpr = copy.deepcopy(template_rpr) if template_rpr is not None else ET.Element(W + "rPr")
    for tag in ("i", "iCs", "rStyle", "u", "color"):
        for old in rpr.findall(W + tag):
            rpr.remove(old)
    if segment.italic:
        ET.SubElement(rpr, W + "i")
        ET.SubElement(rpr, W + "iCs")
    if segment.link:
        style = ET.Element(W + "rStyle", {W + "val": "Hyperlink"})
        rpr.insert(0, style)
    if len(rpr):
        run.append(rpr)
    text = ET.SubElement(run, W + "t")
    text.text = segment.text
    text.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
    return run


def _replace_text(root, segments: list[Segment], add_link) -> bool:
    """Put `segments` where the first text was; remove all other text outside fields."""
    parents = _parents(root)
    paragraphs = list(root.iter(W + "p"))
    target = None
    for paragraph in paragraphs:
        keep = _field_runs(paragraph)
        text_runs = [r for r in paragraph.iter(W + "r") if r not in keep and _is_text_run(r)]
        # hyperlinks, spell-check marks and bookmarks around the old text go too
        for element in list(paragraph.iter()):
            if element.tag in (W + "hyperlink",) and not any(r in keep for r in element.iter(W + "r")):
                text_runs.extend(r for r in element.iter(W + "r") if r not in text_runs)
        if not text_runs:
            continue
        if target is None:
            first = text_runs[0]
            target = (paragraph, parents[first], list(parents[first]).index(first), first.find(W + "rPr"))
        for run in text_runs:
            parent = parents[run]
            if run in list(parent):
                parent.remove(run)
        for hyperlink in [e for e in paragraph.iter(W + "hyperlink") if not len(e.findall(W + "r"))]:
            parents[hyperlink].remove(hyperlink)
        if paragraph is not (target and target[0]) and not paragraph.findall(f".//{W}r"):
            container = parents.get(paragraph)
            if container is not None and len([p for p in container if p.tag == W + "p"]) > 1:
                container.remove(paragraph)  # an emptied extra line would change the header height

    if target is None:
        # No text before: put it at the start of the first paragraph.
        if not paragraphs:
            return False
        paragraph = paragraphs[0]
        ppr = paragraph.find(W + "pPr")
        target = (paragraph, paragraph, 1 if ppr is not None else 0, None)

    paragraph, parent, index, rpr = target
    if rpr is not None:
        rpr = copy.deepcopy(rpr)
    for offset, segment in enumerate(segments):
        run = _new_run(rpr, segment)
        if segment.link:
            link = ET.Element(W + "hyperlink", {R + "id": add_link(segment.link), W + "history": "1"})
            link.append(run)
            run = link
        parent.insert(index + offset, run)
    return True


def _set_first_page(xml: str, first_page: int) -> str:
    """Number the first section from `first_page`; later sections continue.

    Edited as text, so the rest of the (large) document stays byte for byte as it was.
    """
    def section(match, counter=[0]):
        text = match.group(0)
        first = counter[0] == 0
        counter[0] += 1
        text = re.sub(r'(<w:pgNumType\b[^>]*?)\s+w:start="\d+"', r"\1", text)
        if first:
            if "<w:pgNumType" in text:
                text = re.sub(r"<w:pgNumType\b", f'<w:pgNumType w:start="{first_page}"', text, count=1)
            else:
                text = re.sub(r"(<w:cols\b|<w:titlePg\b|<w:docGrid\b|</w:sectPr>)",
                              f'<w:pgNumType w:start="{first_page}"/>\\1', text, count=1)
        return text

    return re.sub(r"<w:sectPr\b.*?</w:sectPr>", section, xml, flags=re.S)


# ---------------------------------------------------------------- main

def _part_targets(archive) -> dict[str, str]:
    rels = ET.fromstring(archive.read("word/_rels/document.xml.rels"))
    return {rel.get("Id"): "word/" + rel.get("Target").lstrip("/").removeprefix("word/") for rel in rels}


def stamp(source, destination, running: RunningText, first_page: int | None = None) -> dict:
    """Write a copy of `source` with the running headers and footers filled in.

    Returns {"parts": {part name: role}, "missing": [roles without a header/footer part]}.
    """
    source, destination = Path(source), Path(destination)
    with zipfile.ZipFile(source) as archive:
        contents = {info.filename: archive.read(info.filename) for info in archive.infolist()}
        infos = archive.infolist()

    document = ET.fromstring(contents["word/document.xml"])  # read only
    targets = {}
    with zipfile.ZipFile(source) as archive:
        targets = _part_targets(archive)
    roles = {}
    for ref in document.iter():
        if ref.tag in (W + "headerReference", W + "footerReference"):
            kind = "header" if ref.tag == W + "headerReference" else "footer"
            role = {"default": "odd", "even": "even", "first": "first"}[ref.get(W + "type", "default")]
            roles.setdefault(targets[ref.get(R + "id")], f"{kind}_{role}")

    for part, role in roles.items():
        segments = _segments(getattr(running, role))
        if not segments:
            continue
        root, start_tag = _parse(contents[part])
        rels_name = part.replace("word/", "word/_rels/") + ".rels"
        if rels_name in contents:
            rels, rels_tag = _parse(contents[rels_name])
        else:
            rels, rels_tag = ET.Element(f"{{{PKG_NS}}}Relationships"), None

        def add_link(url, rels=rels):
            for rel in rels:
                if rel.get("Target") == url and rel.get("Type") == HYPERLINK_TYPE:
                    return rel.get("Id")
            ids = {rel.get("Id") for rel in rels}
            new_id = next(f"rIdStamp{n}" for n in range(1, 1000) if f"rIdStamp{n}" not in ids)
            ET.SubElement(rels, f"{{{PKG_NS}}}Relationship",
                          {"Id": new_id, "Type": HYPERLINK_TYPE, "Target": url, "TargetMode": "External"})
            return new_id

        _replace_text(root, segments, add_link)
        contents[part] = _xml(root, start_tag)
        if len(rels):
            contents[rels_name] = _xml(rels, rels_tag)

    if first_page is not None:
        xml = contents["word/document.xml"].decode("utf-8")
        contents["word/document.xml"] = _set_first_page(xml, first_page).encode("utf-8")

    # Word should recalculate fields (the PAGE numbers are cached in the file).
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(delete=False, suffix=".docx", dir=destination.parent) as handle:
        temp = Path(handle.name)
    with zipfile.ZipFile(temp, "w", zipfile.ZIP_DEFLATED) as out:
        names = [i.filename for i in infos]
        for name in names + [n for n in contents if n not in names]:
            out.writestr(name, contents[name])
    shutil.move(temp, destination)
    all_roles = {f"{k}_{r}" for k in ("header", "footer") for r in ("first", "odd", "even")}
    return {"parts": roles, "missing": sorted(all_roles - set(roles.values()))}


def _parse(raw: bytes):
    """Parse a part, keeping the file's own namespace prefixes and root tag.

    Word lists prefixes in mc:Ignorable; those must stay declared on the root element even
    when nothing in the part uses them, or Word reports the file as damaged.
    """
    text = raw.decode("utf-8")
    start = re.search(r"<(?!\?)[^>]+>", text).group(0)
    for prefix, uri in re.findall(r'xmlns:(\w+)="([^"]+)"', start):
        ET.register_namespace(prefix, uri)
    return ET.fromstring(raw), start


def _xml(root, start_tag: str | None = None) -> bytes:
    if root.tag.startswith("{" + PKG_NS + "}"):
        ET.register_namespace("", PKG_NS)  # .rels parts must use the default namespace (others register it too)
    body = ET.tostring(root, encoding="unicode")
    if start_tag:
        body = start_tag + body[re.search(r"<[^>]+>", body).end():]
    return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\r\n' + body).encode("utf-8")
