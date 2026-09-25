"""URLs of program.iglc.net: the current conference's programme at the venue (apps/programme)."""

from django.urls import path

from apps.programme import venue_views as views

handler404 = "apps.conferences.views.not_found"

urlpatterns = [
    path("robots.txt", views.robots_txt),
    path("", views.now, name="venue_now"),
    path("today/", views.today, name="venue_today"),
    path("my/", views.my, name="venue_my"),
    path("calendar.ics", views.calendar, name="venue_calendar"),
    path("programme.pdf", views.booklet, name="venue_booklet"),
    path("sw.js", views.service_worker, name="venue_service_worker"),
]
