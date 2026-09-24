from django.urls import reverse
from wagtail import hooks
from wagtail.admin.menu import MenuItem


@hooks.register("register_admin_menu_item")
def archive_admin_link():
    return MenuItem("Archive (papers, conferences…)", reverse("admin:index"), icon_name="doc-full", order=10000)


@hooks.register("register_admin_menu_item")
def view_site_link():
    return MenuItem("View site", "/", icon_name="site", order=10001)
