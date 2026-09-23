"""Turn the old iglc.net database (a .bacpac export) into rows for the new archive models.

Pure Python, no Django, so it can be checked on its own:
    python -m apps.archive.legacy_import path/to/export.bacpac
The management command `import_legacy` writes the result to the database.

Kept: conferences, volumes, editors, tracks, author persons, papers, authors, link categories, links,
all with their old IDs. Not imported: user accounts (new accounts are created instead) and the two
old CMS pages (recreated in Wagtail).
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone

try:
    from .bacpac import Bacpac
except ImportError:  # run as a plain script
    from bacpac import Bacpac


@dataclass
class ImportData:
    conferences: list[dict] = field(default_factory=list)
    volumes: list[dict] = field(default_factory=list)
    editors: list[dict] = field(default_factory=list)
    tracks: list[dict] = field(default_factory=list)
    persons: list[dict] = field(default_factory=list)
    papers: list[dict] = field(default_factory=list)
    authors: list[dict] = field(default_factory=list)
    link_categories: list[dict] = field(default_factory=list)
    links: list[dict] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    source_counts: dict[str, int] = field(default_factory=dict)


def text(value) -> str:
    return (value or "").strip()


def aware(value):
    return value.replace(tzinfo=timezone.utc) if isinstance(value, datetime) else None


def clean_doi(value) -> str:
    """'https://doi.org/10.24928/2019/0123' -> '10.24928/2019/0123'.

    Only URL and 'doi:' prefixes are removed. Anything else is kept exactly, because the DOI
    must match what is registered: three DOIs from 2019 are registered with a trailing full stop.
    """
    doi = text(value)
    doi = re.sub(r"^(https?://)?(dx\.)?(doi\.org/)?", "", doi, flags=re.IGNORECASE)
    return re.sub(r"^doi:\s*", "", doi, flags=re.IGNORECASE)


def load(path) -> ImportData:
    export = Bacpac(path)
    rows = {name: list(export.rows(f"dbo.{name}")) for name in (
        "Conferences", "Volumes", "Editors", "ConferenceTracks", "AuthorPersons",
        "Papers", "Authors", "LinkCategories", "Links",
    )}
    data = ImportData(source_counts={name: len(r) for name, r in rows.items()})

    for c in rows["Conferences"]:
        data.conferences.append({
            "pk": c["ConferenceID"], "number": c["ConferenceNumber"],
            "start_date": c["StartDate"].date() if c["StartDate"] else None,
            "end_date": c["EndDate"].date() if c["EndDate"] else None,
            "city": text(c["City"]), "country": text(c["Country"]),
            "conference_title": text(c["ConferenceTitle"]), "proceedings_title": text(c["ProceedingsTitle"]),
            "publisher": text(c["Publisher"]), "publication_location": text(c["PublicationLocation"]),
            "issn": text(c["ISSN"]), "is_published": c["IsPublishedOnWebsite"],
            "last_edited_at": aware(c["LastEdit"]),
        })

    for v in rows["Volumes"]:
        data.volumes.append({
            "pk": v["VolumeID"], "conference_id": v["ConferenceID"], "number": v["VolumeNumber"],
            "first_page": v["FirstPage"], "last_page": v["LastPage"], "isbn": text(v["ISBN"]),
            "last_edited_at": aware(v["LastEdit"]),
        })

    for e in rows["Editors"]:
        if e["ConferenceID"] is None:
            data.notes.append(f"Editor {e['EditorID']} skipped: no conference")
            continue
        data.editors.append({
            "pk": e["EditorID"], "conference_id": e["ConferenceID"], "first_name": text(e["FirstName"]),
            "last_name": text(e["LastName"]), "title_and_contact": text(e["TitleAndContact"]),
            "order": e["EditorNumber"],
        })

    for t in rows["ConferenceTracks"]:
        if t["ConferenceID"] is None:
            data.notes.append(f"Track {t['ConferenceTrackID']} skipped: no conference")
            continue
        data.tracks.append({
            "pk": t["ConferenceTrackID"], "conference_id": t["ConferenceID"],
            "title": text(t["TrackTitle"]), "description": text(t["TrackDescription"]),
        })

    for p in rows["AuthorPersons"]:
        data.persons.append({
            "pk": p["AuthorPersonID"], "orcid": text(p["Orcid"]),
            "first_name": text(p["FirstName"]), "last_name": text(p["LastName"]),
        })

    track_ids = {t["pk"] for t in data.tracks}
    for p in rows["Papers"]:
        doi = clean_doi(p["DOI"])
        if doi != text(p["DOI"]):
            data.notes.append(f"Paper {p['PaperID']}: DOI {text(p['DOI'])!r} cleaned to {doi!r}")
        if doi.endswith("."):
            data.notes.append(f"Paper {p['PaperID']}: DOI {doi!r} ends with a full stop (registered that way)")
        first, last = p["FirstPage"], p["LastPage"]
        if first and last and first > last:
            data.notes.append(f"Paper {p['PaperID']}: first page {first} after last page {last} (kept as is)")
        if not text(p["FullTextUrl"]):
            data.notes.append(f"Paper {p['PaperID']}: no full-text URL")
        data.papers.append({
            "pk": p["PaperID"], "conference_id": p["ConferenceID"], "volume_id": p["VolumeID"],
            "track_id": p["ConferenceTrackID"] if p["ConferenceTrackID"] in track_ids else None,
            "title": text(p["Title"]), "abstract": text(p["Abstract"]), "keywords": text(p["Keywords"]),
            "first_page": first, "last_page": last, "doi": doi,
            "full_text_url": text(p["FullTextUrl"]), "a3_url": text(p["A3Url"]),
            "presentation_url": text(p["PresentationUrl"]), "status": p["PaperStatus"],
            "last_edited_at": aware(p["LastEdit"]),
        })

    paper_ids = {p["pk"] for p in data.papers}
    person_ids = {p["pk"] for p in data.persons}
    for a in rows["Authors"]:
        if a["PaperID"] not in paper_ids:
            data.notes.append(f"Author {a['AuthorID']} skipped: not linked to a paper")
            continue
        data.authors.append({
            "pk": a["AuthorID"], "paper_id": a["PaperID"],
            "person_id": a["AuthorPersonId"] if a["AuthorPersonId"] in person_ids else None,
            "first_name": text(a["FirstName"]), "last_name": text(a["LastName"]),
            "title_and_contact": text(a["TitleAndContact"]), "order": a["AuthorNumber"],
        })

    renumber(data.authors, "paper_id", "Author", data.notes)
    renumber(data.editors, "conference_id", "Editor", data.notes)

    for c in rows["LinkCategories"]:
        data.link_categories.append({
            "pk": c["LinkCategoryID"], "name": text(c["Name"]), "description": text(c["Description"]),
            "sort_order": c["SortOrder"],
        })
    for link in rows["Links"]:
        data.links.append({
            "pk": link["LinkID"], "category_id": link["LinkCategoryID"], "name": text(link["Name"]),
            "url": text(link["Url"]), "description": text(link["Description"]), "sort_order": link["SortOrder"],
        })
    return data


def renumber(rows: list[dict], parent_key: str, label: str, notes: list[str]) -> None:
    """Number authors (or editors) 1, 2, 3 ... within each paper (or conference), in their old order.

    The old data has missing and negative numbers (one author numbered -1 before 2 and 3);
    rows without a number keep their place after the numbered ones, in ID order.
    """
    groups: dict[int, list[dict]] = {}
    for row in rows:
        groups.setdefault(row[parent_key], []).append(row)
    changed = 0
    for group in groups.values():
        group.sort(key=lambda r: (r["order"] is None, r["order"] or 0, r["pk"]))
        for position, row in enumerate(group, 1):
            if row["order"] is not None and row["order"] < 1:
                notes.append(f"{label} {row['pk']}: number {row['order']} changed to {position}")
            changed += row["order"] != position
            row["order"] = position
    if changed:
        notes.append(f"{label}s renumbered 1, 2, 3 ... per {parent_key.removesuffix('_id')}: {changed} numbers changed")


def summary(data: ImportData) -> str:
    lines = ["Source rows: " + ", ".join(f"{k} {v}" for k, v in data.source_counts.items())]
    lines.append(
        f"To import: {len(data.conferences)} conferences, {len(data.volumes)} volumes, {len(data.editors)} editors, "
        f"{len(data.tracks)} tracks, {len(data.persons)} author persons, {len(data.papers)} papers, "
        f"{len(data.authors)} authors, {len(data.link_categories)} link categories, {len(data.links)} links"
    )
    lines += [f"  - {note}" for note in data.notes]
    return "\n".join(lines)


if __name__ == "__main__":
    print(summary(load(sys.argv[1])))
