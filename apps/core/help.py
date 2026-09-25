"""The site's documentation (docs/*.md and the README), readable in the back office under Help.

Each document says who may read it. Everyone with back-office access: the conference websites and the
paper check rules. Proceedings editors and publishers also: the production process. Superusers: all,
including the running of the site (deployment, switch-over, handover).
"""

import re
from dataclasses import dataclass

from django.utils.html import strip_tags
from django.utils.text import slugify
from markdown_it import MarkdownIt
from django.conf import settings
from django.urls import reverse

EVERYONE, EDITORS, SUPERUSERS = "everyone", "editors", "superusers"


@dataclass(frozen=True)
class Doc:
    slug: str
    path: str  # relative to BASE_DIR
    audience: str
    group: str
    summary: str
    name: str = ""  # instead of the document's first heading


DOCS = [
    Doc("conference-sites", "docs/conference-sites.md", EVERYONE, "Conferences",
        "Setting up a conference's website, and what the organisers can do."),
    Doc("paper-check-rules", "docs/paper-check-rules.md", EVERYONE, "Papers and proceedings",
        "Every rule of the paper check, what it looks for and how strict it is."),
    Doc("production-process", "docs/production-process.md", EDITORS, "Papers and proceedings",
        "Submission, review and proceedings production once the IGLC runs its own submission system."),
    Doc("readme", "README.md", SUPERUSERS, "Running the site",
        "What the code is, how it is organised and how to run it locally.", "About the code (README)"),
    Doc("deploy-azure", "docs/deploy-azure.md", SUPERUSERS, "Running the site",
        "The production site on Azure: setting it up, deploying and backups."),
    Doc("deploy-unraid", "docs/deploy-unraid.md", SUPERUSERS, "Running the site",
        "The password-protected preview on the Unraid server."),
    Doc("switch-over", "docs/switch-over.md", SUPERUSERS, "Running the site",
        "Checklist for moving iglc.net from the old site to the new one."),
    Doc("handover", "docs/handover.md", SUPERUSERS, "Running the site",
        "The accounts behind iglc.net and how to hand them over."),
    Doc("url-inventory", "docs/url-inventory.md", SUPERUSERS, "Running the site",
        "Every address of the old site and how the new site handles it."),
    Doc("content-files", "docs/content-files.md", SUPERUSERS, "Running the site",
        "The files from the old site's Content folder."),
]
BY_SLUG = {doc.slug: doc for doc in DOCS}
BY_PATH = {doc.path: doc for doc in DOCS}


def is_editor(user) -> bool:
    from apps.production.access import is_publisher, productions_for

    return is_publisher(user) or productions_for(user).exists()


def can_read(user, doc: Doc) -> bool:
    if not user.is_authenticated:
        return False
    if user.is_superuser or doc.audience == EVERYONE:
        return True
    return doc.audience == EDITORS and is_editor(user)


def readable(user) -> list[Doc]:
    return [doc for doc in DOCS if can_read(user, doc)]


def read(doc: Doc) -> tuple[str, str, str]:
    """(title, body HTML, table of contents HTML). The first heading is the title."""
    text = (settings.BASE_DIR / doc.path).read_text(encoding="utf-8")
    title = doc.slug
    match = re.match(r"\s*#\s+(.+)\n", text)
    if match:
        title, text = match.group(1).strip(), text[match.end():]
    title = doc.name or title
    html = _MD.render(text)
    # Task lists ("- [ ] item") as boxes, and ids on the sections for the contents.
    html = re.sub(r"<li>(<p>)?\[ \] ", r"<li>\1☐ ", html)
    html = re.sub(r"<li>(<p>)?\[x\] ", r"<li>\1☑ ", html, flags=re.I)
    sections = []

    def section(match):
        text = strip_tags(match.group(1))
        anchor = slugify(text) or f"section-{len(sections) + 1}"
        sections.append((anchor, text))
        return f'<h2 id="{anchor}">{match.group(1)}</h2>'

    html = re.sub(r"<h2>(.*?)</h2>", section, html)
    toc = ""
    if len(sections) > 1:
        toc = '<ul class="toc">' + "".join(f'<li><a href="#{a}">{t}</a></li>' for a, t in sections) + "</ul>"
    return title, html, toc


_MD = MarkdownIt("commonmark", {"html": True}).enable(["table", "strikethrough"])


def title(doc: Doc) -> str:
    text = (settings.BASE_DIR / doc.path).read_text(encoding="utf-8")
    match = re.match(r"\s*#\s+(.+)\n", text)
    return doc.name or (match.group(1).strip() if match else doc.slug)


_LINK = re.compile(r'href="(?:\.\./|\./)?((?:docs/)?[\w.-]+\.md)(#[^"]*)?"')
_CODE = re.compile(r"<code>((?:docs/)?[\w.-]+\.md)</code>")
_BARE = re.compile(r"(?<![\w/\"'>.-])((?:docs/)?[\w-]+\.md)")


def _target(name: str) -> Doc | None:
    return BY_PATH.get(name) or BY_PATH.get(f"docs/{name}")


def link_docs(html: str, user) -> str:
    """Links and mentions of other documents (docs/deploy-azure.md) go to their help pages."""

    def href(match):
        doc = _target(match.group(1))
        if doc is None or not can_read(user, doc):
            return match.group(0)
        return f'href="{reverse("site_help:doc", args=[doc.slug])}{match.group(2) or ""}"'

    def code(match):
        doc = _target(match.group(1))
        if doc is None or not can_read(user, doc):
            return match.group(0)
        return f'<a href="{reverse("site_help:doc", args=[doc.slug])}">{match.group(0)}</a>'

    def bare(match):
        doc = _target(match.group(1))
        if doc is None or not can_read(user, doc):
            return match.group(0)
        return f'<a href="{reverse("site_help:doc", args=[doc.slug])}">{match.group(1)}</a>'

    return _BARE.sub(bare, _CODE.sub(code, _LINK.sub(href, html)))
