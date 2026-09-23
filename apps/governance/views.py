from django.shortcuts import render

from .models import Committee


def committees(request):
    groups = []
    for committee in Committee.objects.all():
        current = sorted(committee.current_seats(), key=lambda s: s.sort_key)
        groups.append({"committee": committee, "current": current, "past": committee.past_seats()})
    return render(request, "governance/committees.html", {"groups": groups})
