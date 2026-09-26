"""The people of a conference and what they may do: one place for the roles.

    Role                    Group                              May
    ----------------------  ---------------------------------  ------------------------------------------------
    IGLC (superusers)       –                                  everything
    Conference chairs       IGLC nn conference chairs          the website (edit, publish), the whole programme,
                                                               add and remove people (except chairs)
    Website organisers      IGLC nn organisers                 the website (edit, publish), programme locations
    Scientific chairs       IGLC nn scientific chairs          the proceedings, as chief editors
                                                               (apps/production/access.py), and the academic
                                                               conference's sessions in the programme
    Other part chairs       IGLC nn industry day chairs, ...   their part of the programme (apps/programme)
    Proceedings editors     (the production's editor list)     the proceedings (apps/production)

Everyone with a role sees the conference's dashboard; only the IGLC changes its settings (current,
frozen, archive) or deletes it. The conference chairs group is the programme's chairs group
(apps/programme/setup.py uses the same name), so chairs keep one group for both; the same goes for
the scientific chairs and the programme's academic part. Only the IGLC appoints conference chairs and
scientific chairs.
"""

from __future__ import annotations

from django.contrib.auth.models import Group, Permission

ORGANISERS, CHAIRS, SCIENTIFIC = "organisers", "chairs", "scientific"
IGLC_APPOINTS = {CHAIRS, SCIENTIFIC}

LABELS = {CHAIRS: "Conference chairs", SCIENTIFIC: "Scientific chairs", ORGANISERS: "Website organisers"}
DESCRIPTIONS = {
    CHAIRS: "Edit and publish the website, run the whole programme, and add or remove organisers and part chairs.",
    SCIENTIFIC: "The proceedings (as chief editors) and the academic conference's sessions in the programme.",
    ORGANISERS: "Edit and publish the website, upload its pictures and documents, and keep the programme's "
                "locations.",
}

PAGE_PERMISSIONS = ("add_page", "change_page", "publish_page")
IMAGE_PERMISSIONS = ("add_image", "change_image", "choose_image")
DOCUMENT_PERMISSIONS = ("add_document", "change_document", "choose_document")


def group_name(conference, role: str) -> str:
    return {ORGANISERS: f"IGLC {conference.number} organisers",
            CHAIRS: f"IGLC {conference.number} conference chairs",
            SCIENTIFIC: f"IGLC {conference.number} scientific chairs"}[role]


def group(conference, role: str, create: bool = False) -> Group | None:
    name = group_name(conference, role)
    if not create:
        return Group.objects.filter(name=name).first()
    found, _ = Group.objects.get_or_create(name=name)
    found.permissions.add(Permission.objects.get(content_type__app_label="wagtailadmin", codename="access_admin"))
    return found


def collection(conference, create: bool = False):
    from wagtail.models import Collection

    root = Collection.get_first_root_node()
    name = f"IGLC {conference.number}"
    found = root.get_children().filter(name=name).first()
    if found is None and create:
        found = root.add_child(name=name)
    return found


def grant_website(target: Group, home) -> Group:
    """Edit and publish the pages under the home page, and upload to the conference's collection.
    Repeatable."""
    from wagtail.models import GroupCollectionPermission, GroupPagePermission

    for codename in PAGE_PERMISSIONS:
        GroupPagePermission.objects.get_or_create(
            group=target, page=home,
            permission=Permission.objects.get(content_type__app_label="wagtailcore", codename=codename))
    folder = collection(home.conference, create=True)
    for app, codenames in (("wagtailimages", IMAGE_PERMISSIONS), ("wagtaildocs", DOCUMENT_PERMISSIONS)):
        for codename in codenames:
            GroupCollectionPermission.objects.get_or_create(
                group=target, collection=folder,
                permission=Permission.objects.get(content_type__app_label=app, codename=codename))
    return target


def setup_website_roles(home):
    """The organisers and chairs groups, both with the website's permissions. Repeatable."""
    for role in (ORGANISERS, CHAIRS):
        grant_website(group(home.conference, role, create=True), home)


# ---------------------------------------------------------------- who has which role

def part_groups(conference, include_scientific: bool = False):
    """[(part, group)] for the programme's parts that have an editors group. The scientific chairs'
    group (the academic part's) is a role of its own and left out unless asked for."""
    programme = getattr(conference, "programme", None) if _has(conference, "programme") else None
    if programme is None:
        return []
    scientific = group_name(conference, SCIENTIFIC)
    return [(part, part.editors) for part in programme.parts.select_related("editors").order_by("sort_order")
            if part.editors_id and (include_scientific or part.editors.name != scientific)]


def _has(obj, relation):
    try:
        return getattr(obj, relation) is not None
    except Exception:
        return False


def roles_of(user, conference) -> set[str]:
    """{"iglc", "chair", "scientific", "organiser", "part", "editor"}: what this person is for this conference."""
    if not user.is_authenticated or not user.is_active:
        return set()
    found = set()
    if user.is_superuser:
        found.add("iglc")
    names = set(user.groups.values_list("name", flat=True))
    if group_name(conference, CHAIRS) in names:
        found.add("chair")
    if group_name(conference, ORGANISERS) in names:
        found.add("organiser")
    if group_name(conference, SCIENTIFIC) in names:
        found.add("scientific")
    if any(g.name in names for _, g in part_groups(conference)):
        found.add("part")
    if _has(conference, "production") and conference.production.editors.filter(user=user).exists():
        found.add("editor")
    return found


def conferences_for(user):
    """The conferences in which this person has a role (for superusers: none; they see them all)."""
    from django.db.models import Q

    from apps.archive.models import Conference

    if not user.is_authenticated or user.is_superuser:
        return Conference.objects.none()
    names = list(user.groups.filter(name__regex=r"^IGLC \d+ ").values_list("name", flat=True))
    numbers = {int(name.split()[1]) for name in names}
    return (Conference.objects.filter(Q(number__in=numbers) | Q(production__editors__user=user))
            .distinct().order_by("-number"))


def can_view(user, conference) -> bool:
    return bool(roles_of(user, conference)) or user.has_perm("archive.change_conference") \
        or user.has_perm("archive.view_conference")


def can_manage(user, conference, role: str) -> bool:
    """May add and remove people in this role (role: "chairs", "scientific", "organisers" or a part's
    group name)."""
    mine = roles_of(user, conference)
    if "iglc" in mine:
        return True
    return "chair" in mine and role not in IGLC_APPOINTS and role not in (
        group_name(conference, CHAIRS), group_name(conference, SCIENTIFIC))


def can_publish(user, conference) -> bool:
    return bool(roles_of(user, conference) & {"iglc", "chair", "organiser"})
