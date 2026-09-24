"""Running headers and footers on the PDF of a paper.

The PDF comes from Word. Word marks the content of headers and footers in the PDF as
pagination artefacts (/Artifact <</Type /Pagination /Subtype /Header|/Footer>>), so they can
be removed exactly, whatever they contained. New ones are then printed in the template's
positions: Times New Roman 10 pt, header baseline 36 pt + one line below the top edge,
footer baseline near 36 pt above the bottom edge, between the paper's left and right margins.

    pages = strip_running(pdf_in)           -> PdfWriter with the pages, headers/footers removed
    add_running(writer, running, first_page, margins) ; writer.write(pdf_out)

Page parity follows the printed page number, as in Word: even pages get the even header.
"""

from __future__ import annotations

import io
import re
from dataclasses import dataclass
from pathlib import Path

from pypdf import PdfReader, PdfWriter
from pypdf.generic import ContentStream

from .stamp import RunningText, Segment, _segments

FONT_SIZE = 10
LEADING = 11.5
HEADER_BASELINE_FROM_TOP = 45.4   # measured on Word's own PDFs of IGLC 34 papers
FOOTER_BASELINE_FROM_BOTTOM = 37.9

_fonts_registered = None


@dataclass
class Margins:
    left: float = 70.9   # points; the template's 2.5 cm
    right: float = 70.9


def register_fonts(folder) -> None:
    """Times New Roman from `folder` (times.ttf, timesi.ttf, timesbd.ttf)."""
    global _fonts_registered
    if _fonts_registered == str(folder):
        return
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    folder = Path(folder)
    pdfmetrics.registerFont(TTFont("IGLC-Regular", str(folder / "times.ttf")))
    pdfmetrics.registerFont(TTFont("IGLC-Italic", str(folder / "timesi.ttf")))
    _fonts_registered = str(folder)


# ---------------------------------------------------------------- removing

def _is_running(operands) -> bool:
    if len(operands) < 2 or operands[0] != "/Artifact":
        return False
    props = operands[1]
    return hasattr(props, "get") and props.get("/Type") == "/Pagination" and \
        props.get("/Subtype") in ("/Header", "/Footer")


def strip_running(source) -> tuple[PdfWriter, int]:
    """Copy of the PDF without Word's header and footer content. Returns (writer, blocks removed)."""
    writer = PdfWriter(clone_from=PdfReader(source))
    removed = 0
    for page in writer.pages:
        content = ContentStream(page.get_contents(), writer)
        kept, skipping = [], 0
        for operands, operator in content.operations:
            if skipping:
                if operator in (b"BDC", b"BMC"):
                    skipping += 1
                elif operator == b"EMC":
                    skipping -= 1
                continue
            if operator == b"BDC" and _is_running(operands):
                skipping, removed = 1, removed + 1
                continue
            kept.append((operands, operator))
        content.operations = kept
        page.replace_contents(content)
    return writer, removed


# ---------------------------------------------------------------- checking

HEADER_ZONE = 62      # points from the top edge: Word's header area, above the text
FOOTER_ZONE = 55      # points from the bottom edge
REFERENCE_ZONE = 100  # page 1: room for a five-line reference above the title


def _multiply(a, b):
    return [a[0] * b[0] + a[1] * b[2], a[0] * b[1] + a[1] * b[3],
            a[2] * b[0] + a[3] * b[2], a[2] * b[1] + a[3] * b[3],
            a[4] * b[0] + a[5] * b[2] + b[4], a[4] * b[1] + a[5] * b[3] + b[5]]


