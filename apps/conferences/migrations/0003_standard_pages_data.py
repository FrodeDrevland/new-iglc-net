"""The standard pages a new conference website starts with, as they were set in code before
they became editable (Settings → Conference standard pages)."""

import uuid

from django.conf import settings
from django.db import migrations

PAGES = [
    # (type, title, slug, intro, body)
    ("ConferencePage", "Call for papers", "call-for-papers", "Topics, submission and review.",
     [("text", "<p>Describe the conference theme and the topics, how to submit an abstract and a paper, and how "
               "papers are reviewed. Link to the IGLC's <a href=\"{main}/for-authors/\">guidelines for authors</a> "
               "and <a href=\"{main}/for-authors/templates/\">templates</a>.</p>"),
      ("tracks", None)]),
    ("ConferencePage", "Important dates", "important-dates", "", [("important_dates", None)]),
    ("ConferencePage", "Programme", "programme", "The programme is published when the sessions are set.",
     [("text", "<p>The programme will be published here.</p>")]),
    ("KeynotesPage", "Keynotes", "keynotes", "", []),
    ("CommitteesPage", "Committees", "committees", "", []),
    ("AcceptedPapersPage", "Accepted papers", "accepted-papers", "", []),
    ("ConferencePage", "Venue and travel", "venue-and-travel", "",
     [("text", "<p>The venue, how to get there, and where to stay.</p>")]),
    ("ConferencePage", "Registration", "registration", "",
     [("text", "<p>Fees, what they include, and the deadlines for early registration.</p>")]),
    ("SponsorsPage", "Sponsors", "sponsors", "", []),
]


def add(apps, schema_editor):
    Template = apps.get_model("conferences", "StandardPageTemplate")
    main = getattr(settings, "SITE_URL", "https://www.iglc.net")
    for order, (page_type, title, slug, intro, body) in enumerate(PAGES):
        if Template.objects.filter(slug=slug).exists():
            continue
        Template.objects.create(
            page_type=page_type, title=title, slug=slug, intro=intro, sort_order=order,
            body=[{"type": kind, "value": value.format(main=main) if isinstance(value, str) else value,
                   "id": str(uuid.uuid4())} for kind, value in body])


class Migration(migrations.Migration):
    dependencies = [("conferences", "0002_standard_page_templates")]
    operations = [migrations.RunPython(add, migrations.RunPython.noop)]
