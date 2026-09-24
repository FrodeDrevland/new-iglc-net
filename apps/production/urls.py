from django.urls import path

from . import editor_views, views

app_name = "production"

urlpatterns = [
    path("for-authors/check-your-paper/", views.check_form, name="check_form"),
    path("for-authors/check-your-paper/iglc-paper-check-skill.zip", views.author_skill, name="author_skill"),
    path("for-authors/check-your-paper/<uuid:pk>/", views.check_report, name="check_report"),
    path("for-authors/check-your-paper/<uuid:pk>/report.pdf", views.check_report_pdf, name="check_report_pdf"),
    # Editors
    path("production/", editor_views.production_list, name="productions"),
    path("production/<int:number>/", editor_views.production_detail, name="production"),
    path("production/<int:number>/download/", editor_views.download, name="download"),
    path("production/<int:number>/upload/", editor_views.upload, name="upload"),
    path("production/<int:number>/arrange/", editor_views.arrange, name="arrange"),
    path("production/<int:number>/<int:conftool_id>/", editor_views.paper, name="paper"),
    path("production/<int:number>/<int:conftool_id>/v<int:version>.<str:kind>", editor_views.version_file,
         name="version_file"),
]
