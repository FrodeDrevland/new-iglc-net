"""The conference workspace's pages: /manage/<number>/ (Overview), website/, branding/, people/ and the
actions in do/<action>/, each with a confirmation page. The sidebar for them is in workspace.py; who
may do what in roles.py; the data in dashboard.py."""

from __future__ import annotations

from datetime import date

from django import forms
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import path

from apps.archive.models import Conference

from . import dashboard, roles
from .models import HEADING_FONTS, ConferenceHomePage

app_name = "conference"


# ---------------------------------------------------------------- the pages

def _context(request, number, need=None):
    """The conference and what this person may do in it. need: "website" for the website and branding
    pages (chairs, organisers and the IGLC)."""
    conference = get_object_or_404(Conference, number=number)
    user = request.user
    if not roles.can_view(user, conference):
        raise PermissionDenied
    mine = roles.roles_of(user, conference)
    can_edit_record = user.is_superuser or user.has_perm("archive.change_conference")
    if need == "website" and not (mine & {"iglc", "chair", "organiser"} or can_edit_record):
        raise PermissionDenied
    context = dashboard.overview(conference)
    from apps.production.access import productions_for
    from apps.programme.access import programmes_for

    context.update({
        "roles": mine,
        "is_iglc": "iglc" in mine,
        "can_edit": can_edit_record,
        "can_publish": roles.can_publish(user, conference),
        "can_start_programme": bool(mine & {"iglc", "chair"}),
        "can_programme": context["programme"] is not None and programmes_for(user)
                         .filter(pk=context["programme"].pk).exists(),
        "can_production": context["production"] is not None and productions_for(user)
                          .filter(pk=context["production"].pk).exists(),
        "today": date.today(),
    })
    return conference, context


def overview(request, number):
    conference, context = _context(request, number)
    context.update({"tab": "overview", "activity": dashboard.recent_activity(conference, context["home"]),
                    "people": dashboard.people(conference, request.user)})
    return render(request, "conferences/admin/overview.html", context)


def website(request, number):
    conference, context = _context(request, number, need="website")
    context["tab"] = "website"
    return render(request, "conferences/admin/website.html", context)


def people(request, number):
    conference, context = _context(request, number)
    context.update({"tab": "people", "people": dashboard.people(conference, request.user)})
    return render(request, "conferences/admin/people.html", context)


class BrandingForm(forms.Form):
    logo = forms.ModelChoiceField(queryset=None, required=False,
                                  help_text="The conference logo, shown in the header (about 60 pixels high).")
    hero_image = forms.ModelChoiceField(queryset=None, required=False, label="Photograph",
                                        help_text="A wide photograph for the top of the home page (at least 1600 "
                                                  "pixels wide).")
    primary_colour = forms.CharField(max_length=7, widget=forms.TextInput(attrs={"type": "color"}),
                                     help_text="Header, links and headings. White text must be readable on it.")
    accent_colour = forms.CharField(max_length=7, widget=forms.TextInput(attrs={"type": "color"}),
                                    help_text="Buttons and highlights.")
    heading_font = forms.ChoiceField(choices=[(key, value[1]) for key, value in HEADING_FONTS.items()])

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from wagtail.images import get_image_model
        from wagtail.images.widgets import AdminImageChooser

        for name in ("logo", "hero_image"):
            self.fields[name].queryset = get_image_model().objects.all()
            self.fields[name].widget = AdminImageChooser()


BRANDING_FIELDS = ("logo", "hero_image", "primary_colour", "accent_colour", "heading_font")


def branding(request, number):
    """The home page's Branding tab as a page of its own. Saving makes a new draft of the home page
    with only these fields changed; "Save and publish" publishes it."""
    conference, context = _context(request, number, need="website")
    home = context["home"]
    if home is None:
        messages.info(request, "The conference has no website yet.")
        return redirect("conference:website", number)
    draft = home.get_latest_revision_as_object()
    other_changes = home.has_unpublished_changes and home.live
    frozen = home.frozen and not request.user.is_superuser
    initial = {name: getattr(draft, name) for name in BRANDING_FIELDS}
    form = BrandingForm(request.POST or None, initial=initial)
    if request.method == "POST" and not frozen and form.is_valid():
        for name in BRANDING_FIELDS:
            setattr(draft, name, form.cleaned_data[name])
        try:
            draft.clean()
        except ValidationError as error:
            for field, errors in error.message_dict.items():
                form.add_error(field if field in form.fields else None, errors)
        else:
            revision = draft.save_revision(user=request.user, log_action=True)
            if "publish" in request.POST and roles.can_publish(request.user, conference):
                revision.publish(user=request.user)
                messages.success(request, "The branding is saved and published.")
            else:
                messages.success(request, "The branding is saved as a draft of the home page. Publish it to show "
                                          "it on the website.")
            return redirect("conference:branding", number)
    context.update({"tab": "branding", "form": form, "other_changes": other_changes, "frozen": frozen,
                    "draft": draft})
    return render(request, "conferences/admin/branding.html", context)


