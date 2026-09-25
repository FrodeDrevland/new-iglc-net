"""Crossref deposit XML for a conference's proceedings (schema 5.3.1).

One deposit holds the whole conference: the series (ISSN), the proceedings (DOI 10.24928/<year>,
pointing to the conference page) and every paper (DOI 10.24928/<year>/<number>, pointing to the
paper's page). Depositing again updates the records, so a deposit can simply be repeated after a
correction or when the full proceedings get their ISBN.

Based on the old site's Helpers/CrossrefXmlCreator.cs (schema 4.4.0), extended with
affiliations, ORCID iDs and abstracts.
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from xml.etree import ElementTree as ET

from django.conf import settings

SCHEMA = "5.3.1"
NS = f"http://www.crossref.org/schema/{SCHEMA}"
JATS = "http://www.ncbi.nlm.nih.gov/JATS1"
XSI = "http://www.w3.org/2001/XMLSchema-instance"
ET.register_namespace("", NS)
ET.register_namespace("jats", JATS)
ET.register_namespace("xsi", XSI)

SERIES_TITLE = "Annual Conference of the International Group for Lean Construction"
PUBLISHER = "International Group for Lean Construction"
ORCID = re.compile(r"(\d{4}-\d{4}-\d{4}-\d{3}[\dX])")


def _e(parent, tag, text=None, **attrs):
    element = ET.SubElement(parent, f"{{{NS}}}{tag}", {k: str(v) for k, v in attrs.items() if v not in (None, "")})
    if text not in (None, ""):
        element.text = str(text)
    return element


def _date(parent, day, media_type="online"):
    date = _e(parent, "publication_date", media_type=media_type)
    _e(date, "month", f"{day.month:02d}")
    _e(date, "day", f"{day.day:02d}")
    _e(date, "year", day.year)
    return date


def site_url(path: str) -> str:
    return getattr(settings, "CROSSREF_SITE_URL", settings.SITE_URL).rstrip("/") + path


# The first part of an IGLC affiliation is often the person's position, not the institution.
POSITION = re.compile(
    r"\b(student|candidate|professor|prof\.|lecturer|researcher|scientist|research(er)? fellow|fellow|postdoc|"
    r"post-doctoral|doctoral|phd|ph\.d|msc|m\.sc|engineer|manager|director|advisor|adviser|consultant|associate|"
    r"assistant|adjunct|ceo|cto|founder|partner|head|chair|president|dean|coordinator|specialist|architect|"
    r"analyst|lead|principal|officer|vp|senior|junior|master|graduate|undergraduate|intern|dr\.)\b", re.I)
INSTITUTION = re.compile(r"univers|institut|college|school|academy|hochschule|polytechni|ntnu|technion|ltd|inc\b|"
                         r"gmbh|\bas\b|company|corporation|group|council|agency|administration|centre|center", re.I)


def institutions(text: str) -> list[str]:
    """The institutions in an affiliation text: several when joined with '/' or ';', each
    without a leading position ('Professor, Dept. X, University Y, City, Country' ->
    'Dept. X, University Y, City, Country')."""
    found = []
    for part in re.split(r"\s*/\s*(?=[A-Z])|\s*;\s*", text or ""):
        pieces = [p.strip() for p in part.split(",") if p.strip()]
        while len(pieces) > 1 and POSITION.search(pieces[0]) and not INSTITUTION.search(pieces[0]):
            pieces = pieces[1:]
        if pieces:
            found.append(", ".join(pieces)[:1024])
    return found


def _affiliation_and_orcid(author) -> tuple[list[str], str]:
    from apps.production.docx_reader import parse_affiliation

    orcid = ORCID.search(author.title_and_contact or "") or ORCID.search(getattr(author.person, "orcid", "") or "")
    affiliation = parse_affiliation(author.title_and_contact or "")["affiliation"]
    return institutions(affiliation), (f"https://orcid.org/{orcid.group(1)}" if orcid else "")


def orcid_issues(paper) -> dict[int, str]:
    """Authors (by pk) whose ORCID iD Crossref would reject: a wrong check digit, or the same iD on
    two authors of the paper. Those iDs are left out of the deposit (the rest of the record goes)."""
    from apps.production.docx_reader import orcid_checksum_ok

    found, seen = {}, {}
    for author in paper.authors.select_related("person").all():
        _, orcid = _affiliation_and_orcid(author)
        if not orcid:
            continue
        number = orcid.rsplit("/", 1)[-1]
        name = f"{author.first_name} {author.last_name}".strip()
        if not orcid_checksum_ok(number):
            found[author.pk] = f"{name}: ORCID {number} is not valid (wrong check digit)"
        elif number in seen:
            first_pk, first_name = seen[number]
            found[first_pk] = f"{first_name}: ORCID {number} is also given for {name}"
            found[author.pk] = f"{name}: ORCID {number} is also given for {first_name}"
        else:
            seen[number] = (author.pk, name)
    return found


def _contributors(parent, paper):
    authors = list(paper.authors.select_related("person").all())
    if not authors:
        return
    rejected = orcid_issues(paper)
    contributors = _e(parent, "contributors")
    for index, author in enumerate(authors):
        person = _e(contributors, "person_name", sequence="first" if index == 0 else "additional",
                    contributor_role="author")
        if author.first_name:
            _e(person, "given_name", author.first_name)
        _e(person, "surname", author.last_name or author.first_name)
        names, orcid = _affiliation_and_orcid(author)
        if names:
            affiliations = _e(person, "affiliations")
            for name in names:
                _e(_e(affiliations, "institution"), "institution_name", name)
        if orcid and author.pk not in rejected:
            _e(person, "ORCID", orcid)


def _abstract(parent, text: str):
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n|\r\n\r\n", text or "") if p.strip()]
    if not paragraphs:
        return
    abstract = ET.SubElement(parent, f"{{{JATS}}}abstract")
    for paragraph in paragraphs:
        ET.SubElement(abstract, f"{{{JATS}}}p").text = re.sub(r"\s+", " ", paragraph)


def conference_xml(conference, papers, isbn: str = "", depositor: tuple[str, str] | None = None) -> tuple[str, bytes]:
    """(doi_batch_id, XML) for the conference and the given papers."""
    if not conference.start_date:
        raise ValueError(f"{conference} has no start date")
    batch_id = f"iglc{conference.number}-{uuid.uuid4().hex[:12]}"
    name, email = depositor or (settings.CROSSREF_DEPOSITOR_NAME, settings.CROSSREF_DEPOSITOR_EMAIL)
    root = ET.Element(f"{{{NS}}}doi_batch", {
        "version": SCHEMA,
        f"{{{XSI}}}schemaLocation": f"{NS} https://www.crossref.org/schemas/crossref{SCHEMA}.xsd"})
    head = _e(root, "head")
    _e(head, "doi_batch_id", batch_id)
    _e(head, "timestamp", datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")[:17])
    depositor_element = _e(head, "depositor")
    _e(depositor_element, "depositor_name", name)
    _e(depositor_element, "email_address", email)
    _e(head, "registrant", settings.CROSSREF_REGISTRANT)

    event = _e(_e(root, "body"), "conference")
    metadata = _e(event, "event_metadata")
    start, end = conference.start_date, conference.end_date or conference.start_date
    _e(metadata, "conference_name", conference.conference_title
       or f"{_ordinal(conference.number)} Annual Conference of the International Group for Lean Construction")
    _e(metadata, "conference_acronym", f"IGLC{conference.number}")
    _e(metadata, "conference_number", conference.number)
    place = ", ".join(dict.fromkeys(filter(None, [conference.city, conference.country])))
    if place:
        _e(metadata, "conference_location", place)
    _e(metadata, "conference_date", f"{start:%d %b %Y} - {end:%d %b %Y}", start_day=start.day,
       start_month=f"{start.month:02d}", start_year=start.year, end_day=end.day, end_month=f"{end.month:02d}",
       end_year=end.year)

    proceedings = _e(event, "proceedings_series_metadata")
    series = _e(proceedings, "series_metadata")
    _e(_e(series, "titles"), "title", SERIES_TITLE)
    # The series' ISSNs: 2309-0979 (print) and, used in recent years, 2789-0015 (electronic)
    _e(series, "issn", settings.CROSSREF_ISSN_PRINT, media_type="print")
    if (conference.issn or "").strip() == settings.CROSSREF_ISSN_ELECTRONIC:
        _e(series, "issn", settings.CROSSREF_ISSN_ELECTRONIC, media_type="electronic")
    _e(proceedings, "proceedings_title", conference.proceedings_title
       or f"Proceedings of the {_ordinal(conference.number)} Annual Conference of the International Group for "
          f"Lean Construction (IGLC{conference.number})")
    _e(proceedings, "proceedings_subject", "Lean Construction")
    _e(_e(proceedings, "publisher"), "publisher_name", conference.publisher or PUBLISHER)
    _date(proceedings, start)
    if isbn:
        _e(proceedings, "isbn", isbn, media_type="electronic")
    else:
        _e(proceedings, "noisbn", reason="archive_volume")
    doi_data = _e(proceedings, "doi_data")
    _e(doi_data, "doi", f"{settings.DOI_PREFIX}/{start.year}")
    _e(doi_data, "resource", site_url(conference.get_absolute_url()))

    for paper in papers:
        if not paper.doi:
            continue
        element = _e(event, "conference_paper", publication_type="full_text")
        _contributors(element, paper)
        _e(_e(element, "titles"), "title", paper.title)
        _abstract(element, paper.abstract)
        _date(element, start)
        if paper.first_page and paper.last_page:
            pages = _e(element, "pages")
            _e(pages, "first_page", paper.first_page)
            _e(pages, "last_page", paper.last_page)
        doi_data = _e(element, "doi_data")
        _e(doi_data, "doi", paper.doi)
        _e(doi_data, "resource", site_url(paper.get_absolute_url()))
    ET.indent(root)
    # Other modules register namespace prefixes globally too: set ours just before writing.
    ET.register_namespace("", NS)
    ET.register_namespace("jats", JATS)
    ET.register_namespace("xsi", XSI)
    return batch_id, ET.tostring(root, encoding="utf-8", xml_declaration=True)


def _ordinal(n: int) -> str:
    suffix = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"
