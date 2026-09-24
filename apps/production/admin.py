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


# ---------------------------------------------------------------- proceedings production

from .models import PaperVersion, ProceedingsVolume, Submission, VolumeEditor  # noqa: E402


class VolumeEditorInline(admin.TabularInline):
    model = VolumeEditor
    extra = 1
    autocomplete_fields = ("user",)

    def get_formset(self, request, obj=None, **kwargs):
        self._volume = obj
        return super().get_formset(request, obj, **kwargs)

    def formfield_for_manytomany(self, db_field, request, **kwargs):
        if db_field.name == "tracks":
            from apps.archive.models import ConferenceTrack

            volume = getattr(self, "_volume", None)
            kwargs["queryset"] = (ConferenceTrack.objects.filter(conference=volume.conference)
                                  if volume else ConferenceTrack.objects.none())
        return super().formfield_for_manytomany(db_field, request, **kwargs)


@admin.register(ProceedingsVolume)
class ProceedingsVolumeAdmin(admin.ModelAdmin):
    list_display = ("__str__", "status", "paper_count", "approved_count")
    inlines = [VolumeEditorInline]

    @admin.display(description="papers")
    def paper_count(self, obj):
        return obj.submissions.exclude(status=Submission.Status.WITHDRAWN).count()

    @admin.display(description="approved")
    def approved_count(self, obj):
        return obj.submissions.filter(status=Submission.Status.APPROVED).count()


class PaperVersionInline(admin.TabularInline):
    model = PaperVersion
    extra = 0
    fields = ("number", "uploaded", "uploaded_by", "docx", "pdf", "pages", "passed", "comment")
    readonly_fields = fields
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Submission)
class SubmissionAdmin(admin.ModelAdmin):
    list_display = ("conftool_id", "title", "track", "status", "editor", "first_page")
    list_filter = ("volume", "status", "track")
    search_fields = ("conftool_id", "title")
    list_select_related = ("track", "editor")
    raw_id_fields = ("paper",)
    readonly_fields = ("doi",)
    inlines = [PaperVersionInline]

    def get_form(self, request, obj=None, **kwargs):
        self._submission = obj
        return super().get_form(request, obj, **kwargs)

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "track" and getattr(self, "_submission", None):
            from apps.archive.models import ConferenceTrack

            kwargs["queryset"] = ConferenceTrack.objects.filter(conference=self._submission.volume.conference)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)
