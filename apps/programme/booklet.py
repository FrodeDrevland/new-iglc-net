"""The programme as a printable booklet (PDF, A4 landscape), laid out like the IGLC 34 booklet: a
title page, the parts, and every day as a table with the time on the left. Sessions side by side
get a column each: a heading row with the session's code, title, room and chairs, then a row for
each paper (title and authors, the presenter underlined). Plenary sessions and breaks take the
whole width. Then the rooms, and an index of people with their sessions. Made with ReportLab, in
the proceedings' Times New Roman when it is available (apps/production/publish.fonts_folder),
else Helvetica."""

from __future__ import annotations

import io
from collections import defaultdict
from math import lcm
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (BaseDocTemplate, Frame, NextPageTemplate, PageBreak, PageTemplate, Paragraph,
                                Spacer, Table, TableStyle)

from apps.archive.management.commands.group_authors import fold

from . import lanes as lane_rules

PAGE = landscape(A4)
MARGIN = 12 * mm
TIME_WIDTH = 24 * mm


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
    centred = ParagraphStyle("centred", parent=base, alignment=TA_CENTER)
    return {
        "base": base,
        "title": ParagraphStyle("title", parent=base, fontName=bold, fontSize=30, leading=36, alignment=TA_CENTER,
                                textColor=primary, spaceAfter=6 * mm),
        "subtitle": ParagraphStyle("subtitle", parent=base, fontSize=14, leading=18, alignment=TA_CENTER),
        "day": ParagraphStyle("day", parent=base, fontName=bold, fontSize=15, leading=18, textColor=primary,
                              spaceAfter=1 * mm),
        "dayparts": ParagraphStyle("dayparts", parent=base, fontName=italic, fontSize=9, spaceAfter=3 * mm),
        "head": ParagraphStyle("head", parent=centred, fontName=bold, fontSize=9, leading=11),
        "time": ParagraphStyle("time", parent=centred, fontSize=8.5, leading=10.5),
        "session": ParagraphStyle("session", parent=centred, fontSize=8, leading=9.8),
        "plenary": ParagraphStyle("plenary", parent=centred, fontSize=9.5, leading=12),
        "paper": ParagraphStyle("paper", parent=centred, fontName=bold, fontSize=7.5, leading=9, textColor=primary),
        "authors": ParagraphStyle("authors", parent=centred, fontSize=6.5, leading=8, spaceBefore=3),
        "change": ParagraphStyle("change", parent=centred, fontName=bold, fontSize=7.5, leading=9,
                                 textColor=colors.HexColor("#8a1c1c")),
        "notice": ParagraphStyle("notice", parent=base, fontName=bold, alignment=TA_CENTER,
                                 textColor=colors.HexColor("#8a1c1c")),
        "h2": ParagraphStyle("h2", parent=base, fontName=bold, fontSize=13, leading=16, textColor=primary,
                             spaceBefore=3 * mm, spaceAfter=2 * mm),
        "small": ParagraphStyle("small", parent=base, fontSize=7.5, leading=9),
        "bold": bold,
    }


def _p(text, style):
    return Paragraph(escape(text or ""), style)


def _tint(colour, amount):
    """The colour mixed with white: amount 0 is white, 1 the colour."""
    return colors.Color(*(1 - amount * (1 - c) for c in (colour.red, colour.green, colour.blue)))


def _hm(start, end):
    return f"{start:%H:%M} – {end:%H:%M}"


def _people(session) -> list[str]:
    """"Chair: Cy Lee", "Panellists: A, B" ..., in the order the roles were given."""
    by_role = {}
    for person in session.people.all():
        by_role.setdefault(person.get_role_display(), []).append(person.name)
    return [f"{role}{'s' if len(names) > 1 else ''}: {', '.join(names)}" for role, names in by_role.items()]


def _session_head(s, st, time_differs: bool) -> str:
    """The heading of a session: code and title, room, chairs, changes."""
    title = f"{s.code}: {s.display_title}" if s.code else s.display_title
    lines = [f"<b>{'CANCELLED: ' if s.cancelled else ''}{escape(title)}</b>"]
    if s.location_id:
        lines.append(f"({escape(s.location.name)})")
    if time_differs:
        lines.append(escape(_hm(s.start, s.end)))
    lines += [f"<font size='7'><b>{escape(line)}</b></font>" for line in _people(s)]
    if s.change_note:
        lines.append(f"<font color='#8a1c1c'><b>Changed: {escape(s.change_note)}</b></font>")
    return "<br/>".join(lines)


