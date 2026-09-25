"""Conferences in the back office: Conferences → All conferences, a list whose rows open a dashboard
per conference, with the actions on it (apps/conferences/dashboard.py).

The conference record is the archive's (apps.archive.models.Conference); its edit form is the one
that used to be under Archive → Conferences. The menu "Conferences" also holds the programmes,
the proceedings production and the website standard pages (register_conferences_menu_item).
"""

from __future__ import annotations

from datetime import date

import django_filters
from django import forms
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
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
            get_url=lambda instance: reverse(self.dashboard_url_name, args=[instance.pk]), **kwargs)

    def get_list_more_buttons(self, instance):
        from wagtail.admin.ui.menus import MenuItem

        buttons = [MenuItem("Dashboard", reverse(self.dashboard_url_name, args=[instance.pk]),
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
        context["dashboard_url"] = reverse("conferences:dashboard", args=[self.object.pk])
        return context

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        check = dashboard.deletion(self.object)
        if not check.allowed:
            for blocker in check.blockers:
                messages.error(request, blocker)
            return redirect("conferences:dashboard", self.object.pk)
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
            path("<int:pk>/", dashboard_view, name="dashboard"),
            path("<int:pk>/do/<slug:action>/", action_view, name="action"),
        ]


ConferenceIndexView.dashboard_url_name = "conferences:dashboard"


# ---------------------------------------------------------------- the dashboard

def _may_view(user):
    return user.is_superuser or user.has_perm("archive.change_conference") or user.has_perm("archive.view_conference")


def dashboard_view(request, pk):
    if not _may_view(request.user):
        raise PermissionDenied
    conference = get_object_or_404(Conference, pk=pk)
    context = dashboard.overview(conference)
    context.update({
        "can_act": request.user.is_superuser,
        "can_edit": request.user.is_superuser or request.user.has_perm("archive.change_conference"),
        "activity": dashboard.recent_activity(conference, context["home"]),
        "add_form": AddOrganiserForm(conference=conference),
        "invite_form": InviteForm(),
        "today": date.today(),
    })
    return render(request, "conferences/admin/dashboard.html", context)


# ---------------------------------------------------------------- actions

class AddOrganiserForm(forms.Form):
    user = forms.ModelChoiceField(queryset=None, label="Account",
                                  help_text="An account that already exists on the site.")

    def __init__(self, *args, conference=None, **kwargs):
        super().__init__(*args, **kwargs)
        users = get_user_model().objects.filter(is_active=True).order_by("last_name", "first_name", "username")
        if conference is not None:
            users = users.exclude(groups__name=dashboard.organiser_group_name(conference))
        self.fields["user"].queryset = users
        self.fields["user"].label_from_instance = lambda u: (f"{u.get_full_name()} ({u.email or u.username})"
                                                            if u.get_full_name() else (u.email or u.username))


class InviteForm(forms.Form):
    first_name = forms.CharField(max_length=150)
    last_name = forms.CharField(max_length=150)
    email = forms.EmailField(label="E-mail address")


class TimeZoneForm(forms.Form):
    time_zone = forms.CharField(initial="Europe/Berlin",
                                help_text="Where the conference takes place, as Region/City, e.g. Europe/Berlin.")

    def clean_time_zone(self):
        from apps.programme.models import validate_time_zone

        value = self.cleaned_data["time_zone"].strip()
        validate_time_zone(value)
        return value


# Each action: (title of the confirmation page, explanation, button label). Actions not listed here
# (the organiser forms) are posted straight from the dashboard.
CONFIRM = {
    "create-website": (
        "Create the website",
        "Creates the home page at /{year}/ with the standard pages (Conferences → Website standard pages) below it, "
        "all as drafts, the conference days as the first important date, the group {group} and the "
        "collection IGLC {number} for its pictures and documents. Nothing is public until it is published.",
        "Create the website"),
    "publish-website": (
        "Publish the website",
        "Publishes the pages ticked below (their latest drafts). They are public at once.",
        "Publish"),
    "unpublish-website": (
        "Unpublish the website",
        "Takes the home page and every page below it off the public site. The drafts stay, and the organisers "
        "can still edit them.",
        "Unpublish"),
    "make-current": (
        "Mark as the current conference",
        "The conference.{host} address then shows this conference, and short addresses such as /call-for-papers/ "
        "lead to its pages.{others} It shows only while the website is published.",
        "Mark as current"),
    "unmake-current": (
        "No longer the current conference",
        "The site's main address then lists the conference websites instead.",
        "Unmark"),
    "freeze": (
        "Freeze the website",
        "For after the conference: the organisers can no longer change anything, and the site says that the "
        "conference has taken place and links to its proceedings.",
        "Freeze"),
    "unfreeze": (
        "Unfreeze the website",
        "The organisers can edit the pages again.",
        "Unfreeze"),
    "show-in-archive": (
        "Show the proceedings in the archive",
        "Lists the conference and its {papers} papers in the public archive, the search and the exports. "
        "Publishing through Proceedings production does this by itself; use this for conferences without a "
        "production.",
        "Show in the archive"),
    "hide-in-archive": (
        "Hide the proceedings from the archive",
        "Takes the conference out of the archive's lists, the search and the exports. Paper pages stay "
        "reachable, so that DOIs keep working.",
        "Hide"),
    "start-programme": (
        "Start the programme",
        "Creates the programme with the usual parts (academic conference, industry day, workshop day, PhD "
        "summer school), hidden until it is ready, and a group of editors for each part.",
        "Start the programme"),
}


def action_view(request, pk, action):
    if not request.user.is_superuser:
        raise PermissionDenied
    conference = get_object_or_404(Conference, pk=pk)
    home = dashboard.home_of(conference)
    back = redirect("conferences:dashboard", conference.pk)

    if action in ("add-organiser", "remove-organiser", "invite-organiser"):
        if request.method != "POST":
            return back
        return _organiser_action(request, conference, action) or back
    if action not in CONFIRM:
        raise PermissionDenied

    problem = _precondition(conference, home, action)
    if problem:
        messages.error(request, problem)
        return back

    form = TimeZoneForm(request.POST or None) if action == "start-programme" else None
    pages = dashboard.publishable(home) if action == "publish-website" else []
    if request.method == "POST" and (form is None or form.is_valid()):
        message = _do(request, conference, home, action, pages, form)
        if message:
            messages.success(request, message)
        return back

    title, text, button = CONFIRM[action]
    others = ConferenceHomePage.objects.filter(is_current=True).exclude(conference=conference).first()
    from django.conf import settings

    text = text.format(year=conference.year, number=conference.number,
                       group=dashboard.organiser_group_name(conference),
                       host=settings.CONFERENCE_HOST.removeprefix("conference."),
                       papers=conference.papers.count(),
                       others=f" {others.short_name} is no longer the current conference." if others else "")
    return render(request, "conferences/admin/confirm.html", {
        "conference": conference, "title": title, "text": text, "button": button, "action": action,
        "pages": pages, "form": form, "home": home,
        "danger": action in ("unpublish-website", "hide-in-archive", "freeze"),
    })


def _precondition(conference, home, action) -> str:
    if action == "create-website":
        if home:
            return "The conference already has a website."
        if not conference.start_date:
            return "The conference needs its dates first (Edit details): the year is the website's address."
        if ConferenceHomePage.objects.filter(slug=str(conference.year)).exists():
            return f"Another conference already has a website at /{conference.year}/."
        return ""
    if action == "start-programme":
        if dashboard._has(conference, "programme"):
            return "The conference already has a programme."
        if not conference.start_date:
            return "The conference needs its dates first (Edit details)."
        return ""
    if action in ("show-in-archive", "hide-in-archive"):
        return ""
    if home is None:
        return "The conference has no website yet."
    if action == "publish-website" and not dashboard.publishable(home):
        return "Everything is published already."
    if home.frozen and action not in ("unfreeze", "make-current", "unmake-current"):
        return "The website is frozen. Unfreeze it first."
    return ""


def _do(request, conference, home, action, pages, form) -> str:
    user = request.user
    if action == "create-website":
        from .setup import seed, sync_site

        sync_site()
        home = seed(conference)
        return f"The website {home.title} was created, as drafts. Its pages are listed below."
    if action == "publish-website":
        chosen = {int(pk) for pk in request.POST.getlist("page")}
        selected = [page for page in pages if page.pk in chosen]
        # a page cannot be public under an unpublished parent
        if selected and not home.live and home.pk not in chosen:
            selected.append(home)
        if not selected:
            messages.warning(request, "No pages were ticked, so nothing was published.")
            return ""
        done = dashboard.publish_pages(selected, user)
        return f"Published {len(done)} page{'s' if len(done) != 1 else ''}."
    if action == "unpublish-website":
        dashboard.unpublish_website(home, user)
        return "The website is no longer public."
    if action in ("make-current", "unmake-current"):
        dashboard.set_home_flags(home, is_current=action == "make-current")
        return (f"{home.short_name} is now the current conference." if action == "make-current"
                else f"{home.short_name} is no longer the current conference.")
    if action in ("freeze", "unfreeze"):
        dashboard.set_home_flags(home, frozen=action == "freeze")
        return "The website is frozen." if action == "freeze" else "The website can be edited again."
    if action in ("show-in-archive", "hide-in-archive"):
        conference.is_published = action == "show-in-archive"
        conference.save(update_fields=["is_published"])
        return ("The proceedings are shown in the archive." if conference.is_published
                else "The proceedings are hidden from the archive.")
    if action == "start-programme":
        from apps.programme import setup as programme_setup

        programme = programme_setup.start(conference, form.cleaned_data["time_zone"])
        return f"{programme} started, hidden until it is ready. Add people to its groups below."
    return ""


def _organiser_action(request, conference, action):
    User = get_user_model()
    if action == "add-organiser":
        form = AddOrganiserForm(request.POST, conference=conference)
        if form.is_valid():
            dashboard.add_organiser(conference, form.cleaned_data["user"])
            messages.success(request, f"{form.cleaned_data['user']} is now an organiser.")
        else:
            messages.error(request, "Choose an account.")
    elif action == "remove-organiser":
        user = User.objects.filter(pk=request.POST.get("user")).first()
        if user:
            dashboard.remove_organiser(conference, user)
            messages.success(request, f"{user} is no longer an organiser.")
    elif action == "invite-organiser":
        form = InviteForm(request.POST)
        if not form.is_valid():
            messages.error(request, "Give the first name, the last name and a valid e-mail address.")
        else:
            try:
                user = dashboard.invite_organiser(request, conference, **form.cleaned_data)
            except ValueError as error:
                messages.error(request, str(error))
            else:
                messages.success(request, f"An account for {user.email} was made, and an e-mail was sent with a "
                                          f"link to choose a password.")
    return None
