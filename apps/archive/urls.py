"""Archive URLs. The paths keep the old site's structure (lower case) so DOIs and citations resolve."""

from django.urls import re_path

from . import views

app_name = "archive"

ID = r"(?P<pk>\d+)"

urlpatterns = [
    re_path(r"^links/?$", views.links, name="links"),
    re_path(r"^papers/?$", views.conference_list, name="conference_list"),
    re_path(rf"^papers/conference/{ID}/?$", views.conference_detail, name="conference"),
    re_path(rf"^papers/details/{ID}/?$", views.paper_detail, name="paper"),
    re_path(rf"^papers/details/{ID}/pdf/?$", views.paper_pdf, name="paper_pdf"),
    re_path(rf"^papers/details/{ID}/presentation/?$", views.paper_presentation, name="paper_presentation"),
    re_path(r"^papers/search/?$", views.search, name="search"),
    re_path(r"^authors/?$", views.author_list, name="authors"),
    re_path(rf"^authors/{ID}/?$", views.author_detail, name="author"),
    re_path(r"^papers/findbyconftoolid(?:/(?P<conftool_id>[\w-]+))?/?$", views.find_by_conftool_id,
            name="find_by_conftool_id"),
    # Exports, with the old action names
    re_path(rf"^papers/exportbibtex/{ID}/?$", views.export_paper, {"fmt": "bibtex"}, name="export_paper_bibtex"),
    re_path(rf"^papers/exportris/{ID}/?$", views.export_paper, {"fmt": "ris"}, name="export_paper_ris"),
    re_path(rf"^papers/exportconferencebibtex/{ID}/?$", views.export_conference, {"fmt": "bibtex"},
            name="export_conference_bibtex"),
    re_path(rf"^papers/exportconferenceris/{ID}/?$", views.export_conference, {"fmt": "ris"},
            name="export_conference_ris"),
    re_path(r"^papers/exportsearchbibtex/?$", views.export_search, {"fmt": "bibtex"}, name="export_search_bibtex"),
    re_path(r"^papers/exportsearchris/?$", views.export_search, {"fmt": "ris"}, name="export_search_ris"),
    re_path(r"^papers/exportcompletebibtex/?$", views.export_complete, {"fmt": "bibtex"},
            name="export_complete_bibtex"),
    re_path(r"^papers/exportcompleteris/?$", views.export_complete, {"fmt": "ris"}, name="export_complete_ris"),
]
