"""Committees in the conference workspace (/manage/<number>/committees/): the members of the website's
committees page in one table per committee, with photos, instead of Wagtail's long inline form.

The members belong to the committees page (conferences.CommitteesPage), so every change is a new draft
of that page; "Publish" puts the latest draft on the website. Members are identified by their position
in the draft, together with their name, so that a stale form cannot change the wrong person.
"""

from __future__ import annotations

import re

from django import forms
from django.contrib import messages
from django.shortcuts import redirect, render

from . import roles
from .models import CommitteeMember, CommitteesPage


def committees_page(home):
    return CommitteesPage.objects.child_of(home).first() if home else None


def draft_members(draft) -> list:
    return list(draft.members.all())


def save_members(draft, members, user):
    for order, member in enumerate(members):
        member.sort_order = order
    draft.members = members
    return draft.save_revision(user=user, log_action=True)


def grouped(members):
    """[(committee, [(index, member)])] in the order the committees first appear."""
    groups: dict[str, list] = {}
    for index, member in enumerate(members):
        groups.setdefault(member.committee, []).append((index, member))
    return list(groups.items())


def parse_lines(text: str):
    """Pasted members: one per line, "Name; Affiliation; Country" or tab-separated (from a spreadsheet).
    A line without separators is just a name."""
    rows = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = [part.strip() for part in re.split(r"\t|;", line)]
        parts += [""] * (3 - len(parts))
        rows.append({"name": parts[0], "affiliation": parts[1], "country": parts[2]})
    return [row for row in rows if row["name"]]


class MemberForm(forms.Form):
    committee = forms.CharField(max_length=120, help_text="For example 'Organising committee' or 'Scientific committee'.",
                                widget=forms.TextInput(attrs={"list": "committee-names"}))
    name = forms.CharField(max_length=200)
    role = forms.CharField(max_length=120, required=False, help_text="For example 'Conference chair'. Shown as a label.")
    photo = forms.ModelChoiceField(queryset=None, required=False, label="Portrait",
                                   help_text="At least 400 × 400 pixels; shown round, cut to a square around the "
                                             "picture's focal point.")
    affiliation = forms.CharField(max_length=300, required=False)
    country = forms.CharField(max_length=100, required=False)
    url = forms.URLField(required=False, label="Profile page",
                         help_text="Their page at their university or company, or on LinkedIn.")

    FIELDS = ("committee", "name", "role", "photo", "affiliation", "country", "url")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from wagtail.images import get_image_model
        from wagtail.images.widgets import AdminImageChooser

        self.fields["photo"].queryset = get_image_model().objects.all()
        self.fields["photo"].widget = AdminImageChooser()


class BulkForm(forms.Form):
    committee = forms.CharField(max_length=120, widget=forms.TextInput(attrs={"list": "committee-names"}))
    lines = forms.CharField(widget=forms.Textarea(attrs={"rows": 8}), label="Members",
                            help_text="One per line: Name; Affiliation; Country. Rows copied from a spreadsheet "
                                      "(name, affiliation and country in three columns) work too.")


def _context(request, number):
    from .workspace_views import _context as workspace_context

    conference, context = workspace_context(request, number, need="website")
    page = committees_page(context["home"])
    return conference, context, page


