from django.contrib import admin

from .models import Committee, Seat


class SeatInline(admin.TabularInline):
    model = Seat
    extra = 1
    fields = ("first_name", "last_name", "role", "is_chair", "affiliation", "country", "start_date", "end_date",
              "person", "note")
    raw_id_fields = ("person",)


@admin.register(Committee)
class CommitteeAdmin(admin.ModelAdmin):
    list_display = ("name", "charter_section", "order", "current_count")
    prepopulated_fields = {"slug": ("name",)}
    inlines = [SeatInline]

    @admin.display(description="serving now")
    def current_count(self, obj):
        return obj.seats.current().count()


@admin.register(Seat)
class SeatAdmin(admin.ModelAdmin):
    list_display = ("last_name", "first_name", "committee", "role", "is_chair", "start_date", "end_date")
    list_filter = ("committee", "role")
    search_fields = ("last_name", "first_name", "affiliation")
    raw_id_fields = ("person",)
