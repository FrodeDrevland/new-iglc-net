from django.urls import path

from . import views

app_name = "production"

urlpatterns = [
    path("for-authors/check-your-paper/", views.check_form, name="check_form"),
    path("for-authors/check-your-paper/iglc-paper-check-skill.zip", views.author_skill, name="author_skill"),
    path("for-authors/check-your-paper/<uuid:pk>/", views.check_report, name="check_report"),
    path("for-authors/check-your-paper/<uuid:pk>/report.pdf", views.check_report_pdf, name="check_report_pdf"),
]
