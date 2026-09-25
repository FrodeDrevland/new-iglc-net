"""The conference dashboard in the back office (Conferences → All conferences → a conference):
what the platform knows about a conference, and the actions on it.

    overview(conference)                  everything the dashboard shows, read from the database
    website_state(home)                   "none", "draft", "published", "current" or "frozen"
    set_home_flags(home, **flags)         current and frozen, on the live page and its revisions
    publish_pages(pages, user)            publish the latest revision of each page
    unpublish_website(home, user)         the home page and every page below it
    deletion(conference)                  what deleting would remove, and what stops it
    delete_conference(conference, user)   the website through Wagtail, then the record
    invite_organiser(...)                 a new account in the organisers group, with a set-password e-mail

The actions are for superusers; the views check that (apps/conferences/admin_views.py).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.db import transaction

from .models import ConferenceHomePage

WEBSITE_STATES = {
    "none": "No website",
    "draft": "Draft",
    "published": "Published",
    "current": "Current",
    "frozen": "Frozen",
}


# ---------------------------------------------------------------- reading

def when(conference, today: date | None = None) -> str:
    """ "upcoming", "running", "past" or "" (no dates)."""
    today = today or date.today()
    if not conference.start_date:
        return ""
    end = conference.end_date or conference.start_date
    if today < conference.start_date:
        return "upcoming"
    if today <= end:
        return "running"
    return "past"


def home_of(conference) -> ConferenceHomePage | None:
    return ConferenceHomePage.objects.filter(conference=conference).first()


def website_state(home) -> str:
    if home is None:
        return "none"
    if home.frozen:
        return "frozen"
    if not home.live:
        return "draft"
    return "current" if home.is_current else "published"


def organiser_group_name(conference) -> str:
    return f"IGLC {conference.number} organisers"


def organisers(conference):
    group = Group.objects.filter(name=organiser_group_name(conference)).first()
    if group is None:
        return None, []
    return group, list(group.user_set.order_by("last_name", "first_name", "username"))


def _pages(home):
    """The pages below the home page, in menu order, with their state."""
    rows = []
    for page in home.get_descendants().specific().order_by("path"):
        if not page.live:
            state = "draft"
        elif page.has_unpublished_changes:
            state = "changed"
        else:
            state = "live"
        rows.append({"page": page, "state": state, "depth": page.depth - home.depth})
    return rows


def _important_dates(home):
    """From the latest draft, which is what the organisers edit."""
    draft = home.get_latest_revision_as_object()
    return list(draft.important_dates.all())


def _people_of_group(group):
    return list(group.user_set.order_by("last_name", "first_name")) if group else []


def overview(conference) -> dict:
    from apps.archive.models import Paper

    home = home_of(conference)
    result = {
        "conference": conference,
        "when": when(conference),
        "tracks": list(conference.tracks.all()),
        "editors": list(conference.editors.all()),
        "home": home,
        "website": website_state(home),
        "website_label": WEBSITE_STATES[website_state(home)],
        "pages": _pages(home) if home else [],
        "important_dates": _important_dates(home) if home else [],
        "unpublished_pages": 0,
        "papers": Paper.objects.filter(conference=conference).count(),
    }
    if home:
        result["unpublished_pages"] = sum(1 for row in result["pages"] if row["state"] != "live") + (
            0 if home.live and not home.has_unpublished_changes else 1)
        result["home_url"] = home.get_url()
    result["organiser_group"], result["organisers"] = organisers(conference)

    programme = getattr(conference, "programme", None) if _has(conference, "programme") else None
    result["programme"] = programme
    if programme:
        parts = list(programme.parts.select_related("editors"))
        result["programme_sessions"] = programme.sessions.count()
        result["programme_registrations"] = programme.registrations.count()
        result["programme_people"] = (
            [("Conference chairs", programme.chairs, _people_of_group(programme.chairs))] if programme.chairs else []
        ) + [(part.name, part.editors, _people_of_group(part.editors)) for part in parts if part.editors]

    production = getattr(conference, "production", None) if _has(conference, "production") else None
    result["production"] = production
    if production:
        from apps.production.models import Submission

        submissions = production.submissions.all()
        result["submissions"] = submissions.exclude(status=Submission.Status.WITHDRAWN).count()
        result["submissions_approved"] = submissions.filter(status=Submission.Status.APPROVED).count()
        result["submissions_withdrawn"] = submissions.filter(status=Submission.Status.WITHDRAWN).count()
        result["production_editors"] = list(production.editors.select_related("user"))

    deposits = conference.crossref_deposits.filter(test=False)
    result["deposits"] = deposits.count()
    result["last_deposit"] = deposits.order_by("-created").first()
    return result


def _has(conference, relation: str) -> bool:
    """A reverse one-to-one without catching DoesNotExist everywhere."""
    try:
        getattr(conference, relation)
        return True
    except Exception:  # RelatedObjectDoesNotExist
        return False


def recent_activity(conference, home, limit: int = 12):
    """The latest log entries for the record and the website's pages, newest first."""
    from django.contrib.contenttypes.models import ContentType
    from wagtail.models import ModelLogEntry, PageLogEntry

    entries = list(ModelLogEntry.objects.filter(content_type=ContentType.objects.get_for_model(conference),
                                                object_id=str(conference.pk))
                   .select_related("user").order_by("-timestamp")[:limit])
    if home:
        pages = home.get_descendants(inclusive=True).values_list("pk", flat=True)
        entries += list(PageLogEntry.objects.filter(page_id__in=pages).select_related("user", "page")
                        .order_by("-timestamp")[:limit])
    entries.sort(key=lambda entry: entry.timestamp, reverse=True)
    return entries[:limit]


