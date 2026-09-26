"""Conference websites: one small site per conference, at conference.iglc.net/<year>/.

The pages live in their own Wagtail Site (the host name is the setting CONFERENCE_HOST):

    ConferenceIndexPage          conference.iglc.net/          serves the current conference
      ConferenceHomePage         conference.iglc.net/2027/     one per conference, slug = year
        ConferencePage           call for papers, venue, registration, programme, free pages
        KeynotesPage, CommitteesPage, SponsorsPage, AcceptedPapersPage

The organisers of a conference edit and publish the pages below their home page (the site's
settings, current and frozen, stay with the IGLC). Dates, tracks and accepted papers come from the platform.
After the conference the site is frozen and linked from the archive.
"""

from __future__ import annotations

import re

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.http import HttpResponseRedirect
from django.utils.functional import cached_property
from modelcluster.fields import ParentalKey
from wagtail import blocks
from wagtail.admin.panels import (FieldPanel, HelpPanel, InlinePanel, MultiFieldPanel, ObjectList,
                                  TabbedInterface)
from wagtail.embeds.blocks import EmbedBlock
from wagtail.fields import RichTextField, StreamField
from wagtail.images import get_image_model_string
from wagtail.images.blocks import ImageChooserBlock
from wagtail.models import Orderable, Page
from wagtail.url_routing import RouteResult

from apps.pages.models import RICH_TEXT_FEATURES

IMAGE = get_image_model_string()
HEX = re.compile(r"^#[0-9a-fA-F]{6}$")

# Fonts are served from the site itself (no font services: visitors' addresses stay here).
HEADING_FONTS = {
    "serif": ('"Source Serif 4", Georgia, "Times New Roman", serif', "Source Serif (IGLC default)"),
    "sans": ('"Source Sans 3", system-ui, -apple-system, "Segoe UI", Roboto, Arial, sans-serif', "Source Sans"),
    "georgia": ("Georgia, Cambria, \"Times New Roman\", serif", "Georgia"),
    "system": ("system-ui, -apple-system, \"Segoe UI\", Roboto, Arial, sans-serif", "The visitor's system font"),
}


# ---------------------------------------------------------------- colours

