from django.db import migrations

COMMITTEES = [
    ("Officers", "officers", "", "§8", 0,
     "The General Secretary and the Moderator are elected by the Annual Business Meeting. The Former General "
     "Secretary serves for two years after their term as General Secretary."),
    ("Standardisation Committee", "standardisation-committee", "", "§9.2", 1,
     "The Standardisation Committee creates and maintains the IGLC standards and advises the General Secretary. "
     "It is chaired by the General Secretary and has twelve members: the General Secretary, the Former General "
     "Secretary, the Moderator and nine elected members. Each year the Annual Business Meeting elects three "
     "members for a three-year term."),
    ("Control Committee", "control-committee", "", "§9.1", 2,
     "The Control Committee ensures that the IGLC follows its charter, operating procedures and standards. It has "
     "two members and two spares. Each year the Annual Business Meeting elects one member and one spare for a "
     "two-year term."),
]


def create(apps, schema_editor):
    Committee = apps.get_model("governance", "Committee")
    for name, slug, _, section, order, description in COMMITTEES:
        Committee.objects.get_or_create(slug=slug, defaults={
            "name": name, "charter_section": section, "order": order, "description": description})


class Migration(migrations.Migration):
    dependencies = [("governance", "0001_initial")]
    operations = [migrations.RunPython(create, migrations.RunPython.noop)]
