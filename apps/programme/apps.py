from django.apps import AppConfig


class ProgrammeConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.programme"
    verbose_name = "Conference programme"

    def ready(self):
        from django.db.models.signals import post_save, pre_save

        from apps.archive.models import Conference

        pre_save.connect(_remember_dates, sender=Conference, dispatch_uid="programme_remember_dates")
        post_save.connect(_follow_dates, sender=Conference, dispatch_uid="programme_follow_dates")


def _remember_dates(sender, instance, **kwargs):
    old = sender.objects.filter(pk=instance.pk).values("start_date", "end_date").first() if instance.pk else None
    instance._programme_old_dates = (old["start_date"], old["end_date"]) if old else None


def _follow_dates(sender, instance, created, **kwargs):
    """When the conference's dates change, its programme's days follow (Programme.sync_days)."""
    if created or getattr(instance, "_programme_old_dates", None) == (instance.start_date, instance.end_date):
        return
    programme = getattr(instance, "programme", None)
    if programme is not None:
        programme.sync_days()
