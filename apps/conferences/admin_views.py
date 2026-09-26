"""Conferences in the IGLC administration: Conferences → All conferences, a list whose rows open the
conference's workspace (/manage/<number>/, apps/conferences/workspace_views.py).

The conference record is the archive's (apps.archive.models.Conference); its edit form is the one
that used to be under Archive → Conferences. The menu "Conferences" also holds the programmes,
the proceedings production and the website standard pages (register_conferences_menu_item).
"""

from __future__ import annotations

from datetime import date

import django_filters
from django.contrib import messages
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect
from django.urls import path, reverse
from wagtail.admin.filters import WagtailFilterSet
from wagtail.admin.menu import Menu, SubmenuMenuItem
from wagtail.admin.panels import FieldPanel, FieldRowPanel, HelpPanel, InlinePanel, MultiFieldPanel
from wagtail.admin.ui.tables import Column, StatusTagColumn, TitleColumn
from wagtail.admin.views.generic.models import DeleteView, IndexView
from wagtail.admin.viewsets.model import ModelViewSet

from apps.archive.admin_views import TrackedCreateView, TrackedEditView
from apps.archive.models import Conference

from . import dashboard
from .models import ConferenceHomePage

MENU_HOOK = "register_conferences_menu_item"

conferences_menu = Menu(register_hook_name=MENU_HOOK, construct_hook_name="construct_conferences_menu")


def conferences_menu_item():
    return SubmenuMenuItem("Conferences", conferences_menu, name="conferences", icon_name="date", order=190)


# ---------------------------------------------------------------- the list

class ConferenceFilterSet(WagtailFilterSet):
    when = django_filters.ChoiceFilter(
        label="When", method="filter_when", empty_label="All",
        choices=[("upcoming", "Upcoming or running"), ("past", "Past")])
    website = django_filters.ChoiceFilter(
        label="Website", method="filter_website", empty_label="All",
        choices=[(key, label) for key, label in dashboard.WEBSITE_STATES.items()])

    class Meta:
        model = Conference
        fields = ["is_published"]

    def filter_when(self, queryset, name, value):
        today = date.today()
        ended = Q(end_date__lt=today) | Q(end_date__isnull=True, start_date__lt=today)
        return queryset.filter(ended) if value == "past" else queryset.exclude(ended).exclude(start_date=None)

    def filter_website(self, queryset, name, value):
        homes = ConferenceHomePage.objects.all()
        filters = {
            "none": ~Q(pk__in=homes.values("conference_id")),
            "draft": Q(pk__in=homes.filter(live=False, frozen=False).values("conference_id")),
            "published": Q(pk__in=homes.filter(live=True, frozen=False, is_current=False).values("conference_id")),
            "current": Q(pk__in=homes.filter(live=True, frozen=False, is_current=True).values("conference_id")),
            "frozen": Q(pk__in=homes.filter(frozen=True).values("conference_id")),
        }
        return queryset.filter(filters[value]) if value in filters else queryset


def _dates(conference):
    if not conference.start_date:
        return "–"
    start, end = conference.start_date, conference.end_date
    if not end or end == start:
        return f"{start.day} {start:%b %Y}"
    if (start.year, start.month) == (end.year, end.month):
        return f"{start.day}–{end.day} {end:%b %Y}"
    return f"{start.day} {start:%b} – {end.day} {end:%b %Y}"


def _home(conference):
    try:
        return conference.site_home
    except ConferenceHomePage.DoesNotExist:
        return None


def _website(conference):
    return dashboard.WEBSITE_STATES[dashboard.website_state(_home(conference))]


def _programme(conference):
    programme = getattr(conference, "programme", None) if _has(conference, "programme") else None
    return programme.get_status_display().split(" (")[0] if programme else "–"


def _proceedings(conference):
    production = conference.production if _has(conference, "production") else None
    parts = []
    if production:
        parts.append(production.get_status_display())
    if conference.paper_count:
        parts.append(f"{conference.paper_count} papers")
    return ", ".join(parts) or "–"


def _has(conference, relation):
    try:
        return getattr(conference, relation) is not None
    except Exception:
        return False


