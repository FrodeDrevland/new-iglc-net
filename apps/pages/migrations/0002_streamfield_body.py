import wagtail.blocks
import wagtail.fields
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("pages", "0001_initial"),
    ]

    operations = [
        migrations.AlterField(
            model_name="standardpage",
            name="body",
            field=wagtail.fields.StreamField(
                [
                    ("text", wagtail.blocks.RichTextBlock(features=[
                        "h2", "h3", "h4", "bold", "italic", "superscript", "subscript", "ol", "ul", "hr",
                        "link", "document-link", "image", "embed",
                    ])),
                    ("html", wagtail.blocks.RawHTMLBlock(
                        help_text="Raw HTML, for tables and embedded forms that the text editor cannot hold.")),
                ],
                blank=True,
            ),
        ),
        migrations.AddField(
            model_name="standardpage",
            name="show_child_pages",
            field=models.BooleanField(
                default=True, help_text="List the pages below this one at the end of the page."
            ),
        ),
    ]