# ---------------------------------------------------------------- actions

class PersonForm(forms.Form):
    email = forms.EmailField(label="E-mail address")
    first_name = forms.CharField(max_length=150, required=False)
    last_name = forms.CharField(max_length=150, required=False)


class TimeZoneForm(forms.Form):
    time_zone = forms.CharField(initial="Europe/Berlin",
                                help_text="Where the conference takes place, as Region/City, e.g. Europe/Berlin.")

    def clean_time_zone(self):
        from apps.programme.models import validate_time_zone

        value = self.cleaned_data["time_zone"].strip()
        validate_time_zone(value)
        return value


IGLC_ONLY = {"create-website", "make-current", "unmake-current", "freeze", "unfreeze", "show-in-archive",
             "hide-in-archive"}


def _allowed(user, conference, action) -> bool:
    mine = roles.roles_of(user, conference)
    if "iglc" in mine:
        return True
    if action in IGLC_ONLY:
        return False
    if action == "start-programme":
        return "chair" in mine
    if action in ("publish-website", "unpublish-website"):
        return roles.can_publish(user, conference)
    return False


# Each action: (title of the confirmation page, explanation, button label). Actions not listed here
# (the organiser forms) are posted straight from the dashboard.
CONFIRM = {
    "create-website": (
        "Create the website",
        "Creates the home page at /{year}/ with the standard pages (IGLC administration → Conferences → Website "
        "standard pages) below it, "
        "all as drafts, the conference days as the first important date, the roles conference chairs and "
        "website organisers (who edit and publish the website) and the collection IGLC {number} for its pictures "
        "and documents. Nothing is public until it is published.",
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


WEBSITE_ACTIONS = {"create-website", "publish-website", "unpublish-website", "make-current", "unmake-current",
                   "freeze", "unfreeze"}


def action_view(request, number, action):
    conference = get_object_or_404(Conference, number=number)
    if not roles.can_view(request.user, conference):
        raise PermissionDenied
    home = dashboard.home_of(conference)
    target = ("conference:people" if action in ("add-person", "remove-person") else
              "conference:website" if action in WEBSITE_ACTIONS else "conference:overview")
    back = redirect(target, conference.number)

    if action in ("add-person", "remove-person"):
        if request.method != "POST":
            return back
        _person_action(request, conference, action)
        return back
    if action not in CONFIRM:
        raise PermissionDenied
    if not _allowed(request.user, conference, action):
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
        "pages": pages, "form": form, "home": home, "back_url": back.url,
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


def _person_action(request, conference, action):
    key = request.POST.get("role", "")
    group = dashboard.role_group(conference, key) if key else None
    if group is None or not roles.can_manage(request.user, conference, key if key in (roles.CHAIRS, roles.ORGANISERS)
                                             else group.name):
        raise PermissionDenied
    User = get_user_model()
    if action == "remove-person":
        user = User.objects.filter(pk=request.POST.get("user")).first()
        if user:
            dashboard.remove_person(conference, key, user)
            messages.success(request, f"{user.get_full_name() or user.get_username()} no longer has the role "
                                      f"{group.name}.")
        return
    form = PersonForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Give a valid e-mail address.")
        return
    user, created = dashboard.add_person(request, conference, key, **form.cleaned_data)
    who = user.get_full_name() or user.email
    if created:
        messages.success(request, f"{who} was given an account and the role {group.name}, and an e-mail was sent "
                                  f"with a link to choose a password.")
    else:
        messages.success(request, f"{who} (an existing account) now has the role {group.name}.")


urlpatterns = [
    path("", overview, name="overview"),
    path("website/", website, name="website"),
    path("branding/", branding, name="branding"),
    path("people/", people, name="people"),
    path("do/<slug:action>/", action_view, name="action"),
]
