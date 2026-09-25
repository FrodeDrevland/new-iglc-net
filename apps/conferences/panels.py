"""The panel on the back office's front page (/manage/) for people with a role in a conference."""

from wagtail.admin.ui.components import Component

from . import dashboard, roles


class YourConferencesPanel(Component):
    name = "your_conferences"
    order = 10
    template_name = "conferences/admin/panel.html"

    def __init__(self, request):
        self.request = request
        self.conferences = [] if request.user.is_superuser else list(roles.conferences_for(request.user))

    def get_context_data(self, parent_context=None):
        rows = []
        for conference in self.conferences:
            home = dashboard.home_of(conference)
            mine = roles.roles_of(self.request.user, conference)
            rows.append({"conference": conference, "home": home, "website": dashboard.website_state(home),
                         "can_publish": roles.can_publish(self.request.user, conference),
                         "has_programme": dashboard._has(conference, "programme") and bool(
                             mine & {"chair", "organiser", "part"})})
        return {"rows": rows}
