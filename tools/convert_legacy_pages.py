"""One-off conversion of the old site's Razor views into content for Wagtail pages.

Reads Views/*.cshtml from the legacy ASP.NET project and writes
apps/pages/legacy_content/pages.json: one entry per page with its slug, parent, title
and a list of body blocks. Most content becomes rich text in the form Wagtail stores it;
tables, images and embedded forms become raw HTML blocks so nothing is lost.

    python tools/convert_legacy_pages.py "<path to legacy>/IGLC/Views"

Then load the pages with:  python manage.py import_legacy_pages
Standard library only.
"""

from __future__ import annotations

import json
import re
import sys
import types
from html import escape
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "apps" / "pages" / "legacy_content" / "pages.json"

# (source view, slug, parent slug or None, title override or None)
PAGES = [
    ("Home/About.cshtml", "about", None, "About the IGLC"),
    ("Home/CharterAndOperatingProcedures.cshtml", "charter-and-operating-procedures", None,
     "IGLC Charter and Operating Procedures"),
    ("Home/Standards.cshtml", "standards", None, None),
    ("Home/Contact.cshtml", "contact", None, "Contact"),
    ("Home/Copyright.cshtml", "copyright", None, "Copyright"),
    ("ForAuthors/About.cshtml", "for-authors", None, "For authors"),
    ("ForAuthors/PaperSubmissionAndReviewProcess.cshtml", "paper-submission-and-review-process", "for-authors", None),
    ("ForAuthors/ContentRequirements.cshtml", "content-requirements", "for-authors", None),
    ("ForAuthors/FormattingRequirements.cshtml", "formatting-requirements", "for-authors", None),
    ("ForAuthors/PaperStructure.cshtml", "paper-structure", "for-authors", "Paper structure"),
    ("ForAuthors/Referencing.cshtml", "referencing", "for-authors", "Referencing"),
    ("ForAuthors/Keywords.cshtml", "keywords", "for-authors", None),
    ("ForAuthors/Templates.cshtml", "templates", "for-authors", None),
    ("ForAuthors/CopyrightPolicy.cshtml", "copyright-policy", "for-authors", None),
    ("ForAuthors/EthicsAndMalpracticeStatement.cshtml", "ethics-and-malpractice-statement", "for-authors", None),
    ("ForAuthors/Publication.cshtml", "publication", "for-authors", None),
    ("ForAuthors/PublicationSchedule.cshtml", "publication-schedule", "for-authors", None),
    ("ActiveConference/Index.cshtml", "active-conference", None, "Upcoming conference"),
    ("ActiveConference/CallForPapers.cshtml", "call-for-papers", "active-conference", None),
    ("ActiveConference/FollowingConference.cshtml", "following-conference", "active-conference", None),
    (None, "community", None, "Community"),
    ("Community/Coaching.cshtml", "coaching", "community", None),
    ("Community/MailingList.cshtml", "mailing-list", "community", "IGLC mailing list"),
    ("Proceedings/Index.cshtml", "proceedings", None, "Full proceedings"),
    (None, "anniversary", None, "Anniversaries"),
    ("Anniversary/SvenBertelsen80.cshtml", "sven-bertelsen-80", "anniversary", None),
    (None, "in-memoriam", None, "In memoriam"),
    ("InMemoriam/SvenBertelsen.cshtml", "sven-bertelsen", "in-memoriam", None),
]

# Tags kept as rich text, mapped to Wagtail's stored form.
RICH_TAGS = {"p": "p", "h1": "h2", "h2": "h2", "h3": "h3", "h32": "h3", "h4": "h4", "h5": "h4",
             "ul": "ul", "ol": "ol", "li": "li", "a": "a", "b": "b", "strong": "b", "i": "i", "em": "i",
             "br": "br", "hr": "hr", "sup": "sup", "sub": "sub"}
