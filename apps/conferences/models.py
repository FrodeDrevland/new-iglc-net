"""Conference websites: one small site per conference, at conference.iglc.net/<year>/.

The pages live in their own Wagtail Site (the host name is the setting CONFERENCE_HOST):

    ConferenceIndexPage          conference.iglc.net/          serves the current conference
      ConferenceHomePage         conference.iglc.net/2027/     one per conference, slug = year
        ConferencePage           call for papers, venue, registration, programme, free pages
        CommitteesPage, SponsorsPage, AcceptedPapersPage

The organisers of a conference edit and publish the pages below their home page (the site's
settings, current and frozen, stay with the IGLC). Which pages a site has, their titles, addresses and
order are the IGLC's: the organisers only edit the content (PageStructureForm). Dates, tracks and accepted papers come from the platform.
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
from wagtail.admin.forms import WagtailAdminPageForm
from wagtail.admin.panels import (FieldPanel, HelpPanel, InlinePanel, ObjectList,
                                  TabbedInterface)
from wagtail.embeds.blocks import EmbedBlock
from wagtail.fields import RichTextField, StreamField
from wagtail.images import get_image_model_string
from wagtail.images.blocks import ImageChooserBlock
from wagtail.models import Orderable, Page
from wagtail.url_routing import RouteResult

from apps.pages.models import RICH_TEXT_FEATURES

IMAGE = get_image_model_string()
HERO_SIZE = (1600, 600)  # the home page's photograph: shown 8:3 on wide screens (see conference.css)
PRIMARY_HELP = ("The header, the top of the home page and the contact band. The text on it is white or black, "
                "whichever reads better. Links and headings use it too, or a darker shade of it if it is too light "
                "for text on white.")
LOGO_HELP = ("Shown in the header of every page, on the conference's main colour, about 60 pixels high, "
             "with the place and dates next to it. Choose a version of the logo that reads well on that colour; a "
             "wide one suits the header best.")
HERO_LOGO_HELP = ("Shown large at the top of the home page, on the photograph, instead of the title. Choose a "
                  "version of the logo that reads well on your photograph. Without it, the title is shown.")
LIGHT_LOGO_HELP = ("Used where the conference is shown on a white or light background: its page in the IGLC's "
                   "proceedings archive, and link previews when the photograph is not set. Choose a version of "
                   "the logo that reads well on white.")
ICON_HELP = ("A square image, at least 512 × 512 pixels: the browser tab and the icon when someone adds the website "
             "to a phone's home screen. Without it, the IGLC symbol is used.")
DARKEN_HELP = ("A dark shade over the left part of the photograph, so that white text and logos stay readable. "
               "Turn it off if your photograph is dark enough, or if your logo reads better without it.")
HERO_HELP = ("A wide photograph for the top of the home page: 1600 × 600 pixels, or larger in the same shape "
             "(8:3, e.g. 2400 × 900). The title sits on its left side over a darkened band, and phones show "
             "only the middle, so keep what matters in the centre; the picture's focal point (under Images) "
             "decides what stays in view.")
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
    # pure black: every colour then has at least 4.5:1 with one of the two
    return "#ffffff" if contrast(background, "#ffffff") >= contrast(background, "#000000") else "#000000"


def readable_on_white(colour: str, minimum: float = 4.5) -> str:
    """The colour itself if text in it is readable on white, else a darker shade of it that is."""
    if contrast(colour, "#ffffff") >= minimum:
        return colour
    red, green, blue = (int(colour[i:i + 2], 16) for i in (1, 3, 5))
    for step in range(1, 21):
        factor = 1 - step * 0.05
        shade = "#{:02x}{:02x}{:02x}".format(round(red * factor), round(green * factor), round(blue * factor))
        if contrast(shade, "#ffffff") >= minimum:
            return shade
    return "#000000"


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


class SpeakersBlock(blocks.StructBlock):
    """The conference's speakers, entered under Speakers in the conference's workspace (Speaker)."""

    group = blocks.CharBlock(
        required=False,
        help_text="Which speakers, as grouped under Speakers (for example 'Keynote speakers'). Blank: all, "
                  "under the names of their groups.")

    class Meta:
        icon = "user"
        label = "Speakers"
        template = "conferences/blocks/speakers.html"

    def get_context(self, value, parent_context=None):
        context = super().get_context(value, parent_context)
        conference = (parent_context or {}).get("conference")
        speakers = Speaker.objects.filter(conference=conference, hidden=False) if conference else Speaker.objects.none()
        wanted = (value.get("group") or "").strip()
        if wanted:
            speakers = speakers.filter(group__iexact=wanted)
        groups: dict[str, list] = {}
        for speaker in speakers.select_related("photo"):
            groups.setdefault(speaker.group or "Speakers", []).append(speaker)
        context["groups"] = list(groups.items())
        context["show_headings"] = not wanted and len(groups) > 1
        return context


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
    ("speakers", SpeakersBlock()),
]


# ---------------------------------------------------------------- shared behaviour

class PageStructureForm(WagtailAdminPageForm):
    """The pages of a conference site follow the IGLC's standard: only superusers change a page's title,
    address or place in the menu. Everyone else edits the content."""

    STRUCTURE = ("title", "slug", "show_in_menus")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        user = getattr(self, "for_user", None)
        if self.instance.pk and user is not None and not user.is_superuser:
            for name in self.STRUCTURE:
                if name in self.fields:
                    self.fields[name].disabled = True
                    self.fields[name].help_text = "Set by the IGLC for every conference website."


class ConferencePageMixin:
    """For every page of a conference site: its home page and the site's branding and menu."""

    base_form_class = PageStructureForm

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
        # in a preview (the editor's, or View draft) the draft pages are in the menu too, so that a
        # website that is not yet published can be looked at as a whole
        children = home.get_children().in_menu() if home else None
        if home and not getattr(request, "is_preview", False):
            children = children.live()
        context["menu"] = list(children.specific()) if home else []
        context["is_preview"] = getattr(request, "is_preview", False)
        if context["is_preview"]:
            # links in a preview open the other pages' drafts (Wagtail's View draft, on the main site)
            from django.urls import reverse

            def draft_url(page):
                return settings.SITE_URL + reverse("wagtailadmin_pages:view_draft", args=[page.pk],
                                                   urlconf=settings.ROOT_URLCONF)

            for item in context["menu"]:
                item.preview_url = draft_url(item)
            context["home_preview_url"] = draft_url(home) if home else ""
        context["main_site_url"] = settings.SITE_URL
        # the menu item to mark: the page itself or its ancestor just below the home page
        context["menu_current"] = None
        if home and self.depth > home.depth:
            context["menu_current"] = (self.pk if self.depth == home.depth + 1 else
                                       self.get_ancestors().filter(depth=home.depth + 1).values_list("pk", flat=True).first())
        return context


