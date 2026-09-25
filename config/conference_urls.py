"""URLs of the conference sites (conference.iglc.net). See apps.conferences."""

from django.conf import settings
from django.conf.urls.static import static
from django.urls import include, path, re_path
from django.views.generic import RedirectView
from django.views.static import serve
from wagtail import urls as wagtail_urls
from wagtail.documents import urls as wagtaildocs_urls

from apps.conferences import views

handler404 = "apps.conferences.views.not_found"

urlpatterns = [
    path("robots.txt", views.robots_txt),
    path("sitemap.xml", views.sitemap),
    # The back office is on the main site
    re_path(r"^(?:manage|cms|django-admin)(?:/(?P<rest>.*))?$",
            RedirectView.as_view(url=settings.SITE_URL + "/manage/%(rest)s", query_string=True)),
    path("documents/", include(wagtaildocs_urls)),
    # The programme's own pages, below the conference's programme page (apps/programme/public.py)
    path("<int:year>/programme/", include("apps.programme.conference_urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
elif settings.SERVE_MEDIA:
    urlpatterns += [re_path(r"^media/(?P<path>.*)$", serve, {"document_root": settings.MEDIA_ROOT})]

urlpatterns += [path("", include(wagtail_urls))]