def _luminance(hex_colour: str) -> float:
    channels = [int(hex_colour[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    linear = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def contrast(a: str, b: str) -> float:
    """The WCAG contrast ratio of two colours (1 to 21)."""
    la, lb = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def text_on(background: str) -> str:
    """Black or white, whichever reads better on the background."""
    return "#ffffff" if contrast(background, "#ffffff") >= contrast(background, "#111111") else "#111111"


# ---------------------------------------------------------------- content blocks

class ButtonBlock(blocks.StructBlock):
    label = blocks.CharBlock(max_length=60)
    page = blocks.PageChooserBlock(required=False)
    url = blocks.URLBlock(required=False, help_text="Used when no page is chosen, e.g. the registration system.")

    class Meta:
        icon = "link"
        template = "conferences/blocks/button.html"


class ImageBlock(blocks.StructBlock):
    image = ImageChooserBlock()
    alt = blocks.CharBlock(required=False, max_length=250,
                           help_text="What the picture shows, for readers who cannot see it. Blank if decorative.")
    caption = blocks.CharBlock(required=False, max_length=250)

    class Meta:
        icon = "image"
        template = "conferences/blocks/image.html"


class ProgrammeBlock(blocks.StructBlock):
    """The programme, from Conferences → Programmes. Shown once it is not hidden."""

    part = blocks.ChoiceBlock(
        required=False, choices=[("academic", "Academic conference"), ("industry", "Industry day"),
                                 ("workshop", "Workshop day"), ("phd", "PhD summer school"), ("other", "Other parts")],
        help_text="Blank: every public part.")

    class Meta:
        icon = "date"
        label = "Programme"
        template = "conferences/blocks/programme.html"


BODY_BLOCKS = [
    ("text", blocks.RichTextBlock(features=RICH_TEXT_FEATURES)),
    ("image", ImageBlock()),
    ("button", ButtonBlock()),
    ("embed", EmbedBlock(help_text="A video or a map, by its address (YouTube, Vimeo...).", icon="media")),
    ("important_dates", blocks.StaticBlock(
        admin_text="The important dates, as entered on the conference's home page.",
        template="conferences/blocks/important_dates.html", icon="date")),
    ("tracks", blocks.StaticBlock(
        admin_text="The conference's tracks, from the IGLC's conference record.",
        template="conferences/blocks/tracks.html", icon="list-ul")),
    ("programme", ProgrammeBlock()),
]


# ---------------------------------------------------------------- shared behaviour

class ConferencePageMixin:
    """For every page of a conference site: its home page and the site's branding and menu."""

    # No approval workflow on the conference sites: the organisers publish their own pages.
    has_workflow = False

    def get_workflow(self):
        return None

    @cached_property
    def conference_home(self) -> "ConferenceHomePage | None":
        if isinstance(self.specific, ConferenceHomePage):
            return self.specific
        return ConferenceHomePage.objects.ancestor_of(self).first()

    def get_context(self, request, *args, **kwargs):
        context = super().get_context(request, *args, **kwargs)
        home = self.conference_home
        context["home"] = home
        context["conference"] = home.conference if home else None
        context["menu"] = home.get_children().live().in_menu().specific() if home else []
        context["main_site_url"] = settings.SITE_URL
        # the menu item to mark: the page itself or its ancestor just below the home page
        context["menu_current"] = None
        if home and self.depth > home.depth:
            context["menu_current"] = (self.pk if self.depth == home.depth + 1 else
                                       self.get_ancestors().filter(depth=home.depth + 1).values_list("pk", flat=True).first())
        return context


class ConferenceIndexPage(Page):
    """The root of the conference sites. Its address serves the current conference."""

    intro = models.TextField(blank=True, help_text="Shown when no conference is marked as current.")

    content_panels = Page.content_panels + [FieldPanel("intro")]
    parent_page_types = ["wagtailcore.Page"]
    subpage_types = ["conferences.ConferenceHomePage"]
    max_count = 1
    template = "conferences/index_page.html"
    has_workflow = False  # new conference home pages are published by the IGLC directly

    def get_workflow(self):
        return None

    class Meta:
        verbose_name = "conference sites (root)"

    def current_home(self):
        return (ConferenceHomePage.objects.child_of(self).live().filter(is_current=True)
                .select_related("conference").first())

    def route(self, request, path_components):
        # /call-for-papers/ -> /2027/call-for-papers/ for the current conference
        if path_components and not self.get_children().filter(slug=path_components[0]).exists():
            current = self.current_home()
            if current:
                return RouteResult(self, kwargs={"redirect_to": current.get_url(request) + "/".join(path_components) + "/"})
        return super().route(request, path_components)

    def serve(self, request, *args, redirect_to=None, **kwargs):
        if redirect_to:
            return HttpResponseRedirect(redirect_to)
        current = self.current_home()
        if current:
            return current.serve(request)
        return super().serve(request, *args, **kwargs)

    def get_context(self, request, *args, **kwargs):
        context = super().get_context(request, *args, **kwargs)
        context["homes"] = (ConferenceHomePage.objects.child_of(self).live().select_related("conference")
                            .order_by("-conference__number"))
        context["main_site_url"] = settings.SITE_URL
        return context


class ConferenceHomePage(ConferencePageMixin, Page):
    conference = models.OneToOneField(
        "archive.Conference", on_delete=models.PROTECT, related_name="site_home",
        help_text="The IGLC's record of the conference: number, dates, city and tracks come from it.")
    is_current = models.BooleanField(
        "current conference", default=False,
        help_text="Served at the site's main address. Marking one conference as current unmarks the others.")
    frozen = models.BooleanField(
        default=False, help_text="After the conference: the pages can no longer be edited by the organisers, "
                                 "and the site says that the conference has taken place.")
    tagline = models.CharField(max_length=200, blank=True, help_text="The conference theme, if there is one.")
    intro = RichTextField(features=["bold", "italic", "link"], blank=True)
    logo = models.ForeignKey(IMAGE, null=True, blank=True, on_delete=models.SET_NULL, related_name="+",
                             help_text="The conference logo, shown in the header (about 60 pixels high).")
    hero_image = models.ForeignKey(IMAGE, null=True, blank=True, on_delete=models.SET_NULL, related_name="+",
                                   help_text="A wide photograph for the top of the home page (at least 1600 "
                                             "pixels wide).")
    primary_colour = models.CharField(
        max_length=7, default="#365a91",
        help_text="Header, links and headings, as #rrggbb. White text must be readable on it.")
    accent_colour = models.CharField(max_length=7, default="#d4772a",
                                     help_text="Buttons and highlights, as #rrggbb.")
    heading_font = models.CharField(max_length=20, default="serif",
                                    choices=[(k, v[1]) for k, v in HEADING_FONTS.items()])
    registration_url = models.URLField(blank=True, help_text="The registration system. Shown as a button in the header.")
    contact_email = models.EmailField(blank=True)
    body = StreamField(BODY_BLOCKS, blank=True)

    content_panels = Page.content_panels + [
        FieldPanel("tagline"),
        FieldPanel("intro"),
        FieldPanel("body"),
        InlinePanel("important_dates", label="Important dates", heading="Important dates",
                    help_text="Deadlines and the conference days. Shown on the home page and wherever a page "
                              "has an 'important dates' block."),
        MultiFieldPanel([FieldPanel("registration_url"), FieldPanel("contact_email")], heading="Links"),
    ]
    branding_panels = [
        HelpPanel("<p>The site keeps the IGLC layout; these set its logo, picture, colours and heading font. "
                  "Colours are checked for contrast so that the text stays readable.</p>"),
        FieldPanel("logo"),
        FieldPanel("hero_image"),
        FieldPanel("primary_colour"),
        FieldPanel("accent_colour"),
        FieldPanel("heading_font"),
    ]
    settings_panels = [
        FieldPanel("conference", permission="superuser"),
        FieldPanel("is_current", permission="superuser"),
        FieldPanel("frozen", permission="superuser"),
    ] + Page.settings_panels

    # The branding fields are edited on the conference's Branding page in the back office
    # (/manage/<number>/branding/, apps/conferences/workspace_views.py), not in the page editor.
    edit_handler = TabbedInterface([
        ObjectList([HelpPanel("<p>The logo, colours, photograph and heading font are under <strong>Branding</strong> "
                              "in the menu.</p>")] + content_panels, heading="Content"),
        ObjectList(Page.promote_panels, heading="Promote"),
        ObjectList(settings_panels, heading="Settings"),
    ])

    parent_page_types = ["conferences.ConferenceIndexPage"]
    subpage_types = ["conferences.ConferencePage", "conferences.KeynotesPage", "conferences.CommitteesPage",
                     "conferences.SponsorsPage", "conferences.AcceptedPapersPage"]
    template = "conferences/home_page.html"

    class Meta:
        verbose_name = "conference home page"

    def clean(self):
        super().clean()
        errors = {}
        for field in ("primary_colour", "accent_colour"):
            value = getattr(self, field)
            if not HEX.match(value or ""):
                errors[field] = "Give the colour as # and six hexadecimal digits, e.g. #365a91."
        if "primary_colour" not in errors and contrast(self.primary_colour, "#ffffff") < 4.5:
            errors["primary_colour"] = (f"White text on this colour is hard to read (contrast "
                                        f"{contrast(self.primary_colour, '#ffffff'):.1f}:1; at least 4.5:1 is "
                                        f"needed). Choose a darker colour.")
        if self.conference_id:
            if not self.conference.start_date:
                errors["conference"] = "The conference needs its dates first (its year is the site's address)."
            else:
                self.slug = str(self.conference.start_date.year)
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self.is_current:
            ConferenceHomePage.objects.exclude(pk=self.pk).filter(is_current=True).update(is_current=False)

    # --- for the templates

    @property
    def short_name(self):
        return f"IGLC {self.conference.number}"

    @property
    def ordinal(self):
        n = self.conference.number
        suffix = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
        return f"{n}{suffix}"

    @property
    def colours(self) -> dict:
        return {
            "primary": self.primary_colour,
            "accent": self.accent_colour,
            "on_accent": text_on(self.accent_colour),
            # the accent as a text colour on white only when it is readable, else the primary
            "accent_text": self.accent_colour if contrast(self.accent_colour, "#ffffff") >= 4.5 else self.primary_colour,
            "heading_font": HEADING_FONTS.get(self.heading_font, HEADING_FONTS["serif"])[0],
        }

    def tracks(self):
        return self.conference.tracks.all()


class ImportantDate(Orderable):
    page = ParentalKey(ConferenceHomePage, on_delete=models.CASCADE, related_name="important_dates")
    label = models.CharField(max_length=200, help_text="For example 'Full papers due'.")
    date = models.DateField()
    end_date = models.DateField(null=True, blank=True, help_text="For a period, e.g. the conference days.")
    original_date = models.DateField(
        null=True, blank=True, help_text="If the deadline was extended: the old date, shown struck through.")
    note = models.CharField(max_length=200, blank=True)

    panels = [FieldPanel("label"), FieldPanel("date"), FieldPanel("end_date"), FieldPanel("original_date"),
              FieldPanel("note")]

    class Meta(Orderable.Meta):
        verbose_name = "important date"

    @property
    def is_past(self):
        from datetime import date

        return (self.end_date or self.date) < date.today()


class ConferencePage(ConferencePageMixin, Page):
    """Call for papers, venue and travel, registration, programme, and any other page."""

    intro = models.TextField(blank=True, help_text="One or two sentences shown under the title.")
    body = StreamField(BODY_BLOCKS, blank=True)

    content_panels = Page.content_panels + [FieldPanel("intro"), FieldPanel("body")]
    parent_page_types = ["conferences.ConferenceHomePage", "conferences.ConferencePage"]
    subpage_types = ["conferences.ConferencePage"]
    template = "conferences/conference_page.html"

    class Meta:
        verbose_name = "conference page"


class KeynotesPage(ConferencePageMixin, Page):
    intro = models.TextField(blank=True)

    content_panels = Page.content_panels + [FieldPanel("intro"), InlinePanel("keynotes", label="Speaker")]
    parent_page_types = ["conferences.ConferenceHomePage"]
    subpage_types = []
    template = "conferences/keynotes_page.html"

    class Meta:
        verbose_name = "keynotes page"


class Keynote(Orderable):
    page = ParentalKey(KeynotesPage, on_delete=models.CASCADE, related_name="keynotes")
    name = models.CharField(max_length=200)
    affiliation = models.CharField(max_length=300, blank=True)
    photo = models.ForeignKey(IMAGE, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    talk_title = models.CharField(max_length=300, blank=True)
    biography = RichTextField(features=["bold", "italic", "link"], blank=True)
    url = models.URLField("profile page", blank=True)


class CommitteesPage(ConferencePageMixin, Page):
    intro = models.TextField(blank=True)
    show_editors = models.BooleanField(
        "show the proceedings editors", default=True,
        help_text="List the editors from the IGLC's conference record as 'Proceedings editors'.")

    content_panels = Page.content_panels + [
        FieldPanel("intro"), FieldPanel("show_editors"),
        InlinePanel("members", label="Member",
                    help_text="Members are listed under their committee's name, in the order given here."),
    ]
    parent_page_types = ["conferences.ConferenceHomePage"]
    subpage_types = []
    template = "conferences/committees_page.html"

    class Meta:
        verbose_name = "committees page"

    def groups(self):
        grouped: dict[str, list] = {}
        for member in self.members.all():
            grouped.setdefault(member.committee, []).append(member)
        return list(grouped.items())


class CommitteeMember(Orderable):
    page = ParentalKey(CommitteesPage, on_delete=models.CASCADE, related_name="members")
    committee = models.CharField(max_length=120, help_text="For example 'Organising committee' or "
                                                           "'Scientific committee'.")
    name = models.CharField(max_length=200)
    role = models.CharField(max_length=120, blank=True, help_text="For example 'Chair'.")
    affiliation = models.CharField(max_length=300, blank=True)
    country = models.CharField(max_length=100, blank=True)
    person = models.ForeignKey("archive.AuthorPerson", null=True, blank=True, on_delete=models.SET_NULL,
                               related_name="+", help_text="Links the name to the person's author page.")

    panels = [FieldPanel("committee"), FieldPanel("name"), FieldPanel("role"), FieldPanel("affiliation"),
              FieldPanel("country"), FieldPanel("person")]


class SponsorsPage(ConferencePageMixin, Page):
    intro = models.TextField(blank=True)
    body = StreamField(BODY_BLOCKS, blank=True, help_text="For example how to become a sponsor.")

    content_panels = Page.content_panels + [FieldPanel("intro"), InlinePanel("sponsors", label="Sponsor"),
                                            FieldPanel("body")]
    parent_page_types = ["conferences.ConferenceHomePage"]
    subpage_types = []
    template = "conferences/sponsors_page.html"

    class Meta:
        verbose_name = "sponsors page"

    def levels(self):
        grouped: dict[str, list] = {}
        for sponsor in self.sponsors.all():
            grouped.setdefault(sponsor.level, []).append(sponsor)
        return list(grouped.items())


class Sponsor(Orderable):
    page = ParentalKey(SponsorsPage, on_delete=models.CASCADE, related_name="sponsors")
    name = models.CharField(max_length=200)
    level = models.CharField(max_length=60, blank=True, help_text="For example 'Gold'. Sponsors are grouped by it.")
    logo = models.ForeignKey(IMAGE, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    url = models.URLField(blank=True)


class AcceptedPapersPage(ConferencePageMixin, Page):
    """The accepted papers, from the proceedings production (and, once published, the archive)."""

    intro = models.TextField(blank=True)

    content_panels = Page.content_panels + [
        FieldPanel("intro"),
        HelpPanel("<p>The list comes from the papers the IGLC has received from ConfTool for the "
                  "proceedings. Once the proceedings are published, the titles link to the papers.</p>"),
    ]
    parent_page_types = ["conferences.ConferenceHomePage"]
    subpage_types = []
    max_count_per_parent = 1
    template = "conferences/accepted_papers_page.html"

    class Meta:
        verbose_name = "accepted papers page"

    def papers(self):
        """[(track or None, [{"title", "authors", "url"}])] in track order."""
        conference = self.conference_home.conference
        rows = []
        from apps.archive.models import Paper
        from apps.production.models import Submission

        published = conference.is_published
        if published:
            for paper in (Paper.objects.filter(conference=conference).select_related("track").prefetch_related("authors")
                          .order_by("track__order", "first_page", "title")):
                rows.append((paper.track, {"title": paper.title, "authors": paper.full_author_string(),
                                           "url": paper.get_absolute_url()}))
        else:
            submissions = (Submission.objects.filter(production__conference=conference)
                           .exclude(status=Submission.Status.WITHDRAWN).select_related("track", "paper")
                           .order_by("track__order", "position", "title"))
            for s in submissions:
                authors = ", ".join(a.get("name", "") for a in s.registered_authors if a.get("name"))
                rows.append((s.track, {"title": s.title, "authors": authors, "url": ""}))
        grouped: list = []
        for track, row in rows:
            if not grouped or grouped[-1][0] != track:
                grouped.append((track, []))
            grouped[-1][1].append(row)
        return grouped, published


# ---------------------------------------------------------------- the standard pages of a new site

class StandardPageTemplate(models.Model):
    """One of the pages every new conference website starts with (as a draft). Edited by the
    IGLC in the back office (Conferences → Website standard pages); changes apply to sites
    created afterwards, not to existing ones."""

    PAGE_TYPES = [
        ("ConferencePage", "Ordinary page (text, pictures, buttons, dates, tracks)"),
        ("KeynotesPage", "Keynotes (a list of speakers)"),
        ("CommitteesPage", "Committees (a list of members)"),
        ("SponsorsPage", "Sponsors (logos by level, and text)"),
        ("AcceptedPapersPage", "Accepted papers (listed automatically)"),
    ]
    WITH_BODY = {"ConferencePage", "SponsorsPage"}

    page_type = models.CharField(max_length=40, choices=PAGE_TYPES, default="ConferencePage")
    title = models.CharField(max_length=255)
    slug = models.SlugField(max_length=100, unique=True,
                            help_text="The last part of the address, e.g. call-for-papers → /2027/call-for-papers/.")
    intro = models.TextField(blank=True, help_text="One or two sentences shown under the title.")
    body = StreamField(BODY_BLOCKS, blank=True,
                       help_text="The starting text. Only ordinary pages and the sponsors page have one.")
    show_in_menus = models.BooleanField("show in the menu", default=True)
    active = models.BooleanField(default=True, help_text="Untick to stop adding this page to new sites.")
    sort_order = models.PositiveIntegerField(default=0, help_text="Position in the menu.")

    panels = [
        FieldPanel("page_type"),
        FieldPanel("title"),
        FieldPanel("slug"),
        FieldPanel("intro"),
        FieldPanel("body"),
        FieldPanel("show_in_menus"),
        FieldPanel("active"),
    ]

    class Meta:
        ordering = ["sort_order", "pk"]
        verbose_name = "conference standard page"

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        if self._state.adding and not self.sort_order:  # a new page goes last
            last = StandardPageTemplate.objects.aggregate(models.Max("sort_order"))["sort_order__max"]
            self.sort_order = 0 if last is None else last + 1
        super().save(*args, **kwargs)

    def clean(self):
        super().clean()
        errors = {}
        if self.slug and self.slug.isdigit():
            errors["slug"] = "A number is not allowed: numbers are the conference years."
        if (self.page_type == "AcceptedPapersPage" and StandardPageTemplate.objects
                .filter(page_type="AcceptedPapersPage").exclude(pk=self.pk).exists()):
            errors["page_type"] = "There is already an accepted papers page: a site can have only one."
        if self.page_type not in self.WITH_BODY and self.body and len(self.body):
            errors["body"] = "This kind of page has no text of its own: leave it empty."
        if errors:
            raise ValidationError(errors)
