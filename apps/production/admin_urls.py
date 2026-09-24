"""The editors' pages, in the back office under /manage/production/ (registered in wagtail_hooks)."""

from django.urls import path

from . import editor_views

app_name = "proceedings"

urlpatterns = [
    path("", editor_views.production_list, name="productions"),
    path("<int:number>/", editor_views.production_detail, name="production"),
    path("<int:number>/download/", editor_views.download, name="download"),
    path("<int:number>/upload/", editor_views.upload, name="upload"),
    path("<int:number>/arrange/", editor_views.arrange, name="arrange"),
    path("<int:number>/publish/", editor_views.publish, name="publish"),
    path("<int:number>/book/", editor_views.book, name="book"),
    path("<int:number>/book/<str:name>", editor_views.book_file, name="book_file"),
    path("<int:number>/<int:conftool_id>/", editor_views.paper, name="paper"),
    path("<int:number>/<int:conftool_id>/v<int:version>.<str:kind>", editor_views.version_file, name="version_file"),
]
