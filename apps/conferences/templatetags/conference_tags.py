from django import template
from django.utils.dateformat import format as date_format

register = template.Library()


@register.simple_tag
def date_range(start, end=None):
    """'19–23 July 2027', '30 June – 2 July 2027', '31 December 2027 – 2 January 2028'."""
    if not start:
        return ""
    if not end or end == start:
        return date_format(start, "j F Y")
    if (start.year, start.month) == (end.year, end.month):
        return f"{start.day}–{date_format(end, 'j F Y')}"
    if start.year == end.year:
        return f"{date_format(start, 'j F')} – {date_format(end, 'j F Y')}"
    return f"{date_format(start, 'j F Y')} – {date_format(end, 'j F Y')}"
