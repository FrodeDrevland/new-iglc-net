"""Who may see and edit a conference's programme (docs/programme.md, "Who edits what").

- Conference chairs (the programme's chairs group): every part, the locations and the settings.
- Organisers (the group "IGLC nn organisers" of the conference website): the locations.
- Part editors (each part's group: scientific chairs, industry day chairs, workshop day chairs,
  PhD summer school deans): the sessions of their part.
- Superusers: everything, also when the conference website is frozen.

Everyone with a role sees the whole programme of that conference, and no other conference's.
"""

from __future__ import annotations

from .models import Part, Programme


def _group_ids(user) -> set[int]:
    if not hasattr(user, "_programme_group_ids"):
        user._programme_group_ids = set(user.groups.values_list("pk", flat=True)) if user.is_authenticated else set()
    return user._programme_group_ids


def is_frozen(programme) -> bool:
    home = getattr(programme.conference, "site_home", None)
    return bool(home and home.frozen)


def is_chair(user, programme) -> bool:
    if not user.is_authenticated or not user.is_active:
        return False
    return user.is_superuser or (programme.chairs_id is not None and programme.chairs_id in _group_ids(user))


def is_organiser(user, programme) -> bool:
    return user.is_authenticated and user.groups.filter(name=programme.organiser_group_name()).exists()


def _may_change(user, programme) -> bool:
    return user.is_superuser or not is_frozen(programme)


def can_edit_part(user, part) -> bool:
    if not _may_change(user, part.programme):
        return False
    return is_chair(user, part.programme) or (part.editors_id is not None and part.editors_id in _group_ids(user))


def editable_parts(user, programme):
    return [part for part in programme.parts.all() if can_edit_part(user, part)]


def can_edit_locations(user, programme) -> bool:
    return _may_change(user, programme) and (is_chair(user, programme) or is_organiser(user, programme))


def can_edit_settings(user, programme) -> bool:
    return _may_change(user, programme) and is_chair(user, programme)


def can_view(user, programme) -> bool:
    if not user.is_authenticated or not user.is_active:
        return False
    return (is_chair(user, programme) or is_organiser(user, programme)
            or programme.parts.filter(editors_id__in=_group_ids(user)).exists())


def programmes_for(user):
    programmes = Programme.objects.select_related("conference")
    if not user.is_authenticated or not user.is_active:
        return programmes.none()
    if user.is_superuser:
        return programmes
    groups = _group_ids(user)
    organiser_numbers = [int(name.split()[1]) for name in user.groups.filter(name__regex=r"^IGLC \d+ organisers$")
                         .values_list("name", flat=True)]
    by_part = Part.objects.filter(editors_id__in=groups).values_list("programme_id", flat=True)
    from django.db.models import Q

    return programmes.filter(Q(chairs_id__in=groups) | Q(pk__in=by_part)
                             | Q(conference__number__in=organiser_numbers)).distinct()
