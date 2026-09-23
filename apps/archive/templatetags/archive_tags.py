import re

from django import template
from django.utils.html import escape
from django.utils.safestring import mark_safe

from apps.archive.search import terms

register = template.Library()


def _pattern(query):
    words = sorted(terms(query or ""), key=len, reverse=True)
    if not words:
        return None
    # Match the start of words, so "plan" also marks "planning".
    return re.compile(r"\b(" + "|".join(re.escape(w) for w in words) + r")", re.IGNORECASE)


@register.filter
def highlight(text, query):
    """Escape the text and wrap the search words in <mark>."""
    text = escape(text or "")
    pattern = _pattern(query)
    if pattern:
        text = pattern.sub(r"<mark>\1</mark>", text)
    return mark_safe(text)


@register.filter
def snippet(text, query, length=260):
    """A short part of the text around the first search word, highlighted."""
    text = re.sub(r"\s+", " ", text or "").strip()
    pattern = _pattern(query)
    match = pattern.search(text) if pattern else None
    if not match or len(text) <= length:
        part = text[:length]
        prefix, suffix = "", "…" if len(text) > length else ""
    else:
        start = max(0, match.start() - length // 3)
        start = text.rfind(" ", 0, start) + 1 if start else 0
        part = text[start:start + length]
        prefix, suffix = ("…" if start else ""), ("…" if start + length < len(text) else "")
    return mark_safe(prefix + str(highlight(part, query)) + suffix)
