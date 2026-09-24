"""XML sitemap for search engines, including Google Scholar.

/sitemap.xml is an index pointing to one sitemap per section. Addresses use the host and scheme
of the request, so the same code serves the preview and www.iglc.net.
"""

from django.contrib.sitemaps import Sitemap
from django.db.models import Count
from django.urls import reverse
from wagtail.models import Page

from apps.archive.models import AuthorPerson, Conference, Paper


class PaperSitemap(Sitemap):
    changefreq = "yearly"
    priority = 0.8
    limit = 5000

    def items(self):
        return Paper.objects.filter(conference__is_published=True).only("pk", "last_edited_at").order_by("pk")

    def lastmod(self, paper):
        return paper.last_edited_at


class ConferenceSitemap(Sitemap):
    changefreq = "yearly"
    priority = 0.7

    def items(self):
        return Conference.objects.filter(is_published=True).order_by("-number")

    def lastmod(self, conference):
        return conference.last_edited_at


class AuthorSitemap(Sitemap):
    changefreq = "yearly"
    priority = 0.4
    limit = 5000

    def items(self):
        return (AuthorPerson.objects.annotate(n=Count("authorships")).filter(n__gt=0)
                .only("pk").order_by("pk"))


class ListingSitemap(Sitemap):
    """Pages made by views rather than the CMS."""

    changefreq = "monthly"
    priority = 0.6

    def items(self):
        return ["archive:conference_list", "archive:authors", "archive:links", "governance:committees"]

    def location(self, name):
        return reverse(name)


class PageSitemap(Sitemap):
    """The CMS pages (about, charter, for authors, conference pages...).

    Wagtail's own sitemap takes the host name from the Wagtail Site record; this one uses the
    request's, like the other sections. The CMS home page is left out: "/" is the archive home.
    """

    changefreq = "monthly"
    priority = 0.5

    def items(self):
        from wagtail.models import Site

        site = Site.objects.filter(is_default_site=True).first()
        pages = Page.objects.live().public().filter(depth__gt=2)
        if site:  # the conference sites have their own sitemap
            pages = pages.descendant_of(site.root_page)
        return pages.order_by("path")

    def location(self, page):
        return page.get_url_parts()[2]

    def lastmod(self, page):
        return page.last_published_at


SITEMAPS = {
    "pages": PageSitemap,
    "listings": ListingSitemap,
    "conferences": ConferenceSitemap,
    "papers": PaperSitemap,
    "authors": AuthorSitemap,
}
