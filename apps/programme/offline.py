"""Working offline at the venue: a service worker that keeps the programme's pages, so that they
open without a network (conference Wi-Fi fails). On program.iglc.net it covers the whole host; on
the conference site the pages under /<year>/programme/.

Pages are fetched from the network when it is there (so they are current) and kept; without a
network the kept copy is shown. When the programme changes, the worker's version changes and the
browser fetches every page again."""

from __future__ import annotations

import json

from django.db.models import Max
from django.http import HttpResponse
from django.templatetags.static import static

from . import public
from .models import Session

WORKER = """/* IGLC programme offline (apps/programme/offline.py) */
const VERSION = %(version)s;
const PAGES = %(pages)s;
const CACHE = "iglc-programme-" + VERSION;

self.addEventListener("install", event => {
  event.waitUntil(caches.open(CACHE).then(cache =>
    Promise.all(PAGES.map(url => cache.add(new Request(url, {credentials: "same-origin"})).catch(() => null)))
  ).then(() => self.skipWaiting()));
});

self.addEventListener("activate", event => {
  event.waitUntil(caches.keys().then(keys => Promise.all(
    keys.filter(key => key.startsWith("iglc-programme-") && key !== CACHE).map(key => caches.delete(key))
  )).then(() => self.clients.claim()));
});

self.addEventListener("fetch", event => {
  const request = event.request;
  if (request.method !== "GET" || new URL(request.url).origin !== self.location.origin) return;
  event.respondWith(fetch(request).then(response => {
    if (response.ok && response.type === "basic") {
      const copy = response.clone();
      caches.open(CACHE).then(cache => cache.put(request, copy));
    }
    return response;
  }).catch(() => caches.match(request).then(found => found || caches.match(request, {ignoreSearch: true}))
    .then(found => found || new Response("<!DOCTYPE html><meta name=viewport content='width=device-width'>" +
      "<p style='font:1.1rem system-ui;padding:1rem'>You are offline, and this page was not kept. " +
      "Go back to the programme.</p>", {headers: {"Content-Type": "text/html; charset=utf-8"}}))));
});
"""


def version(programme) -> str:
    latest = programme.sessions.aggregate(latest=Max("updated"))["latest"]
    stamps = [programme.updated, latest]
    return "-".join(str(int(s.timestamp())) for s in stamps if s)


def _statics():
    return [static("css/site.css"), static("css/conference.css"), static("js/programme.js"),
            static("fonts/source-sans-3-var.woff2"), static("fonts/source-serif-4-var.woff2")]


def worker(programme, pages) -> HttpResponse:
    body = WORKER % {"version": json.dumps(version(programme)), "pages": json.dumps(pages + _statics())}
    response = HttpResponse(body, content_type="application/javascript; charset=utf-8")
    response["Cache-Control"] = "no-cache"
    return response


def venue_pages(programme) -> list[str]:
    days = sorted(set(programme.sessions.filter(part__public=True).values_list("date", flat=True)))
    return ["/", "/today/", "/my/"] + [f"/today/?day={d:%Y-%m-%d}" for d in days]


def conference_pages(programme, year) -> list[str]:
    sessions = programme.sessions.filter(part__public=True).exclude(kind__in=[Session.Kind.BREAK, Session.Kind.MEAL])
    days = sorted(set(programme.sessions.filter(part__public=True).values_list("date", flat=True)))
    pages = [f"/{year}/programme/", public.url("now", year), public.url("today", year), public.url("my", year)]
    pages += [public.url("day", year, f"{d:%Y-%m-%d}") for d in days]
    pages += [public.url("session", year, pk) for pk in sessions.values_list("pk", flat=True)]
    pages += [public.url("location", year, pk) for pk in
              programme.locations.filter(sessions__part__public=True).distinct().values_list("pk", flat=True)]
    return pages
