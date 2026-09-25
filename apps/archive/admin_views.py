"""The archive in the back office (Wagtail admin): papers, authors (people), links.

Replaces Django's admin for everyday editing. Child records are edited on their parent's page:
authors on the paper. The conference record is edited under Conferences (apps/conferences)."""

from django import forms
from django.db.models import Count, Q
from django.utils import timezone
from wagtail.admin.forms import WagtailAdminModelForm
from wagtail.admin.panels import FieldPanel, FieldRowPanel, HelpPanel, InlinePanel, MultiFieldPanel, ObjectList
from wagtail.admin.ui.tables import Column
from wagtail.admin.views.generic import chooser as chooser_views
from wagtail.admin.views.generic.models import CreateView, EditView, IndexView
from wagtail.admin.viewsets.chooser import ChooserViewSet
from wagtail.admin.viewsets.model import ModelViewSet, ModelViewSetGroup

from .models import Author, AuthorPerson, LinkCategory, Paper


# ---------------------------------------------------------------- who edited last

class TrackedCreateView(CreateView):
    def save_instance(self):
        self.form.instance.last_edited_at, self.form.instance.last_edited_by = timezone.now(), self.request.user
        return super().save_instance()


class TrackedEditView(EditView):
    def save_instance(self):
        self.form.instance.last_edited_at, self.form.instance.last_edited_by = timezone.now(), self.request.user
        return super().save_instance()


# ---------------------------------------------------------------- choosing a person

class PersonSearchForm(forms.Form):
    q = forms.CharField(label="Search", required=False)

    def filter(self, objects):
        query = self.cleaned_data.get("q", "").strip() if self.is_valid() else ""
        for word in query.split():
            objects = objects.filter(Q(last_name__icontains=word) | Q(first_name__icontains=word) | Q(orcid__icontains=word))
        return objects

    @property
    def is_searching(self):
        return bool(self.is_valid() and self.cleaned_data.get("q"))

    @property
    def search_query(self):
        return self.cleaned_data.get("q") if self.is_valid() else ""

    is_filtering_by_collection = False


class PersonChooseView(chooser_views.ChooseView):
    filter_form_class = PersonSearchForm


class PersonChooseResultsView(chooser_views.ChooseResultsView):
    filter_form_class = PersonSearchForm


class PersonChooserViewSet(ChooserViewSet):
    model = AuthorPerson
    icon = "user"
    choose_one_text = "Choose a person"
    choose_another_text = "Choose another person"
    edit_item_text = "Edit this person"
    choose_view_class = PersonChooseView
    choose_results_view_class = PersonChooseResultsView
    per_page = 30


person_chooser = PersonChooserViewSet("archive_person_chooser", url_prefix="archive/person-chooser")
PersonChooser = person_chooser.widget_class


# ---------------------------------------------------------------- conferences

# The conference record's list, edit form and dashboard are under Conferences → All conferences
# (apps/conferences/admin_views.py), which uses TrackedCreateView and TrackedEditView above.


# ---------------------------------------------------------------- papers

class PaperForm(WagtailAdminModelForm):
    """Tracks and volumes of the paper's own conference only."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        conference = self.instance.conference_id or self.data.get("conference") or self.initial.get("conference")
        for name in ("track", "volume"):
            if name in self.fields:
                field = self.fields[name]
                field.queryset = field.queryset.filter(conference=conference) if conference else field.queryset.none()


class PaperIndexView(IndexView):
    def get_base_queryset(self):
        return super().get_base_queryset().select_related("conference")


class PaperViewSet(ModelViewSet):
    model = Paper
    menu_label = "Papers"
    icon = "doc-full"
    index_view_class = PaperIndexView
    add_view_class = TrackedCreateView
    edit_view_class = TrackedEditView
    list_display = ["title", Column("authors_text", label="Authors"), Column("conference", label="Conference"),
                    "first_page", "doi"]
    list_filter = ["conference", "status"]
    search_fields = ["title", "doi", "authors_text"]
    list_per_page = 50
    inspect_view_enabled = False
    edit_handler = ObjectList([
        FieldPanel("title"),
        MultiFieldPanel([
            FieldRowPanel([FieldPanel("conference"), FieldPanel("track")]),
            FieldPanel("volume"),
            FieldRowPanel([FieldPanel("first_page"), FieldPanel("last_page"), FieldPanel("doi"), FieldPanel("status")]),
        ], heading="Where it is published", help_text="Tracks and volumes: save the paper after changing the conference."),
        InlinePanel("authors", heading="Authors", label="Author",
                    panels=[FieldRowPanel([FieldPanel("order"), FieldPanel("first_name"), FieldPanel("last_name")]),
                            FieldPanel("title_and_contact"), FieldPanel("person", widget=PersonChooser)]),
        FieldPanel("abstract"),
        FieldPanel("keywords"),
        HelpPanel(template="archive/admin/paper_files.html", heading="Files"),
    ], base_form_class=PaperForm)


# ---------------------------------------------------------------- people

class PersonForm(WagtailAdminModelForm):
    merge = forms.ModelChoiceField(
        queryset=AuthorPerson.objects.all(), required=False, widget=PersonChooser,
        label="Merge another person into this one",
        help_text="Their papers move to this person, and the other person is deleted when you save. "
                  "(To split a person, open the paper and choose another person for its author.)")

    def clean_merge(self):
        other = self.cleaned_data.get("merge")
        if other and other.pk == self.instance.pk:
            raise forms.ValidationError("That is this person.")
        return other

    def save(self, commit=True):
        person = super().save(commit)
        other = self.cleaned_data.get("merge")
        if other and commit:
            Author.objects.filter(person=other).update(person=person)
            if not person.orcid and other.orcid:
                person.orcid = other.orcid
                person.save(update_fields=["orcid"])
            other.delete()
        return person


class PersonIndexView(IndexView):
    def get_base_queryset(self):
        return super().get_base_queryset().annotate(papers=Count("authorships__paper", distinct=True))


class AuthorPersonViewSet(ModelViewSet):
    model = AuthorPerson
    menu_label = "Authors"
    icon = "user"
    index_view_class = PersonIndexView
    list_display = ["last_name", "first_name", "orcid", Column("papers", label="Papers", sort_key="papers")]
    search_fields = ["last_name", "first_name", "orcid"]
    list_per_page = 50
    inspect_view_enabled = False
    edit_handler = ObjectList([
        FieldRowPanel([FieldPanel("first_name"), FieldPanel("last_name"), FieldPanel("orcid")]),
        HelpPanel(template="archive/admin/person_papers.html", heading="Papers"),
        FieldPanel("merge"),
    ], base_form_class=PersonForm)


# ---------------------------------------------------------------- links

class LinkCategoryViewSet(ModelViewSet):
    model = LinkCategory
    menu_label = "Links"
    icon = "link"
    list_display = ["name", "sort_order"]
    inspect_view_enabled = False
    panels = [
        FieldRowPanel([FieldPanel("name"), FieldPanel("sort_order")]),
        FieldPanel("description"),
        InlinePanel("links", heading="Links", label="Link",
                    panels=[FieldRowPanel([FieldPanel("name"), FieldPanel("sort_order")]), FieldPanel("url"),
                            FieldPanel("description")]),
    ]


class ArchiveGroup(ModelViewSetGroup):
    menu_label = "Archive"
    menu_icon = "folder-inverse"
    menu_order = 200
    items = [
        PaperViewSet("archive_paper", url_prefix="archive/paper"),
        AuthorPersonViewSet("archive_person", url_prefix="archive/person"),
        LinkCategoryViewSet("archive_links", url_prefix="archive/links"),
    ]
