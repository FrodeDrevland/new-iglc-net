"""Who may see and do what in a production.

- Editors (per production): the papers of their tracks, or all papers.
- Chief editors (per production): everything in it; they stage publication.
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
    return PUBLISHER if is_publisher(user) else None


def productions_for(user):
    if user.is_superuser or is_publisher(user):
        return Production.objects.select_related("conference")
    return Production.objects.filter(editors__user=user).select_related("conference").distinct()


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