def _item(item, st) -> list:
    names = item.author_names()
    authors = ", ".join(f"<u>{escape(a)}</u>" if a == item.presenter else escape(a) for a in names)
    board = f"[{escape(item.board)}] " if item.board else ""
    cell = [Paragraph(board + escape(item.display_title), st["paper"])]
    if authors:
        cell.append(Paragraph(authors, st["authors"]))
    return cell


def _clusters(sessions) -> list[list]:
    """The day's sessions in groups that run at the same time (overlapping, directly or through others)."""
    groups, end = [], None
    for s in sorted(sessions, key=lambda s: (s.start, s.end)):
        if groups and s.start < end:
            groups[-1].append(s)
            end = max(end, s.end)
        else:
            groups.append([s])
            end = s.end
    return groups


def _in_columns(group) -> bool:
    """Whether a group is drawn as columns with a row per paper (sessions side by side, or one
    session of papers), rather than as one row across the page (a plenary session, a break)."""
    if len(group) > 1:
        return True
    s = group[0]
    return s.kind in s.WITH_PAPERS and not lane_rules.spans(s) and s.items.exists()


def _day_table(sessions, st, primary, width) -> Table:
    groups = _clusters(sessions)
    widths = [len(g) if _in_columns(g) else 1 for g in groups]
    sub = lcm(*widths) if widths else 1
    sub_width = (width - TIME_WIDTH) / sub
    rows = [[_p("Time", st["head"]), _p("Programme", st["head"])] + [""] * (sub - 1)]
    style = [("SPAN", (1, 0), (-1, 0)), ("LINEBELOW", (0, 0), (-1, 0), 0.8, primary),
             ("LINEABOVE", (0, 0), (-1, 0), 0.8, primary)]
    grid = colors.HexColor("#9fb0c8")
    header_tint, break_tint = _tint(primary, 0.16), colors.HexColor("#f2f2f2")
    for group in groups:
        start, end = min(s.start for s in group), max(s.end for s in group)
        r = len(rows)
        if not _in_columns(group):
            s = group[0]
            cell = [Paragraph(_session_head(s, st, False), st["plenary"])]
            if s.notes:
                cell.append(_p(s.notes, st["session"]))
            for item in s.items.all():
                cell += _item(item, st)
            rows.append([_p(_hm(start, end), st["time"]), cell] + [""] * (sub - 1))
            style += [("SPAN", (1, r), (-1, r)), ("LINEBELOW", (0, r), (-1, r), 0.5, grid)]
            if s.kind in ("break", "meal"):
                style.append(("BACKGROUND", (1, r), (-1, r), break_tint))
            continue
        ordered = sorted(group, key=lambda s: (s.lane or 99, s.location.name if s.location_id else "", s.pk))
        span = sub // len(ordered)
        head = [_p(_hm(start, end), st["time"])]
        for s in ordered:
            differs = (s.start, s.end) != (start, end)
            head += [Paragraph(_session_head(s, st, differs), st["session"])] + [""] * (span - 1)
        rows.append(head)
        style += [("BACKGROUND", (1, r), (-1, r), header_tint), ("LINEBELOW", (0, r), (-1, r), 0.5, grid)]
        items = [list(s.items.all()) for s in ordered]
        count = max((len(x) for x in items), default=0)
        for n in range(count):
            row = [""]
            for each in items:
                row += [_item(each[n], st) if n < len(each) else ""] + [""] * (span - 1)
            rows.append(row)
            style.append(("LINEBELOW", (0, len(rows) - 1), (-1, len(rows) - 1), 0.5, grid))
        for row in range(r, len(rows)):
            for column, _ in enumerate(ordered):
                first = 1 + column * span
                style.append(("SPAN", (first, row), (first + span - 1, row)))
                if column:
                    style.append(("LINEBEFORE", (first, row), (first, row), 0.5, grid))
        if count:
            style.append(("NOSPLIT", (0, r), (-1, r + 1)))  # a heading stays with its first paper
    style += [("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("LINEAFTER", (0, 0), (0, -1), 0.8, primary),
              ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
              ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 4)]
    table = Table(rows, colWidths=[TIME_WIDTH] + [sub_width] * sub, repeatRows=1)
    table.setStyle(TableStyle(style))
    return table


