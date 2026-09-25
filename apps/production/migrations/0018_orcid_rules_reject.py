"""Bad and duplicate ORCID iDs become Reject at camera-ready and at the editors' upload (Crossref
refuses such records). Rows still at the old default (Warn) are changed; edited ones are left."""

from django.db import migrations


def reject(apps, schema_editor):
    CheckRule = apps.get_model("production", "CheckRule")
    for rule in CheckRule.objects.filter(code__in=["orcid_invalid", "orcid_duplicate"]):
        changed = False
        for stage in ("camera_ready", "production"):
            if getattr(rule, stage) == "warn":
                setattr(rule, stage, "reject")
                changed = True
        if changed:
            rule.save()


class Migration(migrations.Migration):
    dependencies = [("production", "0017_check_limits_more")]
    operations = [migrations.RunPython(reject, migrations.RunPython.noop)]
