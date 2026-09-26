"""Who may see and do what in a production.

- Editors (per production): the papers of their tracks, or all papers. The conference's editorial
  assistants (the group "IGLC nn editorial assistants") are editors of all its papers without being
  listed; listing them limits them to some tracks.
- Chief editors (per production): everything in it; they stage publication. The conference's
  scientific chairs (the group "IGLC nn scientific chairs", apps/conferences/roles.py) are chief
  editors of its production without being listed.
- Publishers (site-wide, the "Publishers" group): every production; they approve publication
  of the papers, corrections and the full proceedings, and enter the ISBNs.
- Superusers: everything, as chief editor and publisher.
"""

from .models import Production, ProductionEditor

PUBLISHER = "publisher"


def is_publisher(user) -> bool:
    return user.is_authenticated and user.has_perm("production.publish_production")


def role(user, production) -> str | None:
    """'chief', 'editor', 'publisher' or None. Superusers count as chief editors (and publishers)."""
    if not user.is_authenticated:
        return None
    if user.is_superuser:
        return ProductionEditor.Role.CHIEF
    entry = production.editors.filter(user=user).first()
    if entry:
        return entry.role
    if is_scientific_chair(user, production.conference):
        return ProductionEditor.Role.CHIEF
    if is_editorial_assistant(user, production.conference):
        return ProductionEditor.Role.EDITOR
    return PUBLISHER if is_publisher(user) else None


def _numbers(user, role: str) -> list[int]:
    names = user.groups.filter(name__regex=rf"^IGLC \d+ {role}$").values_list("name", flat=True)
    return [int(name.split()[1]) for name in names]


def _scientific_numbers(user) -> list[int]:
    return _numbers(user, "scientific chairs")


def is_editorial_assistant(user, conference) -> bool:
    return user.is_authenticated and conference.number in _numbers(user, "editorial assistants")


def is_scientific_chair(user, conference) -> bool:
    return user.is_authenticated and conference.number in _scientific_numbers(user)


def chief_editors(production):
    """The chief editors: those listed as such, and the conference's scientific chairs."""
    from django.contrib.auth import get_user_model
    from django.db.models import Q

    return (get_user_model().objects.filter(
        Q(production_roles__production=production, production_roles__role=ProductionEditor.Role.CHIEF)
        | Q(groups__name=f"IGLC {production.conference.number} scientific chairs"), is_active=True).distinct())


def chief_conference_ids(user) -> list[int]:
    """The conferences whose proceedings this person is chief editor of."""
    from apps.archive.models import Conference
    from django.db.models import Q

    return list(Conference.objects.filter(
        Q(production__editors__user=user, production__editors__role=ProductionEditor.Role.CHIEF)
        | Q(number__in=_scientific_numbers(user))).values_list("pk", flat=True).distinct())


def productions_for(user):
    if user.is_superuser or is_publisher(user):
        return Production.objects.select_related("conference")
    from django.db.models import Q

    return (Production.objects.filter(Q(editors__user=user) | Q(conference__number__in=_scientific_numbers(user) + _numbers(user, "editorial assistants")))
            .select_related("conference").distinct())


def submissions_for(user, production):
    """Chief editors and publishers: all papers. Editors: the papers of their tracks, or all when they have none."""
    papers = production.submissions.select_related("track", "editor")
    if role(user, production) in (ProductionEditor.Role.CHIEF, PUBLISHER):
        return papers
    entry = production.editors.filter(user=user).first()
    if entry is None:
        return papers if is_editorial_assistant(user, production.conference) else papers.none()
    tracks = list(entry.tracks.all())
    return papers.filter(track__in=tracks) if tracks else papers
