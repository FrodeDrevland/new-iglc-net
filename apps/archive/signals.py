"""Keep Paper.authors_text in step with the paper's authors (used by search)."""

from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from .models import Author, Paper


@receiver([post_save, post_delete], sender=Author)
def author_changed(sender, instance, **kwargs):
    paper = Paper.objects.filter(pk=instance.paper_id).first()
    if paper:
        paper.refresh_authors_text()


def refresh_all_authors_text():
    """For bulk imports, which do not send signals."""
    for paper in Paper.objects.prefetch_related("authors"):
        paper.refresh_authors_text()
