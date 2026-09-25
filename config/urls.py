from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.auth.views import LogoutView
from django.contrib.sitemaps import views as sitemap_views
from django.http import HttpResponse
from django.urls import include, path, re_path
from django.views.generic import RedirectView
from django.views.static import serve
from wagtail import urls as wagtail_urls
from wagtail.admin import urls as wagtailadmin_urls
from wagtail.documents import urls as wagtaildocs_urls

from django.views.decorators.cache import cache_page

from apps.archive import views as archive_views
from apps.core.sitemaps import SITEMAPS

admin.site.site_header = "IGLC data (superusers)"
admin.site.site_title = "IGLC data (superusers)"
# The back office is Wagtail's admin at /manage/. Django's admin is a fallback for superusers.
admin.site.has_permission = lambda request: request.user.is_active and request.user.is_superuser

def robots_txt(request):
    if settings.SITE_NOINDEX:
        return HttpResponse("User-agent: *\nDisallow: /\n", content_type="text/plain")
    sitemap = request.build_absolute_uri("/sitemap.xml")
    return HttpResponse(f"User-agent: *\nDisallow: /manage/\nDisallow: /django-admin/\n\nSitemap: {sitemap}\n",
                        content_type="text/plain")


urlpatterns = [
    path("robots.txt", robots_txt),
    path("sitemap.xml", cache_page(6 * 3600)(sitemap_views.index), {"sitemaps": SITEMAPS,
         "sitemap_url_name": "sitemap_section"}),
    path("sitemap-<section>.xml", cache_page(6 * 3600)(sitemap_views.sitemap), {"sitemaps": SITEMAPS},
         name="sitemap_section"),
    path("django-admin/", admin.site.urls),
    # The back office (Wagtail): pages, archive, committees, proceedings production, users.
    # Logging out returns to the front page, not to the login page.
    path("manage/logout/", LogoutView.as_view(next_page="/"), name="manage_logout"),
    path("manage/", include(wagtailadmin_urls)),
    # Old addresses of the back office
    re_path(r"^cms/(?P<rest>.*)$", RedirectView.as_view(url="/manage/%(rest)s", query_string=True)),
    re_path(r"^production/(?P<rest>.*)$", RedirectView.as_view(url="/manage/production/%(rest)s", query_string=True)),
    path("documents/", include(wagtaildocs_urls)),
    path("", archive_views.home, name="home"),
    path("", include("apps.archive.urls")),
    path("", include("apps.governance.urls")),
    path("", include("apps.production.urls")),
    path("", include("apps.programme.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
elif settings.SERVE_MEDIA:
    urlpatterns += [re_path(r"^media/(?P<path>.*)$", serve, {"document_root": settings.MEDIA_ROOT})]

# Wagtail serves the CMS pages; it must come last because it matches any path.
urlpatterns += [path("", include(wagtail_urls))]