class ConferenceIndexView(IndexView):
    """Rows open the dashboard, not the edit form."""

    def get_base_queryset(self):
        return (super().get_base_queryset()
                .select_related("site_home", "production", "programme")
                .annotate(paper_count=Count("papers", distinct=True),
                          doi_count=Count("crossref_deposits", filter=Q(crossref_deposits__test=False),
                                          distinct=True)))

    def _get_title_column(self, field_name, column_class=TitleColumn, **kwargs):
        column_class = self._get_title_column_class(column_class)
        return self._get_custom_column(
            field_name, column_class,
            get_url=lambda instance: reverse("conference:overview", args=[instance.number]), **kwargs)

    def get_list_more_buttons(self, instance):
        from wagtail.admin.ui.menus import MenuItem

        buttons = [MenuItem("Open", reverse("conference:overview", args=[instance.number]),
                            icon_name="info-circle", priority=5)]
        return buttons + [b for b in super().get_list_more_buttons(instance) if b.label != "Inspect"]


class ConferenceDeleteView(DeleteView):
    """Deleting a conference takes its website, programme and empty production with it, and is
    refused for conferences with papers, DOIs or a published or frozen website."""

    template_name = "conferences/admin/delete.html"

    def get_usage_url(self):
        return None  # deletion() below says what goes and what stops it

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["deletion"] = dashboard.deletion(self.object)
        context["dashboard_url"] = reverse("conference:overview", args=[self.object.number])
        return context

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        check = dashboard.deletion(self.object)
        if not check.allowed:
            for blocker in check.blockers:
                messages.error(request, blocker)
            return redirect("conference:overview", self.object.number)
        return super().post(request, *args, **kwargs)

    def delete_action(self):
        dashboard.delete_conference(self.object, self.request.user)


class ConferenceViewSet(ModelViewSet):
    model = Conference
    menu_label = "All conferences"
    menu_name = "all-conferences"
    icon = "date"
    menu_order = 1
    pk_path_converter = "int"
    index_view_class = ConferenceIndexView
    add_view_class = TrackedCreateView
    edit_view_class = TrackedEditView
    delete_view_class = ConferenceDeleteView
    filterset_class = ConferenceFilterSet
    search_fields = ["city", "country", "conference_title", "proceedings_title"]
    ordering = ["-number"]
    inspect_view_enabled = False
    list_display = [
        "__str__",
        Column("dates", label="Dates", accessor=_dates, sort_key="start_date"),
        Column("when", label="When", accessor=lambda c: dashboard.when(c).capitalize() or "–"),
        StatusTagColumn("website", label="Website", accessor=_website,
                        primary=lambda c: dashboard.website_state(_home(c)) in ("published", "current")),
        Column("programme", label="Programme", accessor=_programme),
        Column("proceedings", label="Proceedings", accessor=_proceedings),
        Column("is_published", label="In the archive", accessor=lambda c: "Yes" if c.is_published else "No",
               sort_key="is_published"),
        Column("dois", label="DOI deposits", accessor=lambda c: c.doi_count or "–"),
    ]
    panels = [
        MultiFieldPanel([
            FieldRowPanel([FieldPanel("number"), FieldPanel("start_date"), FieldPanel("end_date")]),
            FieldRowPanel([FieldPanel("city"), FieldPanel("country")]),
            FieldPanel("is_published"),
            FieldPanel("website_placeholder"),
        ], heading="Conference"),
        MultiFieldPanel([
            FieldPanel("conference_title"), FieldPanel("proceedings_title"),
            FieldRowPanel([FieldPanel("publisher"), FieldPanel("publication_location"), FieldPanel("issn")]),
        ], heading="Proceedings"),
        HelpPanel(template="archive/admin/conference_files.html", heading="Files"),
        InlinePanel("editors", heading="Editors", label="Editor",
                    panels=[FieldRowPanel([FieldPanel("first_name"), FieldPanel("last_name"), FieldPanel("order")]),
                            FieldPanel("title_and_contact")]),
        InlinePanel("tracks", heading="Tracks", label="Track",
                    panels=[FieldRowPanel([FieldPanel("title"), FieldPanel("order")]), FieldPanel("description")]),
        InlinePanel("volumes", heading="Volumes (printed books)", label="Volume",
                    panels=[FieldRowPanel([FieldPanel("number"), FieldPanel("first_page"), FieldPanel("last_page"),
                                           FieldPanel("isbn")])]),
    ]

    @property
    def menu_hook(self):
        return MENU_HOOK

    def get_urlpatterns(self):
        return super().get_urlpatterns() + [
            path("<int:pk>/", old_dashboard, name="dashboard"),
            path("<int:pk>/do/<slug:action>/", old_dashboard, name="action"),
        ]



# ---------------------------------------------------------------- old addresses

def old_dashboard(request, pk, action=None):
    """/manage/conferences/<pk>/ was the dashboard until the conference workspace (/manage/<number>/)."""
    conference = get_object_or_404(Conference, pk=pk)
    return redirect("conference:overview", conference.number)
