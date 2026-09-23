def navigation(request):
    """The first part of the path, so the main menu can mark the current section."""
    return {"nav_section": request.path.strip("/").split("/")[0].lower()}
