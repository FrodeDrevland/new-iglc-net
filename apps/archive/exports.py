"""BibTeX and RIS exports of papers."""

import re
from datetime import datetime, timezone


def _people(people):
    return [f"{p.last_name}, {p.first_name}".strip(", ") for p in people]


def _bibtex_value(value) -> str:
    return str(value).replace("{", "(").replace("}", ")").replace("\r", " ").replace("\n", " ")


def bibtex_entry(paper, site_url: str) -> str:
    conference = paper.conference
    authors = list(paper.authors.all())
    first_author = authors[0].last_name if authors else "IGLC"
    key = re.sub(r"[^A-Za-z0-9]", "", f"{first_author}{paper.year or ''}") + f"_{paper.pk}"
    pages = f"{paper.first_page}--{paper.last_page}" if paper.first_page and paper.last_page else ""
    fields = [
        ("author", " and ".join(_people(authors))),
        ("editor", " and ".join(_people(conference.editors.all()))),
        ("title", paper.title),
        ("booktitle", conference.proceedings_title),
        ("year", paper.year),
        ("pages", pages),
        ("address", conference.location),
        ("publisher", conference.publisher),
        ("isbn", paper.volume.isbn if paper.volume else ""),
        ("issn", conference.issn),
        ("doi", paper.doi),
        ("url", f"{site_url}{paper.get_absolute_url()}"),
        ("abstract", paper.abstract),
        ("keywords", paper.keywords),
    ]
    lines = [f"@inproceedings{{{key},"]
    lines += [f"  {name} = {{{_bibtex_value(value)}}}," for name, value in fields if value]
    lines.append("}")
    return "\n".join(lines)


def _ris_line(tag: str, value="") -> str:
    value = str(value).replace("\r", " ").replace("\n", " ")
    return f"{tag}  - {value}".rstrip() if tag == "ER" else f"{tag}  - {value}"


def ris_entry(paper, site_url: str) -> str:
    conference = paper.conference
    lines = [_ris_line("TY", "CONF"), _ris_line("TI", paper.title)]
    lines += [_ris_line("AU", name) for name in _people(paper.authors.all())]
    lines += [_ris_line("AD", a.title_and_contact) for a in paper.authors.all() if a.title_and_contact]
    lines += [_ris_line("ED", name) for name in _people(conference.editors.all())]
    if paper.year:
        lines.append(_ris_line("PY", paper.year))
    if conference.start_date:
        lines.append(_ris_line("DA", conference.start_date.strftime("%Y/%m/%d")))
    if conference.proceedings_title:
        lines += [_ris_line("T2", conference.proceedings_title), _ris_line("C3", conference.proceedings_title)]
    if conference.location:
        lines.append(_ris_line("CY", conference.location))
    if paper.first_page and paper.last_page:
        lines += [_ris_line("SP", paper.first_page), _ris_line("EP", paper.last_page)]
    if paper.doi:
        lines.append(_ris_line("DO", paper.doi))
    if paper.volume and paper.volume.isbn:
        lines.append(_ris_line("SN", f"{paper.volume.isbn} (ISBN)"))
    if conference.issn:
        lines.append(_ris_line("SN", f"{conference.issn} (ISSN)"))
    if paper.abstract:
        lines.append(_ris_line("AB", paper.abstract))
    for keyword in (k.strip() for k in paper.keywords.split(",")):
        if keyword:
            lines.append(_ris_line("KW", keyword))
    if conference.publisher:
        lines.append(_ris_line("PB", conference.publisher))
    url = f"{site_url}{paper.get_absolute_url()}"
    lines += [
        _ris_line("L1", f"{url}/pdf"),
        _ris_line("UR", url),
        _ris_line("DB", "IGLC.net"),
        _ris_line("LA", "English"),
        _ris_line("N1", f"Export date: {datetime.now(timezone.utc):%d %B %Y}"),
        _ris_line("ER"),
    ]
    return "\n".join(lines)


def bibtex(papers, site_url: str) -> str:
    return "\n\n".join(bibtex_entry(paper, site_url) for paper in papers) + "\n"


def ris(papers, site_url: str) -> str:
    return "\n\n".join(ris_entry(paper, site_url) for paper in papers) + "\n"
