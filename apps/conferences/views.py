from django.conf import settings
from django.http import HttpResponse
from django.shortcuts import render
from wagtail.models import Page, Site

from .setup import index_page


def robots_txt(request):
    if settings.SITE_NOINDEX:
        return HttpResponse("User-agent: *\nDisallow: /\n", content_type="text/plain")
    return HttpResponse(f"User-agent: *\nDisallow:\n\nSitemap: {request.build_absolute_uri('/sitemap.xml')}\n",
                        content_type="text/plain")


def sitemap(request):
    index = index_page(create=False)
    pages = Page.objects.live().public().descendant_of(index, inclusive=True).order_by("path") if index else []
    site = Site.find_for_request(request)
    lines = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for page in pages:
        relative = page.get_url_parts(request)
        if not relative or (site and relative[0] != site.pk):
            continue
        lines.append(f"<url><loc>{request.build_absolute_uri(relative[2])}</loc>"
                     + (f"<lastmod>{page.last_published_at:%Y-%m-%d}</lastmod>" if page.last_published_at else "")
                     + "</url>")
    lines.append("</urlset>")
    return HttpResponse("\n".join(lines), content_type="application/xml")


def not_found(request, exception=None):
    return render(request, "conferences/404.html", {"main_site_url": settings.SITE_URL}, status=404)
