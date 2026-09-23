from django.contrib import admin
from django.utils import timezone

from .models import Author, AuthorPerson, Conference, ConferenceTrack, Editor, Link, LinkCategory, Paper, Volume


class TrackedAdmin(admin.ModelAdmin):
    readonly_fields = ("last_edited_at", "last_edited_by")

    def save_model(self, request, obj, form, change):
        obj.last_edited_at = timezone.now()
        obj.last_edited_by = request.user
        super().save_model(request, obj, form, change)


class EditorInline(admin.TabularInline):
    model = Editor
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
    inlines = [EditorInline, VolumeInline, TrackInline]


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


@admin.register(AuthorPerson)
class AuthorPersonAdmin(admin.ModelAdmin):
    list_display = ("last_name", "first_name", "orcid")
    search_fields = ("last_name", "first_name", "orcid")


class LinkInline(admin.TabularInline):
    model = Link
    extra = 0


@admin.register(LinkCategory)
class LinkCategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "sort_order")
    inlines = [LinkInline]
