"""Who may see and do what in a production.

- Editors (per production): the papers of their tracks, or all papers.
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
    return PUBLISHER if is_publisher(user) else None


def _scientific_numbers(user) -> list[int]:
    names = user.groups.filter(name__regex=r"^IGLC \d+ scientific chairs$").values_list("name", flat=True)
    return [int(name.split()[1]) for name in names]


def is_scientific_chair(user, conference) -> bool:
    return user.is_authenticated and conference.number in _scientific_numbers(user)


def productions_for(user):
    if user.is_superuser or is_publisher(user):
        return Production.objects.select_related("conference")
    from django.db.models import Q

    return (Production.objects.filter(Q(editors__user=user) | Q(conference__number__in=_scientific_numbers(user)))
            .select_related("conference").distinct())


def submissions_for(user, production):
    """Chief editors and publishers: all papers. Editors: the papers of their tracks, or all when they have none."""
    papers = production.submissions.select_related("track", "editor")
    if role(user, production) in (ProductionEditor.Role.CHIEF, PUBLISHER):
        return papers
    entry = production.editors.filter(user=user).first()
    if entry is None:
        return papers.none()
    tracks = list(entry.tracks.all())
    return papers.filter(track__in=tracks) if tracks else papers