def _text_positions(page, document=None, with_x=False):
    """(top of the letters, text) for text drawn by the page itself.

    A small interpreter of the page's content stream, so positions are exact. Text inside
    figures (form XObjects) is left out: figures are the paper's content, and their text
    would otherwise be reported at the wrong place.
    """
    found = []
    identity = [1, 0, 0, 1, 0, 0]
    ctm, stack = identity[:], []
    tm = line = identity[:]
    size, leading = 12.0, 0.0
    size_font = [""]
    content = ContentStream(page.get_contents(), document) if page.get_contents() is not None else None
    if content is None:
        return found

    def show(text):
        if text.strip():
            m = _multiply(tm, ctm)
            height = abs(size * m[3]) or size
            if with_x:
                found.append((m[4], m[5] + 0.75 * height, text.strip(), size_font[0]))
            else:
                found.append((m[5] + 0.75 * height, text.strip()))

    for operands, op in content.operations:
        if op == b"q":
            stack.append(ctm[:])
        elif op == b"Q" and stack:
            ctm = stack.pop()
        elif op == b"cm":
            ctm = _multiply([float(v) for v in operands], ctm)
        elif op == b"BT":
            tm = line = identity[:]
        elif op == b"Tf" and len(operands) == 2:
            size = float(operands[1])
            size_font[0] = str(operands[0])
        elif op == b"TL":
            leading = float(operands[0])
        elif op in (b"Td", b"TD"):
            tx, ty = float(operands[0]), float(operands[1])
            if op == b"TD":
                leading = -ty
            line = _multiply([1, 0, 0, 1, tx, ty], line)
            tm = line[:]
        elif op == b"Tm":
            line = [float(v) for v in operands]
            tm = line[:]
        elif op in (b"T*", b"'", b'"'):
            line = _multiply([1, 0, 0, 1, 0, -leading], line)
            tm = line[:]
            if op != b"T*":
                show(str(operands[-1]))
        elif op == b"Tj":
            show(str(operands[0]))
        elif op == b"TJ":
            show("".join(str(part) for part in operands[0] if not isinstance(part, (int, float))))
    return found


def layout_findings(writer: PdfWriter, removed: int) -> list[tuple[str, str]]:
    """Check a PDF whose running headers and footers have been removed (strip_running):
    nothing may be left where the new ones will be printed."""
    findings = []
    if removed == 0:
        findings.append(("pdf_not_from_word", "The PDF has no headers or footers marked by Word: "
                                              "save it from Word for Windows (or use the IGLC conversion tool)"))
    left, crowded = [], False
    for number, page in enumerate(writer.pages, 1):
        height = float(page.mediabox.height)
        for y, text in _text_positions(page, writer):
            if y > height - HEADER_ZONE or y < FOOTER_ZONE:
                left.append((number, text))
            elif number == 1 and y > height - REFERENCE_ZONE:
                crowded = True
    if left:
        pages = sorted({n for n, _ in left})
        findings.append(("pdf_running_left", "Text in the header or footer area that is not a Word header or footer "
                                             f"(page {', '.join(map(str, pages[:5]))}): “{left[0][1][:60]}”"))
    if crowded:
        findings.append(("reference_space_missing", "The title starts too high on the first page: the reference "
                                                    "needs the space above it (use the Title style of the current template)"))
    return findings


# ---------------------------------------------------------------- printing

def _words(segments: list[Segment]):
    """(piece, segment) where a line may break after each piece: after spaces (kept with the
    word before them) and, as in Word, after a hyphen or dash inside a word."""
    for segment in segments:
        for text in re.findall(r"[^ ]*?[-–](?=[^ ])|[^ ]+ *| +", re.sub(r" {2,}", " ", segment.text)):
            yield text, segment


def _font(segment: Segment) -> str:
    return "IGLC-Italic" if segment.italic else "IGLC-Regular"


# Word lets the spaces of a justified line shrink a little to fit one more word.
SPACE_SHRINK = 0.2


