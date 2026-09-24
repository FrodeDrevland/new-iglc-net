"""The texts of an IGLC paper's running headers and footers, from the archive's data."""

from apps.archive import citations

from .stamp import RunningText, Segment


def _date_range(start, end) -> str:
    """22–26 June 2026; 30 June – 3 July 2026; 30 December 2026 – 2 January 2027."""
    if not start:
        return ""
    if not end or end == start:
        return f"{start.day} {start:%B %Y}"
    if (start.year, start.month) == (end.year, end.month):
        return f"{start.day}–{end.day} {end:%B %Y}"
    if start.year == end.year:
        return f"{start.day} {start:%B} – {end.day} {end:%B %Y}"
    return f"{start.day} {start:%B %Y} – {end.day} {end:%B %Y}"


def conference_line(conference) -> str:
    place = conference.city if conference.city == conference.country else ", ".join(
        filter(None, [conference.city, conference.country]))
    return ", ".join(filter(None, [f"Proceedings IGLC{conference.number}",
                                   _date_range(conference.start_date, conference.end_date), place]))


def author_names(paper) -> str:
    names = [f"{a.first_name} {a.last_name}".strip() for a in paper.authors.all()]
    if len(names) <= 1:
        return "".join(names)
    if len(names) == 2:
        return " & ".join(names)
    return ", ".join(names[:-1]) + ", & " + names[-1]


def running_text(paper, track: str = "") -> RunningText:
    track = track or (paper.track.title if getattr(paper, "track", None) else "")
    reference = citations.apa7(paper)
    reference_segments = [Segment(reference["before"] + " "), Segment(reference["italic"], italic=True),
                          Segment(reference["after"] + " ")]
    if reference["doi_url"]:
        reference_segments.append(Segment(reference["doi_url"], link=reference["doi_url"]))
    return RunningText(
        header_first=reference_segments,
        header_odd=author_names(paper),
        header_even=paper.title,
        footer_first=track,
        footer_odd=track,
        footer_even=conference_line(paper.conference),
    )
