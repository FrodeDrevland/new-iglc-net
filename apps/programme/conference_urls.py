"""The programme's pages on the conference site: /<year>/programme/... (config/conference_urls.py)."""

from django.urls import path

from . import conference_views as views

app_name = "conference_programme"

urlpatterns = [
    path("day/<str:day>/", views.day, name="day"),
    path("session/<int:pk>/", views.session, name="session"),
    path("location/<int:pk>/", views.location, name="location"),
    path("part/<int:pk>/", views.part, name="part"),
    path("private/<uuid:token>/", views.private, name="private"),
]
