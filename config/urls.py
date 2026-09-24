from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.auth.views import LogoutView
from django.contrib.sitemaps import views as sitemap_views
from django.http import HttpResponse
from django.urls import include, path, re_path
from django.views.static import serve
from wagtail import urls as wagtail_urls
from wagtail.admin import urls as wagtailadmin_urls
from wagtail.documents import urls as wagtaildocs_urls

from django.views.decorators.cache import cache_page

from apps.archive import views as archive_views
from apps.core.sitemaps import SITEMAPS

admin.site.site_header = "IGLC administration"
admin.site.site_title = "IGLC administration"

def robots_txt(request):
    if settings.SITE_NOINDEX:
        return HttpResponse("User-agent: *\nDisallow: /\n", content_type="text/plain")
    sitemap = request.build_absolute_uri("/sitemap.xml")
    return HttpResponse(f"User-agent: *\nDisallow: /manage/\nDisallow: /cms/\n\nSitemap: {sitemap}\n",
                        content_type="text/plain")


urlpatterns = [
    path("robots.txt", robots_txt),
    path("sitemap.xml", cache_page(6 * 3600)(sitemap_views.index), {"sitemaps": SITEMAPS,
         "sitemap_url_name": "sitemap_section"}),
    path("sitemap-<section>.xml", cache_page(6 * 3600)(sitemap_views.sitemap), {"sitemaps": SITEMAPS},
         name="sitemap_section"),
    path("manage/", admin.site.urls),
    # Before the CMS's own logout, which would go to the CMS login page.
    path("cms/logout/", LogoutView.as_view(next_page="/"), name="cms_logout"),
    path("cms/", include(wagtailadmin_urls)),
    path("documents/", include(wagtaildocs_urls)),
    path("", archive_views.home, name="home"),
    path("", include("apps.archive.urls")),
    path("", include("apps.governance.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
elif settings.SERVE_MEDIA:
    urlpatterns += [re_path(r"^media/(?P<path>.*)$", serve, {"document_root": settings.MEDIA_ROOT})]

# Wagtail serves the CMS pages; it must come last because it matches any path.
urlpatterns += [path("", include(wagtail_urls))]