def placeholder_conference(year: int):
    """The conference with a placeholder page at /<year>/: placeholder on, and no published website."""
    from apps.archive.models import Conference

    conference = (Conference.objects.filter(website_placeholder=True, start_date__year=year)
                  .order_by("-number").first())
    if conference is None:
        return None
    if ConferenceHomePage.objects.filter(conference=conference, live=True).exists():
        return None
    return conference


def ordinal(number: int) -> str:
    suffix = "th" if 10 <= number % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(number % 10, "th")
    return f"{number}{suffix}"


def serve_placeholder(request, conference):
    """A simple page for a conference whose website is not published yet. The logo and contact address
    come from the website's latest draft, if it has one."""
    from django.template.response import TemplateResponse

    home = ConferenceHomePage.objects.filter(conference=conference).first()
    draft = home.get_latest_revision_as_object() if home else None
    email = (draft.contact_email if draft else "") or (
        settings.CONFERENCE_CONTACT_EMAIL.format(number=conference.number) if settings.CONFERENCE_CONTACT_EMAIL else "")
    return TemplateResponse(request, "conferences/placeholder.html", {
        "conference": conference, "draft": draft, "email": email, "ordinal": ordinal(conference.number),
        "name": f"IGLC {conference.number}",
        "colours": draft.colours if draft else None, "main_site_url": settings.SITE_URL,
    })


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
        # /2027/ of a conference whose website is not published yet: its placeholder page, if it has one
        if len(path_components) == 1 and path_components[0].isdigit():
            placeholder = placeholder_conference(int(path_components[0]))
            if placeholder is not None:
                return RouteResult(self, kwargs={"placeholder": placeholder})
        # /call-for-papers/ -> /2027/call-for-papers/ for the current conference
        if path_components and not self.get_children().filter(slug=path_components[0]).exists():
            current = self.current_home()
            if current:
                return RouteResult(self, kwargs={"redirect_to": current.get_url(request) + "/".join(path_components) + "/"})
        return super().route(request, path_components)

    def serve(self, request, *args, redirect_to=None, placeholder=None, **kwargs):
        if redirect_to:
            return HttpResponseRedirect(redirect_to)
        if placeholder is not None:
            return serve_placeholder(request, placeholder)
        current = self.current_home()
        if current:
            return current.serve(request)
        # the current conference's website is not published yet: its placeholder, if it has one
        waiting = (ConferenceHomePage.objects.child_of(self).filter(is_current=True, live=False,
                                                                    conference__website_placeholder=True)
                   .select_related("conference").first())
        if waiting is not None:
            return serve_placeholder(request, waiting.conference)
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
    # The logos: each is shown on a known background, and the organisers choose a version of their logo
    # that reads well there (the platform says where, not which colours).
    logo = models.ForeignKey(IMAGE, null=True, blank=True, on_delete=models.SET_NULL, related_name="+",
                             verbose_name="logo in the header", help_text=LOGO_HELP)
    hero_logo = models.ForeignKey(IMAGE, null=True, blank=True, on_delete=models.SET_NULL, related_name="+",
                                  verbose_name="logo on the photograph", help_text=HERO_LOGO_HELP)
    logo_on_light = models.ForeignKey(IMAGE, null=True, blank=True, on_delete=models.SET_NULL, related_name="+",
                                      verbose_name="logo on light backgrounds", help_text=LIGHT_LOGO_HELP)
    icon = models.ForeignKey(IMAGE, null=True, blank=True, on_delete=models.SET_NULL, related_name="+",
                             help_text=ICON_HELP)
    hero_darken = models.BooleanField("darken the photograph", default=True, help_text=DARKEN_HELP)
    hero_image = models.ForeignKey(IMAGE, null=True, blank=True, on_delete=models.SET_NULL, related_name="+",
                                   help_text=HERO_HELP)
    primary_colour = models.CharField(
        max_length=7, default="#365a91",
        help_text=PRIMARY_HELP)
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
        ObjectList([HelpPanel("<p>The important dates, the registration link and the contact address are under "
                              "<strong>Dates and links</strong> in the menu; the logo, colours, photograph and "
                              "heading font under <strong>Branding</strong>.</p>")] + content_panels,
                   heading="Content"),
        ObjectList(Page.promote_panels, heading="Promote"),
        ObjectList(settings_panels, heading="Settings"),
    ])

    parent_page_types = ["conferences.ConferenceIndexPage"]
    subpage_types = ["conferences.ConferencePage", "conferences.CommitteesPage",
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
        return ordinal(self.conference.number)

    @property
    def colours(self) -> dict:
        return {
            "primary": self.primary_colour,
            # text on the main colour (header, top of the home page, contact band): white or black
            "on_primary": text_on(self.primary_colour),
            "light_primary": text_on(self.primary_colour) == "#000000",
            # links and headings on white: the main colour, or a darker shade of it if it is too light
            "primary_text": readable_on_white(self.primary_colour),
            "accent": self.accent_colour,
            "on_accent": text_on(self.accent_colour),
            # the accent as a text colour on white only when it is readable, else the main colour's
            "accent_text": (self.accent_colour if contrast(self.accent_colour, "#ffffff") >= 4.5
                            else readable_on_white(self.primary_colour)),
            "heading_font": HEADING_FONTS.get(self.heading_font, HEADING_FONTS["serif"])[0],
        }

    def tracks(self):
        return self.conference.tracks.all()

    @property
    def hero_position(self) -> str:
        """object-position for the photograph: its focal point, or the centre."""
        image = self.hero_image
        if image is None or image.focal_point_x is None or not image.width or not image.height:
            return "50% 50%"
        return f"{100 * image.focal_point_x / image.width:.0f}% {100 * image.focal_point_y / image.height:.0f}%"


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


class Speaker(Orderable):
    """A speaker of the conference (keynotes, industry day, panels...), entered once under Speakers in the
    conference's workspace and shown by the Speakers block; programme sessions link to them."""

    conference = models.ForeignKey("archive.Conference", on_delete=models.CASCADE, related_name="speakers")
    group = models.CharField(max_length=120, blank=True, default="Keynote speakers",
                             help_text="For example 'Keynote speakers' or 'Industry day speakers'. A Speakers block "
                                       "shows one group, or all of them.")
    name = models.CharField(max_length=200)
    affiliation = models.CharField(max_length=300, blank=True)
    photo = models.ForeignKey(IMAGE, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    talk_title = models.CharField(max_length=300, blank=True)
    biography = RichTextField(features=["bold", "italic", "link"], blank=True)
    url = models.URLField("profile page", blank=True)
    hidden = models.BooleanField("not yet announced", default=False,
                                 help_text="Kept off the website until it is unticked.")

    class Meta(Orderable.Meta):
        verbose_name = "speaker"

    def __str__(self):
        return self.name

    @property
    def initials(self):
        return "".join(part[0] for part in self.name.split()[:3] if part).upper()


class CommitteesPage(ConferencePageMixin, Page):
    LAYOUTS = [
        ("sections", "Each committee below the previous one, with large portraits"),
        ("columns", "Committees side by side, with small portraits"),
        ("compact", "Committees side by side, names only"),
    ]

    intro = models.TextField(blank=True)
    layout = models.CharField(max_length=20, choices=LAYOUTS, default="sections",
                              help_text="Side by side suits several small committees; below each other suits a few "
                                        "committees with portraits.")

    # The members are edited under Committees in the conference's menu (apps/conferences/committee_views.py).
    content_panels = Page.content_panels + [
        HelpPanel("<p>The members are added, ordered and given portraits under <strong>Committees</strong> in the "
                  "menu.</p>"),
        FieldPanel("intro"),
    ]
    parent_page_types = ["conferences.ConferenceHomePage"]
    subpage_types = []
    template = "conferences/committees_page.html"

    class Meta:
        verbose_name = "committees page"

    def groups(self):
        """[(committee, members, with_photos)]: a committee where nobody has a photograph is shown as a
        compact list rather than cards with initials."""
        grouped: dict[str, list] = {}
        for member in self.members.all():
            grouped.setdefault(member.committee, []).append(member)
        return [(name, members, any(m.photo_id for m in members)) for name, members in grouped.items()]


class CommitteeMember(Orderable):
    page = ParentalKey(CommitteesPage, on_delete=models.CASCADE, related_name="members")
    committee = models.CharField(max_length=120, help_text="For example 'Organising committee' or "
                                                           "'Scientific committee'.")
    name = models.CharField(max_length=200)
    role = models.CharField(max_length=120, blank=True, help_text="For example 'Chair'.")
    affiliation = models.CharField(max_length=300, blank=True)
    country = models.CharField(max_length=100, blank=True)
    photo = models.ForeignKey(IMAGE, null=True, blank=True, on_delete=models.SET_NULL, related_name="+",
                              help_text="A portrait, at least 400 × 400 pixels; shown round, cut to a square "
                                        "around the picture's focal point. Without one, the initials are shown.")
    url = models.URLField("profile page", blank=True,
                          help_text="The person's page at their university or company, or on LinkedIn.")
    person = models.ForeignKey("archive.AuthorPerson", null=True, blank=True, on_delete=models.SET_NULL,
                               related_name="+", help_text="The person's author page in the IGLC proceedings, if "
                                                           "they have one (used when no profile page is given).")

    panels = [FieldPanel("committee"), FieldPanel("name"), FieldPanel("role"), FieldPanel("photo"),
              FieldPanel("affiliation"), FieldPanel("country"), FieldPanel("url"), FieldPanel("person")]

    @property
    def initials(self) -> str:
        words = [w for w in self.name.replace("-", " ").split() if w[:1].isalpha()]
        return ((words[0][0] + (words[-1][0] if len(words) > 1 else "")).upper()) if words else "?"


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
        ("ConferencePage", "Ordinary page (text, pictures, buttons, dates, tracks, speakers, programme)"),
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