def _lines(segments, width):
    """Break into lines as Word does for a justified paragraph."""
    from reportlab.pdfbase.pdfmetrics import stringWidth

    lines, line, used, spaces = [], [], 0.0, 0.0
    for word, segment in _words(segments):
        font = _font(segment)
        w = stringWidth(word.rstrip(" "), font, FONT_SIZE)
        if line and used + w > width + SPACE_SHRINK * spaces:
            lines.append(line)
            line, used, spaces = [], 0.0, 0.0
        line.append((word, segment))
        used += stringWidth(word, font, FONT_SIZE)
        if word.endswith(" "):
            spaces += stringWidth(" ", font, FONT_SIZE)
    if line:
        lines.append(line)
    return lines


def _draw_line(canvas, pieces, x, y, justify_to=None):
    """Draw one line word by word; with justify_to, spread (or shrink) the spaces to that width."""
    from reportlab.pdfbase.pdfmetrics import stringWidth

    texts = [word for word, _ in pieces]
    texts[-1] = texts[-1].rstrip(" ")
    natural = sum(stringWidth(t, _font(s), FONT_SIZE) for t, (_, s) in zip(texts, pieces))
    gaps = sum(1 for t in texts[:-1] if t.endswith(" "))
    extra = (justify_to - natural) / gaps if justify_to and gaps else 0.0
    for text, (_, segment) in zip(texts, pieces):
        font = _font(segment)
        canvas.setFont(font, FONT_SIZE)
        width = stringWidth(text, font, FONT_SIZE)
        if segment.link:  # Word's Hyperlink style: blue, underlined
            canvas.setFillColorRGB(0, 0, 1)
            canvas.drawString(x, y, text)
            canvas.setStrokeColorRGB(0, 0, 1)
            canvas.setLineWidth(0.5)
            canvas.line(x, y - 1.1, x + stringWidth(text.rstrip(" "), font, FONT_SIZE), y - 1.1)
            canvas.setFillColorRGB(0, 0, 0)
            canvas.linkURL(segment.link, (x, y - 2, x + width, y + FONT_SIZE), relative=0)
        else:
            canvas.drawString(x, y, text)
        x += width + (extra if text.endswith(" ") else 0.0)


def _overlay(pages, margins) -> bytes:
    """One PDF with a page of header/footer text for every page (one embedded font subset)."""
    from reportlab.pdfbase.pdfmetrics import stringWidth
    from reportlab.pdfgen import canvas as pdfcanvas

    buffer = io.BytesIO()
    canvas = pdfcanvas.Canvas(buffer)
    for size, header, footer, number in pages:
        page_width, page_height = size
        canvas.setPageSize(size)
        left, right = margins.left, page_width - margins.right
        y = page_height - HEADER_BASELINE_FROM_TOP
        lines = _lines(header, right - left)
        for number_of_line, line in enumerate(lines):
            last = number_of_line == len(lines) - 1
            _draw_line(canvas, line, left, y, justify_to=None if last else right - left)
            y -= LEADING
        y = FOOTER_BASELINE_FROM_BOTTOM
        if footer:
            _draw_line(canvas, [(w, s) for line in _lines(footer, right - left - 40) for w, s in line], left, y)
        label = str(number)
        canvas.setFont("IGLC-Regular", FONT_SIZE)
        canvas.drawString(right - stringWidth(label, "IGLC-Regular", FONT_SIZE), y, label)
        canvas.showPage()
    canvas.save()
    return buffer.getvalue()


def add_running(writer: PdfWriter, running: RunningText, first_page: int, margins: Margins = Margins()):
    pages = []
    for index, page in enumerate(writer.pages):
        number = first_page + index
        if index == 0:
            header, footer = running.header_first, running.footer_first
        elif number % 2 == 0:
            header, footer = running.header_even, running.footer_even
        else:
            header, footer = running.header_odd, running.footer_odd
        size = (float(page.mediabox.width), float(page.mediabox.height))
        pages.append((size, _segments(header), _segments(footer), number))
    overlay = PdfReader(io.BytesIO(_overlay(pages, margins)))
    for page, layer in zip(writer.pages, overlay.pages):
        page.merge_page(layer)
    return writer
