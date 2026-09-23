from django.conf import settings


def _section(path):
    section = path.strip("/").split("/")[0].lower()
    return "papers" if section == "authors" else section


def navigation(request):
    """The first part of the path, so the main menu can mark the current section."""
    return {
        "nav_section": _section(request.path),
        "conference_website": settings.CONFERENCE_WEBSITE,
        "about_sections": ("about", "charter-and-operating-procedures", "standards", "contact", "copyright"),
    }
