"""The programme's pages on the conference site: /<year>/programme/... (config/conference_urls.py)."""

from django.urls import path

from . import conference_views as views
from . import venue_views

app_name = "conference_programme"

urlpatterns = [
    path("day/<str:day>/", views.day, name="day"),
    path("session/<int:pk>/", views.session, name="session"),
    path("location/<int:pk>/", views.location, name="location"),
    path("part/<int:pk>/", views.part, name="part"),
    path("private/<uuid:token>/", views.private, name="private"),
    path("session/<int:pk>/calendar.ics", venue_views.session_calendar, name="session_calendar"),
    path("now/", venue_views.now, name="now"),
    path("today/", venue_views.today, name="today"),
    path("my/", venue_views.my, name="my"),
    path("calendar.ics", venue_views.calendar, name="calendar"),
]
