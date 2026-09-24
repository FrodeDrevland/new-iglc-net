from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    """'Volume' is the archive's word for a published book, so the production models are renamed."""

    dependencies = [
        ("production", "0002_production_volumes"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("archive", "0007_track_order"),
    ]

    operations = [
        migrations.RenameModel("ProceedingsVolume", "Production"),
        migrations.RenameModel("VolumeEditor", "ProductionEditor"),
        migrations.RenameField("submission", "volume", "production"),
        migrations.RenameField("productioneditor", "volume", "production"),
        migrations.AlterModelOptions("production", {"ordering": ["-conference__number"],
                                                   "verbose_name": "proceedings production"}),
        migrations.AlterUniqueTogether("productioneditor", {("production", "user")}),
        migrations.AlterUniqueTogether("submission", {("production", "conftool_id")}),
        migrations.AlterModelOptions("submission", {"ordering": ["production", "track__order", "position", "conftool_id"]}),
        migrations.AlterField(
            model_name="productioneditor", name="user",
            field=models.ForeignKey(on_delete=models.deletion.CASCADE, related_name="production_roles",
                                    to=settings.AUTH_USER_MODEL)),
    ]
