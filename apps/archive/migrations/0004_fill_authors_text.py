from django.db import migrations


def fill(apps, schema_editor):
    Paper = apps.get_model("archive", "Paper")
    Author = apps.get_model("archive", "Author")
    names = {}
    for a in Author.objects.order_by("paper_id", "order", "pk").values("paper_id", "first_name", "last_name"):
        names.setdefault(a["paper_id"], []).append(f"{a['first_name']} {a['last_name']}")
    for paper_id, parts in names.items():
        Paper.objects.filter(pk=paper_id).update(authors_text=" ".join(parts))


class Migration(migrations.Migration):
    dependencies = [("archive", "0003_paper_authors_text")]
    operations = [migrations.RunPython(fill, migrations.RunPython.noop)]
