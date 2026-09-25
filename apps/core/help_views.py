from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import render
from django.urls import path

from . import help


@login_required
def index(request):
    groups = {}
    for doc in help.readable(request.user):
        groups.setdefault(doc.group, []).append((doc, help.title(doc)))
    guide = request.user.is_superuser or help.is_editor(request.user)
    return render(request, "core/help/index.html", {"groups": groups, "editors_guide": guide})


@login_required
def doc(request, slug):
    item = help.BY_SLUG.get(slug)
    if item is None or not help.can_read(request.user, item):
        raise Http404
    title, body, toc = help.read(item)
    return render(request, "core/help/doc.html", {
        "doc": item, "title": title, "body": help.link_docs(body, request.user), "toc": toc,
    })


app_name = "site_help"
urlpatterns = [
    path("", index, name="index"),
    path("<slug:slug>/", doc, name="doc"),
]
