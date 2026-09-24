from django.apps import AppConfig


class ArchiveConfig(AppConfig):
    name = "apps.archive"
    label = "archive"
    verbose_name = "Proceedings archive"

    def ready(self):
        from django.db.models.signals import post_migrate

        from . import signals  # noqa: F401

        post_migrate.connect(create_archive_editor_group, sender=self)


ARCHIVE_EDITOR_GROUP = "Archive editors"
# What they may edit: the archive (conferences, papers, authors, links) and the committees.
# Deleting conferences and papers is left out: DOIs point to them.
ARCHIVE_EDITOR_PERMISSIONS = {
    "archive": ["view_conference", "change_conference", "add_conference",
                "view_paper", "change_paper", "add_paper",
                "view_authorperson", "change_authorperson", "add_authorperson", "delete_authorperson",
                "view_linkcategory", "change_linkcategory", "add_linkcategory", "delete_linkcategory",
                "view_conferencetrack", "view_editor", "view_volume", "view_proceedingsfile", "view_author",
                "view_link"],
    "governance": ["view_committee", "change_committee", "add_committee", "view_seat"],
    "wagtailadmin": ["access_admin"],
}


def create_archive_editor_group(sender, **kwargs):
    from django.apps import apps
    from django.contrib.auth.management import create_permissions
    from django.contrib.auth.models import Group, Permission

    for label in ARCHIVE_EDITOR_PERMISSIONS:
        create_permissions(apps.get_app_config(label), verbosity=0, using=kwargs.get("using", "default"))
    group, _ = Group.objects.get_or_create(name=ARCHIVE_EDITOR_GROUP)
    for label, codenames in ARCHIVE_EDITOR_PERMISSIONS.items():
        group.permissions.add(*Permission.objects.filter(content_type__app_label=label, codename__in=codenames))
