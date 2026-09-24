from django.contrib import admin, messages
from django.db.models import Count
from django.utils import timezone

from .models import (
    Author, AuthorPerson, Conference, ConferenceTrack, Editor, Link, LinkCategory, Paper, ProceedingsFile, Volume,
)


class TrackedAdmin(admin.ModelAdmin):
    readonly_fields = ("last_edited_at", "last_edited_by")

    def save_model(self, request, obj, form, change):
        obj.last_edited_at = timezone.now()
        obj.last_edited_by = request.user
        super().save_model(request, obj, form, change)


class EditorInline(admin.TabularInline):
    model = Editor
    extra = 0


class ProceedingsFileInline(admin.TabularInline):
    model = ProceedingsFile
    extra = 0


class TrackInline(admin.TabularInline):
    model = ConferenceTrack
    extra = 0


class VolumeInline(admin.TabularInline):
    model = Volume
    extra = 0
    exclude = ("last_edited_at", "last_edited_by")


@admin.register(Conference)
class ConferenceAdmin(TrackedAdmin):
    list_display = ("number", "city", "country", "start_date", "is_published")
    list_filter = ("is_published",)
    search_fields = ("city", "country", "conference_title", "proceedings_title")
    inlines = [EditorInline, VolumeInline, ProceedingsFileInline, TrackInline]
    actions = ["make_production"]

    @admin.action(description="Make the full proceedings here (take the published papers into production)")
    def make_production(self, request, queryset):
        from django.contrib import messages

        from apps.production.adopt import AdoptError, adopt_published

        for conference in queryset:
            try:
                production, report = adopt_published(conference, request.user)
                self.message_user(request, f"{production}: {report['added']} papers taken from the archive, "
                                           f"{report['updated']} updated. Open it under Proceedings production.")
            except AdoptError as error:
                self.message_user(request, f"{conference}: {error}", messages.ERROR)


class AuthorInline(admin.TabularInline):
    model = Author
    extra = 0
    fields = ("order", "first_name", "last_name", "title_and_contact", "person")
    raw_id_fields = ("person",)


@admin.register(Paper)
class PaperAdmin(TrackedAdmin):
    list_display = ("title", "conference", "first_page", "doi", "status")
    list_filter = ("status", "conference")
    search_fields = ("title", "doi", "authors__last_name")
    raw_id_fields = ("volume", "track")
    inlines = [AuthorInline]


class AuthorshipInline(admin.TabularInline):
    model = Author
    fk_name = "person"
    fields = ("paper", "first_name", "last_name")
    readonly_fields = ("paper", "first_name", "last_name")
    extra = 0
    can_delete = False
    verbose_name_plural = "authorships (to split a person, set another person on the paper's author)"

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(AuthorPerson)
class AuthorPersonAdmin(admin.ModelAdmin):
    list_display = ("last_name", "first_name", "orcid", "paper_count")
    search_fields = ("last_name", "first_name", "orcid")
    actions = ["merge_people"]
    inlines = [AuthorshipInline]

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(_papers=Count("authorships__paper", distinct=True))

    @admin.display(description="papers", ordering="_papers")
    def paper_count(self, obj):
        return obj._papers

    @admin.action(description="Merge the selected people into one")
    def merge_people(self, request, queryset):
        people = sorted(queryset, key=lambda p: (-p._papers, p.pk))
        if len(people) < 2:
            self.message_user(request, "Select two or more people to merge.", messages.WARNING)
            return
        keep, others = people[0], people[1:]
        Author.objects.filter(person__in=others).update(person=keep)
        if not keep.orcid:
            keep.orcid = next((p.orcid for p in others if p.orcid), "")
            keep.save(update_fields=["orcid"])
        AuthorPerson.objects.filter(pk__in=[p.pk for p in others]).delete()
        self.message_user(request, f"Merged {len(others)} into {keep.first_name} {keep.last_name}.",
                          messages.SUCCESS)


class LinkInline(admin.TabularInline):
    model = Link
    extra = 0


@admin.register(LinkCategory)
class LinkCategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "sort_order")
    inlines = [LinkInline]
