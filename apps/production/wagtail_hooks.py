"""Proceedings production in the back office (/manage/production/)."""

from django import forms

from django.urls import include, path, reverse
from wagtail import hooks
from wagtail.admin.menu import MenuItem

from wagtail.admin.forms import WagtailAdminModelForm
from wagtail.admin.menu import MenuItem as _MenuItem  # noqa: F401
from wagtail.admin.panels import FieldPanel, FieldRowPanel, HelpPanel, InlinePanel, ObjectList
from wagtail.admin.viewsets.model import ModelViewSet
from django.core.exceptions import PermissionDenied
from wagtail.admin.views.generic.models import EditView
from wagtail.permission_policies import ModelPermissionPolicy

from . import admin_urls
from .models import CheckRule, PaperCheck, Production, ProductionEditor


@hooks.register("register_admin_urls")
def production_urls():
    return [path("production/", include(admin_urls))]


class ProductionMenuItem(MenuItem):
    def is_shown(self, request):
        from .access import productions_for

        return productions_for(request.user).exists() or request.user.is_superuser


@hooks.register("register_conferences_menu_item")  # the Conferences menu (apps/conferences/admin_views.py)
def production_menu_item():
    return ProductionMenuItem("Proceedings production", reverse("proceedings:productions"), icon_name="doc-full-inverse",
                              order=3)


# ---------------------------------------------------------------- production settings and editors

class EditorForm(WagtailAdminModelForm):
    """An editor's tracks: those of the production's conference."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if "tracks" in self.fields:
            conference = getattr(getattr(self.instance, "production", None), "conference_id", None)
            queryset = self.fields["tracks"].queryset
            self.fields["tracks"].queryset = (queryset.filter(conference_id=conference) if conference
                                              else queryset.filter(conference__production__isnull=False))


ProductionEditor.base_form_class = EditorForm


class ProductionPolicy(ModelPermissionPolicy):
    """Superusers and publishers (change_production) edit any production; a chief editor edits
    their own. Deleting needs the real permission."""

    def _chief_somewhere(self, user):
        return user.is_active and user.production_roles.filter(role=ProductionEditor.Role.CHIEF).exists()

    def user_has_permission(self, user, action):
        if action in ("change", "view") and self._chief_somewhere(user):
            return True
        return super().user_has_permission(user, action)

    def user_has_permission_for_instance(self, user, action, instance):
        if super().user_has_permission(user, action):
            return True
        return action in ("change", "view") and instance.editors.filter(
            user=user, role=ProductionEditor.Role.CHIEF).exists()


class ProductionEditView(EditView):
    def get_object(self, queryset=None):
        production = super().get_object(queryset)
        if not self.permission_policy.user_has_permission_for_instance(self.request.user, "change", production):
            raise PermissionDenied
        return production

    def get_success_url(self):
        return reverse("proceedings:production", args=[self.object.conference.number])


class ProductionViewSet(ModelViewSet):
    """Who works on a production, and its settings. Reached from the production's own page."""

    model = Production
    edit_view_class = ProductionEditView
    add_view_enabled = False
    icon = "doc-full-inverse"
    add_to_admin_menu = False
    inspect_view_enabled = False
    list_display = ["__str__", "status"]

    @property
    def permission_policy(self):
        return ProductionPolicy(self.model)

    edit_handler = ObjectList([
        FieldRowPanel([FieldPanel("conference", read_only=True), FieldPanel("status", read_only=True),
                       FieldPanel("first_page", read_only=True)]),
        FieldRowPanel([FieldPanel("conference_chair"), FieldPanel("copyright_holders")]),
        InlinePanel("editors", heading="Editors", label="Editor",
                    help_text="Chief editors see and arrange everything and stage publication; editors see the papers of "
                              "their tracks (all papers if no track is ticked). Being added here gives access to the back office.",
                    panels=[FieldRowPanel([FieldPanel("user"), FieldPanel("role")]),
                            FieldPanel("tracks", widget=forms.CheckboxSelectMultiple)]),
    ])


# ---------------------------------------------------------------- the authors' template checks (read only)

class ReadOnlyPolicy(ModelPermissionPolicy):
    def user_has_permission(self, user, action):
        return action in ("view", "inspect") and super().user_has_permission(user, "view")


class PaperCheckViewSet(ModelViewSet):
    model = PaperCheck
    icon = "tasks"
    menu_label = "Authors' paper checks"
    add_to_admin_menu = False
    inspect_view_enabled = True
    list_display = ["file_name", "stage", "passed", "title", "created"]
    form_fields = ["stage"]  # never edited (read-only policy)
    list_filter = ["stage", "passed"]
    search_fields = ["file_name", "title", "sha256"]
    list_per_page = 50

    @property
    def permission_policy(self):
        return ReadOnlyPolicy(self.model)


paper_checks = PaperCheckViewSet("paper_checks", url_prefix="reports/paper-checks")


# ---------------------------------------------------------------- the paper check's rules (Settings)

class CheckRulePolicy(ModelPermissionPolicy):
    """The rules come from the checks in the code: they can be changed, not added or deleted."""

    def user_has_permission(self, user, action):
        if action in ("add", "delete"):
            return False
        return super().user_has_permission(user, "change" if action == "inspect" else action)


class CheckRuleViewSet(ModelViewSet):
    model = CheckRule
    icon = "tasks"
    menu_label = "Paper check rules"
    add_to_settings_menu = True
    list_display = ["label", "code", "review", "camera_ready", "production"]
    list_filter = ["review", "camera_ready", "production"]
    search_fields = ["label", "code"]
    list_per_page = 100
    ordering = ["order"]
    panels = [
        HelpPanel("<p>What happens at each stage when this check finds something. <b>Reject</b>: the upload is "
                  "refused until it is fixed. <b>Warn</b>: the author must confirm to submit anyway. <b>Note</b>: "
                  "shown for information. <b>Off</b>: not checked. The limits (pages, words …) are under "
                  "Settings → Paper check limits.</p>"),
        FieldPanel("review"), FieldPanel("camera_ready"), FieldPanel("production"),
    ]

    @property
    def permission_policy(self):
        return CheckRulePolicy(self.model)


@hooks.register("register_admin_viewset")
def production_viewsets():
    return [ProductionViewSet("production_settings", url_prefix="production-settings"), paper_checks,
            CheckRuleViewSet("check_rules", url_prefix="paper-check-rules")]


@hooks.register("register_reports_menu_item")
def paper_checks_menu_item():
    return paper_checks.get_menu_item()