RAW_TAGS = {"table", "img", "iframe"}          # kept as raw HTML blocks
DROP_TAGS = {"script", "style", "link", "nav"}  # removed with their content
VOID = {"br", "hr", "img"}


def _load_legacy_redirects():
    """Import apps/archive/legacy.py without Django installed."""
    stub = types.ModuleType("django.http")
    stub.HttpResponsePermanentRedirect = object
    urls = types.ModuleType("django.urls")
    urls.Resolver404, urls.resolve = Exception, lambda path: None
    sys.modules.update({"django": types.ModuleType("django"), "django.http": stub, "django.urls": urls})
    namespace: dict = {}
    exec((ROOT / "apps" / "archive" / "legacy.py").read_text(encoding="utf-8"), namespace)
    return namespace["legacy_target"]


legacy_target = _load_legacy_redirects()


def new_url(old: str) -> str:
    """Rewrite a link to the old site into its new address."""
    old = old.strip()
    if old.startswith("~/"):
        old = old[1:]
    match = re.match(r"^https?://(www\.)?iglc\.net(?P<rest>/.*)?$", old, re.IGNORECASE)
    if match:
        old = match.group("rest") or "/"
    if not old.startswith("/"):
        return old
    path, _, query = old.partition("?")
    params = dict(p.split("=", 1) for p in query.split("&") if "=" in p)
    target = legacy_target(path, params)
    if target:
        return target
    return path.lower() if path.lower().startswith("/papers") else old


def _action_url(action: str, controller: str | None, current: str, args: str = "") -> str:
    view = re.search(r'view\s*=\s*"([^"]+)"', args or "")
    path = f"/{controller or current}/{action}"
    return new_url(path + (f"?view={view.group(1)}" if view else ""))


def strip_razor(source: str, controller: str) -> tuple[str, str | None]:
    title_match = re.search(r'ViewBag\.Title\s*=\s*"([^"]*)"', source)
    text = re.sub(r"@\*.*?\*@", "", source, flags=re.S)
    text = _remove_braced(text, r"@section\s+\w+\s*\{")
    text = _remove_braced(text, r"@\{")
    text = re.sub(
        r'@Url\.Action\(\s*"([^"]+)"\s*(?:,\s*"([^"]+)")?([^)]*)\)',
        lambda m: _action_url(m.group(1), m.group(2), controller, m.group(3)), text)
    text = re.sub(
        r'@Html\.ActionLink\(\s*"([^"]+)"\s*,\s*"([^"]+)"\s*(?:,\s*"([^"]+)")?([^)]*)\)',
        lambda m: f'<a href="{_action_url(m.group(2), m.group(3), controller, m.group(4))}">{m.group(1)}</a>', text)
    text = text.replace("@@", "@")
    return text, title_match.group(1).strip() if title_match else None


def _remove_braced(text: str, opener: str) -> str:
    while True:
        match = re.search(opener, text)
        if not match:
            return text
        depth, i = 1, match.end()
        while i < len(text) and depth:
            depth += {"{": 1, "}": -1}.get(text[i], 0)
            i += 1
        text = text[:match.start()] + text[i:]


def _rewrite_links(tag_text: str) -> str:
    return re.sub(r'\b(href|src)="([^"]*)"', lambda m: f'{m.group(1)}="{escape(new_url(m.group(2)))}"', tag_text)


