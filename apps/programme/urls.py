"""Public pages of the programme on the main site (the authors' confirmation)."""

from django.urls import path

from . import public_views

app_name = "programme_public"

urlpatterns = [
    path("for-authors/confirm-presentation/<uuid:token>/", public_views.confirm, name="confirm"),
]
