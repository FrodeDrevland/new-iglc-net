"""Reference formats shown on paper pages (ported from the old site's PaperHtml helpers).

- apa7: full reference in APA 7th edition style.
- iglc_short: the shortened reference the IGLC uses in its own papers, "... IGLC32. https://doi.org/...".

Both return plain text parts so the template can add italics and links safely.
"""

import re

PARTICLES = {"da", "do", "de", "dos", "das", "van", "von", "der", "den"}


def initials(first_name: str) -> str:
    """'Jean-Pierre da Silva' -> 'J.-P. S.'; 'Iris D.' -> 'I. D.'."""
    parts = []
    for word in (first_name or "").split():
        if word.lower() in PARTICLES:
            continue
        pieces = [p for p in word.split("-") if p]
        parts.append("-".join(f"{p[0].upper()}." for p in pieces))
    return " ".join(parts)


def _join(names: list[str]) -> str:
    """APA 7 list: 'A', 'A, & B', 'A, B, & C'."""
    if len(names) <= 1:
        return "".join(names)
    return ", ".join(names[:-1]) + ", & " + names[-1]


def author_list(paper) -> str:
    names = []
    for a in paper.authors.all():
        ini = initials(a.first_name)
        names.append(f"{a.last_name}, {ini}" if ini else a.last_name)
    return _join(names)


def editor_list(conference) -> str:
    names = []
    for e in conference.editors.all():
        ini = initials(e.first_name)
        names.append(f"{ini} {e.last_name}".strip())
    return _join(names)


def _end(text: str) -> str:
    text = text.strip()
    return text if text.endswith((".", "?", "!")) else text + "."


def apa7(paper) -> dict:
    conference = paper.conference
    authors = author_list(paper)
    editors = editor_list(conference)
    return {
        "before": " ".join(filter(None, [
            _end(authors) if authors else "",
            f"({paper.year or 'n.d.'}).",
            _end(paper.title),
            f"In {editors} ({'Eds.' if conference.editors.count() > 1 else 'Ed.'})," if editors else "In",
        ])),
        "italic": conference.proceedings_title,
        "after": (f" (pp. {paper.first_page}–{paper.last_page})" if paper.first_page and paper.last_page else "")
                 + "." + (f" {_end(conference.publisher)}" if conference.publisher else ""),
        "doi_url": paper.doi_url,
    }


def iglc_short(paper) -> dict:
    authors = author_list(paper)
    return {
        "before": " ".join(filter(None, [
            _end(authors) if authors else "",
            f"({paper.year or 'n.d.'}).",
            _end(paper.title),
        ])),
        "italic": f"IGLC{paper.conference.number}",
        "after": ".",
        "doi_url": paper.doi_url,
    }


def as_text(ref: dict) -> str:
    return re.sub(r"\s+", " ", f"{ref['before']} {ref['italic']}{ref['after']} {ref['doi_url']}").strip()
