from django import template

from ..public import programme_days as _programme_days

register = template.Library()


@register.simple_tag(takes_context=True)
def programme_days(context, conference, kind=""):
    return _programme_days(conference, kind or "", context.get("request"))
