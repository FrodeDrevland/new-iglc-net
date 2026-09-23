from django.conf import settings


def navigation(request):
    """The first part of the path, so the main menu can mark the current section."""
    return {
        "nav_section": request.path.strip("/").split("/")[0].lower(),
        "conference_website": settings.CONFERENCE_WEBSITE,
        "about_sections": ("about", "charter-and-operating-procedures", "standards", "contact", "copyright"),
    }
