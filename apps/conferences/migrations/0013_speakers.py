"""Speakers belong to the conference, not to a keynotes page: the keynotes page type goes, and a Speakers
block shows them on any ordinary page.

- The model Keynote becomes Speaker (the programme's sessions keep their links), with the conference, a
  group ("Keynote speakers" for the ones there are) and "not yet announced".
- (0014) Every keynotes page becomes an ordinary page, with its introduction and a Speakers block; its address,
  place in the menu and publication stay as they were. So do its old revisions.
- The standard page "Keynotes" becomes an ordinary page with a Speakers block.
"""

import django.db.models.deletion
from django.db import migrations, models

GROUP = "Keynote speakers"


def fill_conference(apps, schema_editor):
    Speaker = apps.get_model("conferences", "Speaker")
    Page = apps.get_model("wagtailcore", "Page")
    Home = apps.get_model("conferences", "ConferenceHomePage")
    for speaker in Speaker.objects.all():
        page = Page.objects.get(pk=speaker.page_id)
        home = None
        path = page.path
        while len(path) > 4 and home is None:
            path = path[:-4]
            parent = Page.objects.filter(path=path).first()
            home = Home.objects.filter(pk=parent.pk).first() if parent else None
        if home is None:
            speaker.delete()  # a keynotes page outside a conference site: nothing to keep it for
            continue
        speaker.conference_id = home.conference_id
        speaker.group = GROUP
        speaker.save()


class Migration(migrations.Migration):
    dependencies = [
        ("conferences", "0012_committee_layouts"),
        ("archive", "0001_initial"),
        ("programme", "0005_slides"),  # its sessions link to Keynote, renamed here
    ]

    operations = [
        migrations.RenameModel("Keynote", "Speaker"),
        migrations.AddField(
            model_name="speaker", name="conference",
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE,
                                    related_name="speakers", to="archive.conference"),
        ),
        migrations.AddField(
            model_name="speaker", name="group",
            field=models.CharField(blank=True, default="Keynote speakers", max_length=120,
                                   help_text="For example 'Keynote speakers' or 'Industry day speakers'. A Speakers "
                                             "block shows one group, or all of them."),
        ),
        migrations.AddField(
            model_name="speaker", name="hidden",
            field=models.BooleanField(default=False, verbose_name="not yet announced",
                                      help_text="Kept off the website until it is unticked."),
        ),
        migrations.RunPython(fill_conference, migrations.RunPython.noop),
        migrations.RemoveField(model_name="speaker", name="page"),
        migrations.AlterField(
            model_name="speaker", name="conference",
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="speakers",
                                    to="archive.conference"),
        ),
    ]