# ---------------------------------------------------------------- the website's flags

def _patch_revision(revision, flags: dict):
    if revision is None:
        return
    content = dict(revision.content)
    content.update(flags)
    revision.content = content
    revision.save(update_fields=["content"])


@transaction.atomic
def set_home_flags(home, **flags):
    """Set current and/or frozen at once, on the page and on its latest and live revisions, so that
    publishing a draft later does not bring back the old value. Marking one conference as current
    unmarks the others, in the same way."""
    allowed = {"is_current", "frozen"}
    assert flags and set(flags) <= allowed, flags
    ConferenceHomePage.objects.filter(pk=home.pk).update(**flags)
    for revision in {home.latest_revision, home.live_revision} - {None}:
        _patch_revision(revision, flags)
    if flags.get("is_current"):
        for other in ConferenceHomePage.objects.exclude(pk=home.pk).filter(is_current=True):
            set_home_flags(other, is_current=False)
    home.refresh_from_db()
    return home


# ---------------------------------------------------------------- publishing

def publishable(home):
    """The home page and the pages below it that have something not yet published."""
    pages = [home] + [row["page"] for row in _pages(home)]
    return [page for page in pages if not page.live or page.has_unpublished_changes]


@transaction.atomic
def publish_pages(pages, user):
    """Publish the latest revision of each page, parents first (a page under an unpublished
    parent is not reachable)."""
    done = []
    for page in sorted(pages, key=lambda p: p.depth):
        revision = page.latest_revision or page.save_revision(user=user)
        revision.publish(user=user)
        done.append(page)
    return done


@transaction.atomic
def unpublish_website(home, user):
    from wagtail.actions.unpublish_page import UnpublishPageAction

    home = home.specific
    if home.live:
        UnpublishPageAction(home, user=user, include_descendants=True).execute(skip_permission_checks=True)
    else:  # pages below an unpublished home page may still be live
        for page in home.get_descendants().live().specific():
            UnpublishPageAction(page, user=user).execute(skip_permission_checks=True)


# ---------------------------------------------------------------- deleting

@dataclass
class Deletion:
    removes: list[str] = field(default_factory=list)   # what goes with the conference
    keeps: list[str] = field(default_factory=list)     # what is left behind
    blockers: list[str] = field(default_factory=list)  # why it cannot be deleted now

    @property
    def allowed(self):
        return not self.blockers


