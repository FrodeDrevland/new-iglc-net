"""Starting a conference's programme: its parts and the groups of people who edit them.

    start(conference, time_zone)   repeatable; creates what is missing
    part_group(part)               the group whose members edit a part
"""

from __future__ import annotations

from django.contrib.auth.models import Group, Permission
from django.db import transaction

from .models import Part, Programme

DEFAULT_PARTS = [
    # kind, name, public, colour, editors
    (Part.Kind.ACADEMIC, "Academic conference", True, "#365a91", "scientific chairs"),
    (Part.Kind.INDUSTRY, "Industry day", True, "#b35a14", "industry day chairs"),
    (Part.Kind.WORKSHOP, "Workshop day", True, "#2e6b34", "workshop day chairs"),
    (Part.Kind.PHD, "PhD summer school", False, "#6a2c8c", "PhD summer school deans"),
]
EDITORS_BY_KIND = {kind: editors for kind, _, _, _, editors in DEFAULT_PARTS}


def _group(name: str) -> Group:
    group, _ = Group.objects.get_or_create(name=name)
    group.permissions.add(Permission.objects.get(content_type__app_label="wagtailadmin", codename="access_admin"))
    return group


def part_group(part: Part) -> Group:
    """The part's editors group, made if missing: 'IGLC 35 scientific chairs' and so on."""
    if part.editors_id:
        return part.editors
    editors = EDITORS_BY_KIND.get(part.kind) or f"{part.name} editors"
    group = _group(f"IGLC {part.programme.conference.number} {editors}")
    part.editors = group
    part.save(update_fields=["editors"])
    return group


@transaction.atomic
def start(conference, time_zone: str) -> Programme:
    programme = Programme.objects.filter(conference=conference).first()
    if programme is None:
        if not conference.start_date:
            raise ValueError("The conference needs its dates first (Conferences → All conferences).")
        programme = Programme.objects.create(conference=conference, time_zone=time_zone,
                                             first_day=conference.start_date,
                                             last_day=conference.end_date or conference.start_date)
    if not programme.chairs_id:
        programme.chairs = _group(f"IGLC {conference.number} conference chairs")
        programme.save(update_fields=["chairs"])
    if not programme.parts.exists():
        for order, (kind, name, public, colour, _) in enumerate(DEFAULT_PARTS):
            Part.objects.create(programme=programme, kind=kind, name=name, public=public, colour=colour,
                                sort_order=order)
    for part in programme.parts.filter(editors__isnull=True):
        part_group(part)
    return programme
