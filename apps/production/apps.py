from django.apps import AppConfig


class ProductionConfig(AppConfig):
    name = "apps.production"
    label = "production"
    verbose_name = "Proceedings production"

    def ready(self):
        from django.db.models.signals import post_migrate

        post_migrate.connect(create_editor_group, sender=self)


EDITOR_GROUP = "Proceedings editors"
PUBLISHER_GROUP = "Publishers"  # approve publication, enter ISBNs (site-wide)


def create_editor_group(sender, **kwargs):
    """The group that gives editors access to proceedings production in the admin."""
    from django.apps import apps
    from django.contrib.auth.management import create_permissions
    from django.contrib.auth.models import Group, Permission

    # This may run before Django has created the permissions of these apps.
    for label in ("production", "archive"):
        create_permissions(apps.get_app_config(label), verbosity=0, using=kwargs.get("using", "default"))
    group, _ = Group.objects.get_or_create(name=EDITOR_GROUP)
    wanted = [
        ("production", "view_production"), ("production", "view_productioneditor"),
        ("production", "view_submission"), ("production", "change_submission"),
        ("production", "view_paperversion"), ("production", "add_paperversion"),
        ("archive", "view_conferencetrack"), ("production", "view_papercheck"),
    ]
    permissions = Permission.objects.filter(
        content_type__app_label__in={a for a, _ in wanted}, codename__in=[c for _, c in wanted])
    group.permissions.add(*permissions)
    publishers, _ = Group.objects.get_or_create(name=PUBLISHER_GROUP)
    publishers.permissions.add(*permissions, *Permission.objects.filter(
        content_type__app_label="production", codename__in=["publish_production", "change_production"]))