def deletion(conference) -> Deletion:
    from apps.archive.models import Paper

    d = Deletion()
    papers = Paper.objects.filter(conference=conference).count()
    if papers:
        d.blockers.append(f"It has {papers} paper{'s' if papers != 1 else ''} in the archive. Papers have DOIs "
                          f"that must keep working, so a conference with papers is never deleted here.")
    deposits = conference.crossref_deposits.count()
    if deposits:
        d.blockers.append(f"It has {deposits} Crossref deposit{'s' if deposits != 1 else ''} (DOIs).")
    home = home_of(conference)
    if home:
        if home.frozen:
            d.blockers.append("Its website is frozen: it is the record of a conference that has taken place.")
        elif home.live:
            d.blockers.append("Its website is published. Unpublish it first (Website → Unpublish).")
        pages = home.get_descendants().count()
        d.removes.append(f"The website {home.title} and the {pages} page{'s' if pages != 1 else ''} below it "
                         f"(drafts and their history).")
    if _has(conference, "production"):
        production = conference.production
        submissions = production.submissions.count()
        if submissions:
            d.blockers.append(f"Its proceedings production has {submissions} paper{'s' if submissions != 1 else ''}. "
                              f"Delete them in Proceedings production first, if they really should go.")
        else:
            d.removes.append("Its proceedings production (no papers in it).")
    if _has(conference, "programme"):
        programme = conference.programme
        sessions, registrations = programme.sessions.count(), programme.registrations.count()
        d.removes.append(f"Its programme: {sessions} session{'s' if sessions != 1 else ''}, "
                         f"{programme.locations.count()} locations, {registrations} registration"
                         f"{'s' if registrations != 1 else ''}.")
    for label, related in (("track", conference.tracks), ("editor", conference.editors),
                           ("volume", conference.volumes), ("proceedings file", conference.proceedings_files)):
        n = related.count()
        if n:
            d.removes.append(f"{n} {label}{'s' if n != 1 else ''} of the conference record.")
    group = Group.objects.filter(name=organiser_group_name(conference)).first()
    if group:
        members = group.user_set.count()
        d.removes.append(f"The group {group.name} ({members} member{'s' if members != 1 else ''}; "
                         f"their accounts stay).")
    collection = _collection(conference)
    if collection:
        if _collection_is_empty(collection):
            d.removes.append(f"The empty collection {collection.name}.")
        else:
            d.keeps.append(f"The collection {collection.name}, with its pictures and documents: delete them "
                           f"under Images and Documents if they are not needed.")
    return d


def _collection(conference):
    from wagtail.models import Collection

    return Collection.get_first_root_node().get_children().filter(name=f"IGLC {conference.number}").first()


def _collection_is_empty(collection) -> bool:
    from wagtail.documents import get_document_model
    from wagtail.images import get_image_model

    return not (get_image_model().objects.filter(collection=collection).exists()
                or get_document_model().objects.filter(collection=collection).exists()
                or collection.get_children().exists())


@transaction.atomic
def delete_conference(conference, user):
    """Everything in deletion(conference).removes, then the record. Raises ValueError when
    something stops it."""
    from wagtail.actions.delete_page import DeletePageAction

    check = deletion(conference)
    if not check.allowed:
        raise ValueError(" ".join(check.blockers))
    home = home_of(conference)
    if home:
        DeletePageAction(home, user=user).execute(skip_permission_checks=True)
    if _has(conference, "programme"):
        programme = conference.programme
        programme.sessions.all().delete()  # sessions protect their parts and locations
        programme.delete()
    if _has(conference, "production"):
        conference.production.delete()
    Group.objects.filter(name=organiser_group_name(conference)).delete()
    collection = _collection(conference)
    if collection and _collection_is_empty(collection):
        collection.delete()
    conference.delete()


# ---------------------------------------------------------------- organisers

def add_organiser(conference, user):
    from .setup import organiser_group

    home = home_of(conference)
    group = organiser_group(home) if home else Group.objects.get_or_create(name=organiser_group_name(conference))[0]
    user.groups.add(group)
    return group


def remove_organiser(conference, user):
    group = Group.objects.filter(name=organiser_group_name(conference)).first()
    if group:
        user.groups.remove(group)


def invite_organiser(request, conference, first_name: str, last_name: str, email: str):
    """A new account (user name = e-mail address) in the organisers group, and an e-mail with a
    link to set a password. Returns the user. Raises ValueError if the address is taken."""
    import secrets

    from django.contrib.auth.forms import PasswordResetForm

    User = get_user_model()
    email = email.strip().lower()
    if User.objects.filter(email__iexact=email).exists() or User.objects.filter(username__iexact=email).exists():
        raise ValueError(f"There is already an account for {email}: add it with 'Add an existing account'.")
    user = User.objects.create_user(username=email, email=email, first_name=first_name.strip(),
                                    last_name=last_name.strip(), password=secrets.token_urlsafe(32))
    add_organiser(conference, user)
    form = PasswordResetForm({"email": email})
    form.is_valid()
    form.save(request=request, use_https=request.is_secure(),
              subject_template_name="conferences/admin/invite_subject.txt",
              email_template_name="conferences/admin/invite_email.txt",
              extra_email_context={"conference": conference, "inviter": request.user})
    return user