def committees(request, number):
    conference, context, page = _context(request, number)
    if page is None:
        context.update({"tab": "committees", "page": None})
        return render(request, "conferences/admin/committees.html", context)
    frozen = context["home"].frozen and not request.user.is_superuser
    draft = page.get_latest_revision_as_object()
    members = draft_members(draft)
    add_form, bulk_form = MemberForm(prefix="add"), BulkForm(prefix="bulk")

    if request.method == "POST" and not frozen:
        action = request.POST.get("action", "")
        index = _index(request, members)
        if action == "add":
            add_form = MemberForm(request.POST, prefix="add")
            if add_form.is_valid():
                data = add_form.cleaned_data
                position = _end_of(members, data["committee"])
                members.insert(position, CommitteeMember(**{name: data[name] or ("" if name != "photo" else None)
                                                            for name in MemberForm.FIELDS}))
                save_members(draft, members, request.user)
                messages.success(request, f"{data['name']} was added to {data['committee']} (as a draft).")
                return redirect("conference:committees", number)
        elif action == "bulk":
            bulk_form = BulkForm(request.POST, prefix="bulk")
            if bulk_form.is_valid():
                committee = bulk_form.cleaned_data["committee"].strip()
                rows = parse_lines(bulk_form.cleaned_data["lines"])
                position = _end_of(members, committee)
                for offset, row in enumerate(rows):
                    members.insert(position + offset, CommitteeMember(committee=committee, **row))
                save_members(draft, members, request.user)
                messages.success(request, f"{len(rows)} members were added to {committee} (as a draft).")
                return redirect("conference:committees", number)
        elif action in ("up", "down", "remove") and index is not None:
            member = members[index]
            if action == "remove":
                members.pop(index)
                messages.success(request, f"{member.name} was removed (as a draft).")
            else:
                same = [i for i, m in enumerate(members) if m.committee == member.committee]
                at = same.index(index)
                other = same[at - 1] if action == "up" and at > 0 else (
                    same[at + 1] if action == "down" and at + 1 < len(same) else None)
                if other is not None:
                    members[index], members[other] = members[other], members[index]
            save_members(draft, members, request.user)
            return redirect("conference:committees", number)
        elif action in ("committee-up", "committee-down"):
            members = _move_committee(members, request.POST.get("committee", ""), action == "committee-up")
            save_members(draft, members, request.user)
            return redirect("conference:committees", number)
        elif action == "layout" and request.POST.get("layout") in dict(CommitteesPage.LAYOUTS):
            draft.layout = request.POST["layout"]
            draft.save_revision(user=request.user, log_action=True)
            messages.success(request, "The layout is saved (as a draft). Preview shows it.")
            return redirect("conference:committees", number)
        elif action == "publish" and roles.can_publish(request.user, conference):
            page.get_latest_revision().publish(user=request.user)
            messages.success(request, "The committees page is published.")
            return redirect("conference:committees", number)

    page.refresh_from_db()
    context.update({
        "tab": "committees", "page": page, "frozen": frozen, "groups": grouped(members),
        "count": len(members), "add_form": add_form, "bulk_form": bulk_form,
        "committee_names": list(dict.fromkeys(m.committee for m in members)),
        "unpublished": not page.live or page.has_unpublished_changes,
        "layouts": CommitteesPage.LAYOUTS, "layout": draft.layout,
    })
    return render(request, "conferences/admin/committees.html", context)


def member_edit(request, number, index):
    conference, context, page = _context(request, number)
    if page is None:
        return redirect("conference:committees", number)
    draft = page.get_latest_revision_as_object()
    members = draft_members(draft)
    if not 0 <= index < len(members):
        messages.error(request, "That member is no longer there; the list may have changed.")
        return redirect("conference:committees", number)
    member = members[index]
    initial = {name: getattr(member, name) for name in MemberForm.FIELDS}
    form = MemberForm(request.POST or None, initial=initial)
    frozen = context["home"].frozen and not request.user.is_superuser
    if request.method == "POST" and not frozen and form.is_valid():
        if request.POST.get("name_was") != member.name:
            messages.error(request, "Someone changed the list meanwhile; open the member again.")
            return redirect("conference:committees", number)
        for name in MemberForm.FIELDS:
            value = form.cleaned_data[name]
            setattr(member, name, value if value or name == "photo" else "")
        save_members(draft, members, request.user)
        messages.success(request, f"{member.name} was saved (as a draft).")
        return redirect("conference:committees", number)
    context.update({"tab": "committees", "page": page, "form": form, "member": member, "index": index,
                    "frozen": frozen, "committee_names": list(dict.fromkeys(m.committee for m in members))})
    return render(request, "conferences/admin/committee_member.html", context)


def _index(request, members):
    try:
        index = int(request.POST.get("index", ""))
    except ValueError:
        return None
    if 0 <= index < len(members) and members[index].name == request.POST.get("name_was"):
        return index
    return None


def _end_of(members, committee):
    """Where a new member of this committee goes: after its last member, or at the end."""
    positions = [i for i, m in enumerate(members) if m.committee == committee]
    return positions[-1] + 1 if positions else len(members)


def _move_committee(members, committee, up):
    names = list(dict.fromkeys(m.committee for m in members))
    if committee not in names:
        return members
    at = names.index(committee)
    swap = at - 1 if up else at + 1
    if 0 <= swap < len(names):
        names[at], names[swap] = names[swap], names[at]
    return [m for name in names for m in members if m.committee == name]
