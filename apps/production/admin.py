from django.contrib import admin

from .models import PaperCheck


@admin.register(PaperCheck)
class PaperCheckAdmin(admin.ModelAdmin):
    list_display = ("created", "short_id", "file_name", "stage", "passed", "title")
    list_filter = ("stage", "passed")
    search_fields = ("file_name", "title", "sha256", "id")
    readonly_fields = [f.name for f in PaperCheck._meta.fields]

    def has_add_permission(self, request):
        return False
