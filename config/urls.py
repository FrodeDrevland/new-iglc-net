from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from wagtail import urls as wagtail_urls
from wagtail.admin import urls as wagtailadmin_urls
from wagtail.documents import urls as wagtaildocs_urls

from apps.archive import views as archive_views

admin.site.site_header = "IGLC administration"
admin.site.site_title = "IGLC administration"

urlpatterns = [
    path("manage/", admin.site.urls),
    path("cms/", include(wagtailadmin_urls)),
    path("documents/", include(wagtaildocs_urls)),
    path("", archive_views.home, name="home"),
    path("", include("apps.archive.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

# Wagtail serves the CMS pages; it must come last because it matches any path.
urlpatterns += [path("", include(wagtail_urls))]
