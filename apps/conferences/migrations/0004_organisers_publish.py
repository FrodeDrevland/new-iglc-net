"""Organisers publish their own conference's pages: add the publish permission to the existing
organiser groups, on the pages they already edit."""

from django.db import migrations


def add(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")
    GroupPagePermission = apps.get_model("wagtailcore", "GroupPagePermission")
    publish = Permission.objects.filter(content_type__app_label="wagtailcore", codename="publish_page").first()
    if publish is None:
        return
    for group in Group.objects.filter(name__startswith="IGLC ", name__endswith=" organisers"):
        for gpp in GroupPagePermission.objects.filter(group=group, permission__codename="change_page"):
            GroupPagePermission.objects.get_or_create(group=group, page_id=gpp.page_id, permission=publish)


class Migration(migrations.Migration):
    dependencies = [("conferences", "0003_standard_pages_data"), ("wagtailcore", "0001_initial")]
    operations = [migrations.RunPython(add, migrations.RunPython.noop)]
