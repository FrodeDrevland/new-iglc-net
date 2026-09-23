from django.apps import AppConfig


class ArchiveConfig(AppConfig):
    name = "apps.archive"
    label = "archive"
    verbose_name = "Proceedings archive"

    def ready(self):
        from . import signals  # noqa: F401
