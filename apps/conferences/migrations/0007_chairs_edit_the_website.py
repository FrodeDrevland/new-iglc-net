"""Conference chairs edit and publish their conference's website, like the organisers: every existing
conference website gets the group "IGLC nn conference chairs" (also the programme's chairs group),
with the same page and collection permissions as "IGLC nn organisers"."""

from django.db import migrations

PAGE = ("add_page", "change_page", "publish_page")
COLLECTION = {"wagtailimages": ("add_image", "change_image", "choose_image"),
              "wagtaildocs": ("add_document", "change_document", "choose_document")}


def add(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")
    Home = apps.get_model("conferences", "ConferenceHomePage")
    Collection = apps.get_model("wagtailcore", "Collection")
    GroupPagePermission = apps.get_model("wagtailcore", "GroupPagePermission")
    GroupCollectionPermission = apps.get_model("wagtailcore", "GroupCollectionPermission")
    access = Permission.objects.filter(content_type__app_label="wagtailadmin", codename="access_admin").first()
    for home in Home.objects.select_related("conference"):
        number = home.conference.number
        group, _ = Group.objects.get_or_create(name=f"IGLC {number} conference chairs")
        if access:
            group.permissions.add(access)
        for codename in PAGE:
            permission = Permission.objects.filter(content_type__app_label="wagtailcore", codename=codename).first()
            if permission:
                GroupPagePermission.objects.get_or_create(group=group, page_id=home.pk, permission=permission)
        folder = Collection.objects.filter(depth=2, name=f"IGLC {number}").first()
        if folder is None:
            continue
        for app, codenames in COLLECTION.items():
            for codename in codenames:
                permission = Permission.objects.filter(content_type__app_label=app, codename=codename).first()
                if permission:
                    GroupCollectionPermission.objects.get_or_create(group=group, collection=folder,
                                                                    permission=permission)


class Migration(migrations.Migration):
    dependencies = [("conferences", "0006_standard_programme_page"), ("wagtailcore", "0001_initial"),
                    ("wagtailimages", "0001_initial"), ("wagtaildocs", "0001_initial")]
    operations = [migrations.RunPython(add, migrations.RunPython.noop)]
