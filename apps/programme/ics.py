"""Calendar files (iCalendar, RFC 5545) of the programme: the whole programme, a part, one
session, or a visitor's own selection. Calendar apps that subscribe to the address fetch it again
now and then, so changes and cancellations reach them.

Times are written in UTC, so no time zone definitions are needed."""

from __future__ import annotations

from datetime import timezone as dt_timezone

from django.utils import timezone


def _escape(text: str) -> str:
    return (text or "").replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\r\n", "\\n") \
        .replace("\n", "\\n")


def _fold(line: str) -> str:
    """Lines longer than 75 octets continue on the next line after a space."""
    data = line.encode("utf-8")
    if len(data) <= 75:
        return line
    parts, current = [], b""
    for char in line:
        encoded = char.encode("utf-8")
        if len(current) + len(encoded) > (75 if not parts else 74):
            parts.append(current.decode("utf-8"))
            current = b""
        current += encoded
    parts.append(current.decode("utf-8"))
    return "\r\n ".join(parts)


def _utc(moment) -> str:
    return moment.astimezone(dt_timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def calendar(programme, sessions, name: str, session_url) -> str:
    """session_url(session) -> the absolute address of the session's page."""
    number = programme.conference.number
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//IGLC//Conference programme//EN", "CALSCALE:GREGORIAN",
             "METHOD:PUBLISH", f"X-WR-CALNAME:{_escape(name)}", f"X-WR-TIMEZONE:{programme.time_zone}",
             "REFRESH-INTERVAL;VALUE=DURATION:PT1H", "X-PUBLISHED-TTL:PT1H"]
    stamp = _utc(timezone.now())
    for s in sessions:
        title = f"{s.code} {s.display_title}".strip() if s.code else s.display_title
        where = ", ".join(p for p in ([s.location.name, s.location.building or s.location.address]
                                      if s.location_id else []) if p)
        details = []
        if s.change_note:
            details.append(f"Changed: {s.change_note}")
        details += [f"{p.get_role_display()}: {p.name}" for p in s.people.all()]
        details += [f"- {i.display_title}" + (f" ({i.presenter})" if i.presenter else "") for i in s.items.all()]
        if s.notes:
            details.append(s.notes)
        url = session_url(s)
        details.append(url)
        lines += ["BEGIN:VEVENT", f"UID:iglc{number}-session-{s.pk}@iglc.net", f"DTSTAMP:{stamp}",
                  f"DTSTART:{_utc(s.starts_at())}", f"DTEND:{_utc(s.ends_at())}",
                  f"SUMMARY:{_escape(('CANCELLED: ' if s.cancelled else '') + title)}",
                  f"LAST-MODIFIED:{_utc(s.updated)}", f"SEQUENCE:{int(s.updated.timestamp()) // 60 % 2147483647}",
                  f"STATUS:{'CANCELLED' if s.cancelled else 'CONFIRMED'}", f"URL:{url}"]
        if where:
            lines.append(f"LOCATION:{_escape(where)}")
        lines += [f"DESCRIPTION:{_escape(chr(10).join(details))}", f"CATEGORIES:{_escape(s.part.name)}", "END:VEVENT"]
    lines.append("END:VCALENDAR")
    return "\r\n".join(_fold(line) for line in lines) + "\r\n"
