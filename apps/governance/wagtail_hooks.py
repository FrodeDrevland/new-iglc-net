"""Committees in the back office: members are edited on their committee's page."""

from wagtail import hooks
from wagtail.admin.panels import FieldPanel, FieldRowPanel, InlinePanel
from wagtail.admin.viewsets.model import ModelViewSet

from apps.archive.admin_views import PersonChooser

from .models import Committee


class CommitteeViewSet(ModelViewSet):
    model = Committee
    menu_label = "Committees"
    icon = "group"
    menu_order = 210
    add_to_admin_menu = True
    list_display = ["name", "charter_section", "order"]
    inspect_view_enabled = False
    panels = [
        FieldRowPanel([FieldPanel("name"), FieldPanel("slug"), FieldPanel("charter_section"), FieldPanel("order")]),
        FieldPanel("description"),
        InlinePanel("seats", heading="Members (past and present)", label="Member",
                    panels=[FieldRowPanel([FieldPanel("first_name"), FieldPanel("last_name"), FieldPanel("role"),
                                           FieldPanel("is_chair")]),
                            FieldRowPanel([FieldPanel("affiliation"), FieldPanel("country")]),
                            FieldRowPanel([FieldPanel("start_date"), FieldPanel("end_date")]),
                            FieldRowPanel([FieldPanel("person", widget=PersonChooser), FieldPanel("url")]),
                            FieldPanel("note")]),
    ]


@hooks.register("register_admin_viewset")
def committee_viewset():
    return CommitteeViewSet("committees", url_prefix="committees")
