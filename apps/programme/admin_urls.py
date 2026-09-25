"""The programme's back-office pages, under /manage/programme/ (registered in wagtail_hooks)."""

from django.urls import path

from . import views

app_name = "programme"

urlpatterns = [
    path("", views.programme_list, name="list"),
    path("<int:number>/", views.overview, name="overview"),
    path("<int:number>/settings/", views.programme_settings, name="settings"),
    path("<int:number>/locations/", views.locations, name="locations"),
    path("<int:number>/locations/add/", views.location_edit, name="location_add"),
    path("<int:number>/locations/<int:pk>/", views.location_edit, name="location"),
    path("<int:number>/sessions/add/", views.session_edit, name="session_add"),
    path("<int:number>/sessions/<int:pk>/", views.session_edit, name="session"),
    path("<int:number>/papers/", views.papers, name="papers"),
    path("<int:number>/registrations/", views.registrations, name="registrations"),
    path("<int:number>/backing/", views.backing_report, name="backing"),
]
