from wagtail import hooks
from wagtail.admin.menu import MenuItem


@hooks.register("register_admin_menu_item")
def view_site_link():
    return MenuItem("View site", "/", icon_name="site", order=100000)
