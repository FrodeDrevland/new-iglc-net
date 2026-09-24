"""Who may see and do what in a production."""

from .models import Production, ProductionEditor


def role(user, production) -> str | None:
    """'chief', 'editor' or None. Superusers count as chief editors."""
    if not user.is_authenticated:
        return None
    if user.is_superuser:
        return ProductionEditor.Role.CHIEF
    entry = production.editors.filter(user=user).first()
    return entry.role if entry else None


def productions_for(user):
    if user.is_superuser:
        return Production.objects.select_related("conference")
    return Production.objects.filter(editors__user=user).select_related("conference").distinct()


def submissions_for(user, production):
    """Chief editors: all papers. Editors: the papers of their tracks, or all when they have none."""
    papers = production.submissions.select_related("track", "editor")
    if role(user, production) == ProductionEditor.Role.CHIEF:
        return papers
    entry = production.editors.filter(user=user).first()
    if entry is None:
        return papers.none()
    tracks = list(entry.tracks.all())
    return papers.filter(track__in=tracks) if tracks else papers
