from django.db import models
from wagtail.admin.panels import FieldPanel
from wagtail.fields import RichTextField
from wagtail.models import Page


class StandardPage(Page):
    """An ordinary content page: About, Contact, For authors, Standards and so on."""

    intro = models.TextField(blank=True, help_text="One or two sentences shown under the title.")
    body = RichTextField(blank=True)

    content_panels = Page.content_panels + [FieldPanel("intro"), FieldPanel("body")]

    template = "pages/standard_page.html"
