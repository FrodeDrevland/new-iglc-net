from django.urls import re_path

from . import views

app_name = "governance"

urlpatterns = [
    re_path(r"^about/committees/?$", views.committees, name="committees"),
]
