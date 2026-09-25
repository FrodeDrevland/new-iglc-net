"""The programme as a printable booklet (PDF, A5): a title page, the parts, every day's sessions
with their chairs, papers and presenters, the locations, and an index of people with their
sessions. Made with ReportLab, in the proceedings' Times New Roman when it is available
(apps/production/publish.fonts_folder), else Helvetica."""

from __future__ import annotations

import io
from collections import defaultdict
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A5
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table,
                                TableStyle)

from apps.archive.management.commands.group_authors import fold

from .models import Session


def _fonts() -> tuple[str, str, str]:
    """(regular, bold, italic) font names."""
    try:
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont

        from apps.production.publish import fonts_folder

        folder = fonts_folder()
        for name, file in (("Prog-Regular", "times.ttf"), ("Prog-Bold", "timesbd.ttf"), ("Prog-Italic", "timesi.ttf")):
            try:
                pdfmetrics.getFont(name)
            except KeyError:
                pdfmetrics.registerFont(TTFont(name, str(folder / file)))
        return "Prog-Regular", "Prog-Bold", "Prog-Italic"
    except Exception:  # noqa: BLE001 - the fonts are licensed and may be missing: fall back
        return "Helvetica", "Helvetica-Bold", "Helvetica-Oblique"


def _styles(primary):
    regular, bold, italic = _fonts()
    base = ParagraphStyle("base", fontName=regular, fontSize=8.5, leading=10.5)
    return {
        "base": base,
        "title": ParagraphStyle("title", parent=base, fontName=bold, fontSize=22, leading=26, alignment=TA_CENTER,
                                textColor=primary, spaceAfter=6 * mm),
        "subtitle": ParagraphStyle("subtitle", parent=base, fontSize=12, leading=15, alignment=TA_CENTER),
        "day": ParagraphStyle("day", parent=base, fontName=bold, fontSize=13, leading=16, textColor=primary,
                              spaceBefore=2 * mm, spaceAfter=3 * mm),
        "session": ParagraphStyle("session", parent=base, fontName=bold, fontSize=9.5, leading=11.5),
        "meta": ParagraphStyle("meta", parent=base, fontName=italic, fontSize=8, leading=10),
        "paper": ParagraphStyle("paper", parent=base, leftIndent=3 * mm, spaceBefore=1),
        "change": ParagraphStyle("change", parent=base, fontName=bold, textColor=colors.HexColor("#8a1c1c")),
        "time": ParagraphStyle("time", parent=base, fontName=bold, fontSize=9, leading=11.5),
        "h2": ParagraphStyle("h2", parent=base, fontName=bold, fontSize=12, leading=15, textColor=primary,
                             spaceBefore=3 * mm, spaceAfter=2 * mm),
        "small": ParagraphStyle("small", parent=base, fontSize=7.5, leading=9),
        "bold": bold,
    }


def _p(text, style):
    return Paragraph(escape(text or ""), style)


def _session_block(s, st, show_part: bool):
    title = f"{s.code} {s.display_title}".strip() if s.code else s.display_title
    parts = [_p(("CANCELLED: " if s.cancelled else "") + title, st["session"])]
    meta = [x for x in [s.location.name if s.location_id else "", s.part.name if show_part else "",
                        "plenary" if s.plenary else ""] if x]
    if meta:
        parts.append(_p(" · ".join(meta), st["meta"]))
    if s.change_note:
        parts.append(_p(f"Changed: {s.change_note}", st["change"]))
    people = [f"{p.get_role_display()}: {p.name}" for p in s.people.all()]
    if people:
        parts.append(_p("; ".join(people), st["base"]))
    if s.notes:
        parts.append(_p(s.notes, st["small"]))
    for n, item in enumerate(s.items.all(), 1):
        names = item.author_names()
        authors = ", ".join(f"<u>{escape(a)}</u>" if a == item.presenter else escape(a) for a in names)
        board = f"[{escape(item.board)}] " if item.board else ""
        parts.append(Paragraph(f"{n}. {board}{escape(item.display_title)}<br/><font size='7.5'>{authors}</font>",
                               st["paper"]))
    return parts


