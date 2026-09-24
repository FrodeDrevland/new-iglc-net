"""Group the author entries on papers into people (AuthorPerson), for the author pages.

Entries are the same person when they share an ORCID (found in the affiliation text), or
when the last name and the first given name match after removing accents and case
"Glenn Ballard" and "H. Glenn Ballard" only match through an ORCID; the admin has a merge
action for what this misses, and a person is split by setting another person on an author).

    python manage.py group_authors            # only entries without a person
    python manage.py group_authors --reset    # rebuild all people (keeps no manual merges)
"""

import re
import unicodedata
from collections import Counter, defaultdict

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.archive.models import Author, AuthorPerson

ORCID = re.compile(r"(\d{4}-\d{4}-\d{4}-\d{3}[\dX])")


def fold(text: str) -> str:
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"[^a-z ]+", " ", text.lower().replace("ø", "o").replace("æ", "ae").replace("ß", "ss")).strip()


def name_key(first: str, last: str) -> str | None:
    last_f = " ".join(fold(last or first).split())
    first_tokens = [t for t in fold(first if last else "").split() if t]
    if not last_f:
        return None
    # A single name (mononym) is its own key.
    return f"{last_f}|{first_tokens[0]}" if first_tokens else f"{last_f}|"


def surname(text: str) -> str:
    words = fold(text).split()
    return words[-1] if words else ""


def orcids_in(author) -> list[str]:
    return ORCID.findall(author.title_and_contact or "")


def orcid_owners(authors) -> dict[str, str]:
    """ORCID -> the last name it belongs to.

    Affiliation texts sometimes carry a co-author's ORCID too, so an ORCID only counts for
    entries with the last name it most often appears with.
    """
    seen = defaultdict(Counter)
    for author in authors:
        for orcid in orcids_in(author):
            seen[orcid][surname(author.last_name)] += 1
    return {orcid: names.most_common(1)[0][0] for orcid, names in seen.items()}


def make_orcid_of(owners):
    def orcid_of(author):
        last = surname(author.last_name)
        return next((o for o in orcids_in(author) if owners.get(o) == last), None)
    return orcid_of


class _Union:
    def __init__(self):
        self.parent = {}

    def find(self, x):
        self.parent.setdefault(x, x)
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a, b):
        self.parent[self.find(a)] = self.find(b)


class Command(BaseCommand):
    help = "Group author entries into people for the author pages."

    def add_arguments(self, parser):
        parser.add_argument("--reset", action="store_true", help="delete all people and group again")

    @transaction.atomic
    def handle(self, *args, reset=False, **options):
        if reset:
            Author.objects.update(person=None)
            AuthorPerson.objects.all().delete()

        people_by_key, people_by_orcid = {}, {}
        for person in AuthorPerson.objects.all():
            key = name_key(person.first_name, person.last_name)
            if key:
                people_by_key.setdefault(key, person)
            if person.orcid:
                people_by_orcid.setdefault(person.orcid, person)
        for author in Author.objects.exclude(person=None).select_related("person"):
            key = name_key(author.first_name, author.last_name)
            if key:
                people_by_key.setdefault(key, author.person)

        todo = list(Author.objects.filter(person=None))
        orcid_of = make_orcid_of(orcid_owners(Author.objects.exclude(title_and_contact="")))
        groups = _Union()
        for author in todo:
            node = ("a", author.pk)
            groups.find(node)
            key = name_key(author.first_name, author.last_name)
            if key:
                groups.union(node, ("k", key))
            orcid = orcid_of(author)
            if orcid:
                groups.union(node, ("o", orcid))

        members = defaultdict(list)
        for author in todo:
            members[groups.find(("a", author.pk))].append(author)

        created = assigned = 0
        for authors in members.values():
            keys = {name_key(a.first_name, a.last_name) for a in authors} - {None}
            orcids = Counter(o for o in map(orcid_of, authors) if o)
            person = next((people_by_orcid[o] for o in orcids if o in people_by_orcid), None)
            person = person or next((people_by_key[k] for k in sorted(keys) if k in people_by_key), None)
            if person is None:
                if not keys and not any(a.last_name.strip() for a in authors):
                    continue  # no name at all
                first, last = Counter((a.first_name.strip(), a.last_name.strip()) for a in authors).most_common(1)[0][0]
                person = AuthorPerson.objects.create(
                    first_name=first, last_name=last, orcid=orcids.most_common(1)[0][0] if orcids else "")
                created += 1
            elif orcids and not person.orcid:
                person.orcid = orcids.most_common(1)[0][0]
                person.save(update_fields=["orcid"])
            for key in keys:
                people_by_key.setdefault(key, person)
            Author.objects.filter(pk__in=[a.pk for a in authors]).update(person=person)
            assigned += len(authors)

        self.stdout.write(self.style.SUCCESS(
            f"{assigned} author entries assigned; {created} people created; "
            f"{AuthorPerson.objects.count()} people in total."))
