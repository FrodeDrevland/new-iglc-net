from django.apps import AppConfig
from django.db.models.signals import post_migrate


class ConferencesConfig(AppConfig):
    name = "apps.conferences"
    verbose_name = "Conference sites"

    def ready(self):
        from .setup import sync_site

        post_migrate.connect(sync_site, sender=self)
