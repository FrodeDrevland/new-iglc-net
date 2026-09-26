"""Programmes whose days were far from their conference's dates (e.g. started while the conference
had other dates) get the conference's days, widened only to keep days that have sessions."""

from django.db import migrations
from django.db.models import Max, Min

MARGIN_DAYS = 31


def forwards(apps, schema_editor):
    Programme = apps.get_model("programme", "Programme")
    for programme in Programme.objects.select_related("conference"):
        conference = programme.conference
        if not conference.start_date:
            continue
        end = conference.end_date or conference.start_date
        found = programme.sessions.aggregate(first=Min("date"), last=Max("date"))
        first = min(d for d in [conference.start_date, found["first"]] if d)
        last = max(d for d in [end, found["last"]] if d)
        changed = False
        if not (0 <= (conference.start_date - programme.first_day).days <= MARGIN_DAYS) or programme.first_day > first:
            programme.first_day, changed = first, True
        if not (0 <= (programme.last_day - end).days <= MARGIN_DAYS) or programme.last_day < last:
            programme.last_day, changed = last, True
        if changed:
            programme.save(update_fields=["first_day", "last_day"])


class Migration(migrations.Migration):
    dependencies = [("programme", "0008_meals_without_room")]
    operations = [migrations.RunPython(forwards, migrations.RunPython.noop)]
