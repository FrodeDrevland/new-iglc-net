from wagtail import hooks

from .admin_views import ArchiveGroup, person_chooser


@hooks.register("register_admin_viewset")
def archive_viewsets():
    return [ArchiveGroup(), person_chooser]
