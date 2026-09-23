from django.db import models
from wagtail import blocks
from wagtail.admin.panels import FieldPanel
from wagtail.fields import StreamField
from wagtail.models import Page

RICH_TEXT_FEATURES = [
    "h2", "h3", "h4", "bold", "italic", "superscript", "subscript", "ol", "ul", "hr",
    "link", "document-link", "image", "embed",
]


class StandardPage(Page):
    """An ordinary content page: About, Charter, For authors, Standards and so on."""

    intro = models.TextField(blank=True, help_text="One or two sentences shown under the title.")
    body = StreamField(
        [
            ("text", blocks.RichTextBlock(features=RICH_TEXT_FEATURES)),
            ("html", blocks.RawHTMLBlock(
                help_text="Raw HTML, for tables and embedded forms that the text editor cannot hold.")),
        ],
        blank=True,
    )
    show_child_pages = models.BooleanField(
        default=True, help_text="List the pages below this one at the end of the page."
    )

    content_panels = Page.content_panels + [
        FieldPanel("intro"),
        FieldPanel("body"),
        FieldPanel("show_child_pages"),
    ]

    template = "pages/standard_page.html"

    def get_context(self, request, *args, **kwargs):
        """The section this page belongs to, for the side menu: the page itself if it has
        sub-pages (for example For authors), otherwise its parent if that is not the home page."""
        context = super().get_context(request, *args, **kwargs)
        children = self.get_children().live()
        section = self if children.exists() else self.get_parent().specific
        if section.depth <= 2:
            section = None
        context["section"] = section
        context["section_pages"] = section.get_children().live() if section else []
        return context