class _Converter(HTMLParser):
    """Split cleaned HTML into rich-text and raw-HTML blocks."""

    def __init__(self):
        super().__init__(convert_charrefs=False)
        self.blocks: list[dict] = []
        self.rich: list[str] = []
        self.raw: list[str] | None = None
        self.raw_tag: str | None = None
        self.raw_depth = 0
        self.drop_depth = 0
        self.h1_seen: str | None = None
        self._in_h1 = False

    def _flush_rich(self):
        html = re.sub(r"\s+", " ", "".join(self.rich)).strip()
        html = re.sub(r"<p>\s*</p>", "", html)
        if html:
            self.blocks.append({"type": "text", "value": html})
        self.rich = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if self.drop_depth or tag in DROP_TAGS:
            self.drop_depth += tag not in VOID
            return
        if self.raw is not None:
            self.raw.append(_rewrite_links(self.get_starttag_text()))
            self.raw_depth += tag == self.raw_tag
            return
        if tag in RAW_TAGS or (tag == "div" and "data-sender-form-id" in attrs):
            self._flush_rich()
            text = self.get_starttag_text()
            text = _rewrite_links(text)
            if tag in VOID:
                self.blocks.append({"type": "html", "value": text})
            else:
                self.raw, self.raw_tag, self.raw_depth = [text], tag, 1
            return
        if tag == "h1" and self.h1_seen is None:
            self._in_h1 = True
            self.h1_seen = ""
            return
        mapped = RICH_TAGS.get(tag)
        if mapped == "a":
            href = attrs.get("href")
            self.rich.append(f'<a href="{escape(new_url(href))}">' if href else "<a>")
        elif mapped in ("br", "hr"):
            self.rich.append(f"<{mapped}/>")
        elif mapped:
            self.rich.append(f"<{mapped}>")

    def handle_endtag(self, tag):
        if self.drop_depth:
            self.drop_depth -= tag in DROP_TAGS or tag not in VOID
            return
        if self.raw is not None:
            self.raw.append(f"</{tag}>")
            if tag == self.raw_tag:
                self.raw_depth -= 1
                if not self.raw_depth:
                    self.blocks.append({"type": "html", "value": "".join(self.raw).strip()})
                    self.raw = None
            return
        if tag == "h1" and self._in_h1:
            self._in_h1 = False
            return
        mapped = RICH_TAGS.get(tag)
        if mapped and mapped not in ("br", "hr"):
            self.rich.append(f"</{mapped}>")

    def handle_data(self, data):
        if self.drop_depth:
            return
        if self.raw is not None:
            self.raw.append(data)
        elif self._in_h1:
            self.h1_seen += data
        else:
            # The old Standards page showed "~/Content/Documents/Standards/" in one link text.
            data = re.sub(r"~/Content/(?:[^/\s]+/)*", "", data)
            self.rich.append(escape(data, quote=False))

    def handle_entityref(self, name):
        self.handle_data_raw(f"&{name};")

    def handle_charref(self, name):
        self.handle_data_raw(f"&#{name};")

    def handle_data_raw(self, text):
        if self.drop_depth:
            return
        if self.raw is not None:
            self.raw.append(text)
        elif self._in_h1:
            self.h1_seen += text
        else:
            self.rich.append(text)

    def result(self):
        self._flush_rich()
        return self.blocks


def convert(views: Path, source: str):
    controller = source.split("/")[0]
    html, title = strip_razor((views / source).read_text(encoding="utf-8-sig"), controller)
    parser = _Converter()
    parser.feed(html)
    blocks = parser.result()
    h1 = re.sub(r"\s+", " ", parser.h1_seen or "").strip()
    return blocks, h1 or title


def main(views_dir: str) -> int:
    views = Path(views_dir)
    pages = []
    for source, slug, parent, title in PAGES:
        blocks, found_title = convert(views, source) if source else ([], None)
        title = title or found_title or slug.replace("-", " ").capitalize()
        # Drop a leading heading that only repeats the page title.
        if blocks and blocks[0]["type"] == "text":
            first = blocks[0]["value"]
            match = re.match(r"<h2>(.*?)</h2>\s*", first)
            if match and match.group(1).strip().lower() == title.lower():
                blocks[0]["value"] = first[match.end():]
                if not blocks[0]["value"]:
                    blocks.pop(0)
        pages.append({"slug": slug, "parent": parent, "title": title, "source": source, "body": blocks})
        print(f"{slug:40} {len(blocks):2} blocks  {pages[-1]['title']}")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(pages, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote {len(pages)} pages to {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
