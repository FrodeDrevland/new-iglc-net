from django import template

from .. import public
from ..public import programme_days as _programme_days

register = template.Library()


@register.simple_tag(takes_context=True)
def programme_days(context, conference, kind=""):
    return _programme_days(conference, kind or "", context.get("request"))


@register.simple_tag
def programme_url(name, year, *args, key=""):
    """The address of a programme page on the conference site, e.g. {% programme_url 'session' 2027 s.pk %}.
    key: a part's private link, carried to the pages of its sessions."""
    address = public.url(name, year, *args)
    return f"{address}?k={key}" if key else address
