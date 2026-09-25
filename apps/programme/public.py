"""The programme as shown on the conference website (the "programme" block of a conference page).

Hidden programmes are shown only in the page editor's preview, to people who work on them.
Parts that are not public are left out (their private link comes with the public pages, step 3).
"""

from __future__ import annotations

from collections import OrderedDict

from .models import Programme


def programme_days(conference, kind: str = "", request=None):
    """{"programme", "days": [(date, [sessions])], "several_parts"} or None."""
    if conference is None:
        return None
    programme = Programme.objects.filter(conference=conference).first()
    if programme is None:
        return None
    if not programme.is_public:
        from .access import can_view

        if not (request is not None and getattr(request, "is_preview", False) and can_view(request.user, programme)):
            return None
    parts = programme.parts.filter(public=True)
    if kind:
        parts = parts.filter(kind=kind)
    sessions = (programme.sessions.filter(part__in=parts)
                .select_related("location", "part", "keynote")
                .prefetch_related("people", "items__submission__paper__authors"))
    days = OrderedDict()
    for session in sessions:
        days.setdefault(session.date, []).append(session)
    return {"programme": programme, "days": list(days.items()), "several_parts": len(set(s.part_id for s in sessions)) > 1}