def booklet(programme, home=None) -> bytes:
    conference = programme.conference
    primary = colors.HexColor(home.primary_colour if home else "#365a91")
    st = _styles(primary)
    buffer = io.BytesIO()
    number = conference.number

    def footer(canvas, doc):
        canvas.saveState()
        canvas.setFont(st["base"].fontName, 7)
        canvas.setFillColor(colors.grey)
        canvas.drawString(12 * mm, 8 * mm, f"IGLC {number} programme")
        canvas.drawRightString(A5[0] - 12 * mm, 8 * mm, str(doc.page))
        canvas.restoreState()

    doc = SimpleDocTemplate(buffer, pagesize=A5, leftMargin=12 * mm, rightMargin=12 * mm, topMargin=12 * mm,
                            bottomMargin=15 * mm, title=f"IGLC {number} programme",
                            author="International Group for Lean Construction")
    parts = [p for p in programme.parts.all() if p.public]
    sessions = list(programme.sessions.filter(part__in=parts)
                    .select_related("location", "part", "keynote")
                    .prefetch_related("people", "items__submission__paper__authors"))
    story = [Spacer(1, 35 * mm), _p(f"IGLC {number}", st["title"]),
             _p(conference.conference_title or "Annual Conference of the International Group for Lean Construction",
                st["subtitle"]), Spacer(1, 4 * mm),
             _p(conference.location, st["subtitle"])]
    if conference.start_date:
        end = conference.end_date or conference.start_date
        from apps.conferences.templatetags.conference_tags import date_range

        story.append(_p(date_range(conference.start_date, end), st["subtitle"]))
    story.append(Spacer(1, 12 * mm))
    story.append(_p("Programme" + (" (provisional)" if programme.status == "provisional" else ""), st["subtitle"]))
    if programme.notice:
        story += [Spacer(1, 6 * mm), _p(programme.notice, st["change"])]
    story.append(PageBreak())

    show_part = len({s.part_id for s in sessions}) > 1
    if show_part:
        story.append(_p("Parts of the programme", st["h2"]))
        for part in parts:
            story.append(Paragraph(f"<b>{escape(part.name)}</b>" + (f": {escape(part.description)}"
                                                                     if part.description else ""), st["base"]))
        story.append(Spacer(1, 4 * mm))

    by_day = defaultdict(list)
    for s in sessions:
        by_day[s.date].append(s)
    for day in sorted(by_day):
        story.append(_p(f"{day:%A} {day.day} {day:%B %Y}", st["day"]))
        slots = defaultdict(list)
        for s in by_day[day]:
            slots[(s.start, s.end)].append(s)
        for (start, end), slot in sorted(slots.items()):
            cells = []
            for s in slot:
                cells += _session_block(s, st, show_part) + [Spacer(1, 2 * mm)]
            table = Table([[_p(f"{start:%H:%M}–{end:%H:%M}", st["time"]), cells]], colWidths=[20 * mm, None])
            table.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                                       ("LINEABOVE", (0, 0), (-1, 0), 0.4, colors.lightgrey),
                                       ("TOPPADDING", (0, 0), (-1, -1), 2 * mm)]))
            story.append(table if len(slot) > 1 else KeepTogether(table))
        story.append(PageBreak())

    locations = [loc for loc in programme.locations.all() if any(s.location_id == loc.pk for s in sessions)]
    if locations:
        story.append(_p("Locations", st["h2"]))
        for loc in locations:
            details = ", ".join(x for x in [loc.building, loc.address, loc.accessibility] if x)
            story.append(Paragraph(f"<b>{escape(loc.name)}</b>" + (f": {escape(details)}" if details else ""),
                                   st["base"]))
        story.append(Spacer(1, 4 * mm))

    index = defaultdict(set)
    shown = {}
    for s in sessions:
        label = s.code or f"{s.date:%a} {s.start:%H:%M}"
        names = [p.name for p in s.people.all()] + [n for i in s.items.all() for n in i.author_names()]
        for name in names:
            key = " ".join(fold(name).split())
            if key:
                shown.setdefault(key, name)
                index[key].add(label)
    if index:
        story.append(_p("People", st["h2"]))
        surname = lambda key: (key.split()[-1], key)  # noqa: E731
        for key in sorted(index, key=surname):
            story.append(_p(f"{shown[key]}: {', '.join(sorted(index[key]))}", st["small"]))

    doc.build(story, onFirstPage=lambda c, d: None, onLaterPages=footer)
    return buffer.getvalue()
