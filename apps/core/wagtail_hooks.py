from django.urls import include, path, reverse
from wagtail import hooks
from wagtail.admin.menu import MenuItem

from . import help_views


@hooks.register("register_admin_urls")
def register_help_urls():
    return [path("site-help/", include(help_views))]


@hooks.register("register_help_menu_item")
def site_documentation_menu_item():
    return MenuItem("Site documentation", reverse("site_help:index"), icon_name="doc-full", order=900)