def booklet(programme, home=None) -> bytes:
    conference = programme.conference
    primary = colors.HexColor(home.primary_colour if home else "#365a91")
    st = _styles(primary)
    buffer = io.BytesIO()
    number = conference.number
    dates = ""
    if conference.start_date:
        from apps.conferences.templatetags.conference_tags import date_range

        dates = date_range(conference.start_date, conference.end_date or conference.start_date)
    band = " | ".join(x for x in [f"IGLC {number}", conference.location, dates] if x)

    def footer(canvas, doc):
        canvas.saveState()
        canvas.setFillColor(primary)
        canvas.rect(0, 0, PAGE[0], 9 * mm, stroke=0, fill=1)
        canvas.setFillColor(colors.white)
        canvas.setFont(st["bold"], 8.5)
        canvas.drawString(MARGIN, 3.3 * mm, band)
        canvas.drawRightString(PAGE[0] - MARGIN, 3.3 * mm, f"Page {doc.page}")
        canvas.restoreState()

    doc = BaseDocTemplate(buffer, pagesize=PAGE, leftMargin=MARGIN, rightMargin=MARGIN, topMargin=MARGIN,
                          bottomMargin=14 * mm, title=f"IGLC {number} programme",
                          author="International Group for Lean Construction")
    width, height = doc.width, doc.height
    gap = 6 * mm
    third = (width - 2 * gap) / 3
    doc.addPageTemplates([
        PageTemplate("cover", [Frame(MARGIN, doc.bottomMargin, width, height, id="cover")]),
        PageTemplate("page", [Frame(MARGIN, doc.bottomMargin, width, height, id="page")], onPage=footer),
        PageTemplate("columns", [Frame(MARGIN + n * (third + gap), doc.bottomMargin, third, height, id=f"c{n}")
                                 for n in range(3)], onPage=footer),
    ])
    parts = [p for p in programme.parts.all() if p.public]
    sessions = list(programme.sessions.filter(part__in=parts)
                    .select_related("location", "part", "keynote")
                    .prefetch_related("people", "items__submission__paper__authors", "items__contribution"))
    story = [NextPageTemplate("page"), Spacer(1, 45 * mm), _p(f"IGLC {number}", st["title"]),
             _p(conference.conference_title or "Annual Conference of the International Group for Lean Construction",
                st["subtitle"]), Spacer(1, 4 * mm), _p(conference.location, st["subtitle"])]
    if dates:
        story.append(_p(dates, st["subtitle"]))
    story.append(Spacer(1, 12 * mm))
    story.append(_p("Programme" + (" (provisional)" if programme.status == "provisional" else ""), st["subtitle"]))
    if programme.notice:
        story += [Spacer(1, 6 * mm), _p(programme.notice, st["notice"])]
    story.append(PageBreak())

    several = len({s.part_id for s in sessions}) > 1
    if several:
        story.append(_p("Parts of the programme", st["h2"]))
        for part in parts:
            story.append(Paragraph(f"<b>{escape(part.name)}</b>" + (f": {escape(part.description)}"
                                                                     if part.description else ""), st["base"]))
        story.append(PageBreak())

    by_day = defaultdict(list)
    for s in sessions:
        by_day[s.date].append(s)
    for day in sorted(by_day):
        story.append(_p(f"{day:%A} {day.day} {day:%B %Y}", st["day"]))
        day_parts = sorted({s.part for s in by_day[day]}, key=lambda part: (part.sort_order, part.pk))
        story.append(_p(" and ".join(p.name for p in day_parts) if several else "", st["dayparts"]))
        story.append(_day_table(by_day[day], st, primary, width))
        story.append(PageBreak())

    locations = [loc for loc in programme.locations.all() if any(s.location_id == loc.pk for s in sessions)]
    if locations:
        story.append(_p("Rooms", st["h2"]))
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
        story += [NextPageTemplate("columns"), PageBreak(), _p("People", st["h2"])]
        surname = lambda key: (key.split()[-1], key)  # noqa: E731
        for key in sorted(index, key=surname):
            story.append(_p(f"{shown[key]}: {', '.join(sorted(index[key]))}", st["small"]))

    doc.build(story)
    return buffer.getvalue()
