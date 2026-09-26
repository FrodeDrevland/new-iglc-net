"""Which pages a conference website has is the IGLC's standard: the organisers and conference chairs no
longer add pages (roles.PAGE_PERMISSIONS). They keep editing and publishing the pages that are there."""

import re

from django.db import migrations


def remove(apps, schema_editor):
    GroupPagePermission = apps.get_model("wagtailcore", "GroupPagePermission")
    pattern = re.compile(r"^IGLC \d+ (organisers|conference chairs)$")
    for permission in GroupPagePermission.objects.filter(permission__codename="add_page").select_related("group"):
        if pattern.match(permission.group.name):
            permission.delete()


class Migration(migrations.Migration):
    dependencies = [("conferences", "0014_speakers_block"), ("wagtailcore", "0094_alter_page_locale")]
    operations = [migrations.RunPython(remove, migrations.RunPython.noop)]
