"""URL inventory for iglc.net.

Builds the list of URLs the new site must keep working, and checks a new site against it.
Uses only the Python standard library, so it runs anywhere Python 3.9+ is installed.

Commands
--------
crawl     Crawl the live site and record every internal URL found.
crossref  List every DOI under the IGLC prefix (10.24928) and the URL it points to.
check     Request every URL from one or more inventory files against a new site
          and report the ones that do not end in a working page.

Examples
--------
python tools/url_inventory.py crawl --out inventory/crawl.csv
python tools/url_inventory.py crossref --mailto you@example.org --out inventory/crossref.csv
python tools/url_inventory.py check inventory/crawl.csv inventory/crossref.csv \
    --base http://localhost:8000 --out inventory/check-report.csv
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import deque
from html.parser import HTMLParser
from pathlib import Path

USER_AGENT = "iglc-url-inventory/1.0 (+https://www.iglc.net)"
DEFAULT_START = "https://www.iglc.net/"
SITE_HOSTS = {"iglc.net", "www.iglc.net"}
CANONICAL_ORIGIN = "https://www.iglc.net"
CROSSREF_PREFIX = "10.24928"

# Recorded when found, but never requested: they need a login, change data or are expensive.
DO_NOT_FETCH_PREFIXES = (
    "/admin",
    "/account",
    "/datapunching",
    "/authors",
    "/papers/edit",
    "/papers/resetfriendlyfilename",
    "/papers/export",
)


class _LinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[str] = []
        self.title = ""
        self._in_title = False

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "a" and attrs.get("href"):
            self.links.append(attrs["href"])
        elif tag == "form" and attrs.get("action"):
            self.links.append(attrs["action"])
        elif tag == "title":
            self._in_title = True

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False

    def handle_data(self, data):
        if self._in_title:
            self.title += data.strip()


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


_opener = urllib.request.build_opener(_NoRedirect)


def fetch(url: str, timeout: float = 30.0, method: str = "GET"):
    """Request a URL without following redirects. Returns (status, headers, body)."""
    request = urllib.request.Request(url, method=method, headers={"User-Agent": USER_AGENT})
    try:
        with _opener.open(request, timeout=timeout) as response:
            return response.status, response.headers, response.read()
    except urllib.error.HTTPError as error:
        return error.code, error.headers, error.read() if error.fp else b""
    except (urllib.error.URLError, TimeoutError, ConnectionError) as error:
        return 0, {}, str(error).encode()


def normalise(url: str, base: str) -> str | None:
    """Absolute URL on the canonical origin without fragment, or None if external."""
    absolute = urllib.parse.urljoin(base, url.strip())
    parts = urllib.parse.urlsplit(absolute)
    if parts.scheme not in ("http", "https"):
        return None
    if parts.hostname not in SITE_HOSTS:
        return None
    path = parts.path or "/"
    query = f"?{parts.query}" if parts.query else ""
    return f"{CANONICAL_ORIGIN}{path}{query}"


# Pages behind a login on the old site; the new site replaces them rather than keeping them.
NOT_CHECKED_PREFIXES = DO_NOT_FETCH_PREFIXES[:6]


def _skip_fetch(url: str, prefixes: tuple[str, ...] = DO_NOT_FETCH_PREFIXES) -> bool:
    path = urllib.parse.urlsplit(url).path.lower()
    return any(path.startswith(prefix) for prefix in prefixes)


def crawl(start: str, max_pages: int, delay: float, out: Path) -> int:
    queue: deque[tuple[str, str]] = deque([(normalise(start, start), "")])
    seen: set[str] = {queue[0][0]}
    rows: list[dict] = []
    fetched = 0

    while queue and fetched < max_pages:
        url, source = queue.popleft()
        if _skip_fetch(url):
            rows.append({"url": url, "status": "", "location": "", "content_type": "",
                         "title": "", "found_on": source, "note": "not fetched"})
            continue

        status, headers, body = fetch(url)
        fetched += 1
        location = headers.get("Location", "") if headers else ""
        content_type = headers.get("Content-Type", "") if headers else ""
        row = {"url": url, "status": status, "location": location, "content_type": content_type,
               "title": "", "found_on": source, "note": ""}

        if location:
            target = normalise(location, url)
            if target is None:
                row["note"] = "redirects off site"
            elif target not in seen:
                seen.add(target)
                queue.append((target, url))
        elif status == 200 and "html" in content_type:
            parser = _LinkParser()
            parser.feed(body.decode("utf-8", errors="replace"))
            row["title"] = parser.title[:200]
            for link in parser.links:
                target = normalise(link, url)
                if target and target not in seen:
                    seen.add(target)
                    queue.append((target, url))
        rows.append(row)

        if fetched % 50 == 0:
            print(f"{fetched} fetched, {len(queue)} queued", file=sys.stderr)
        time.sleep(delay)

    for url, source in queue:
        rows.append({"url": url, "status": "", "location": "", "content_type": "",
                     "title": "", "found_on": source, "note": "not reached (max pages)"})

    _write_csv(out, rows, ["url", "status", "location", "content_type", "title", "found_on", "note"])
    print(f"Crawl finished: {fetched} fetched, {len(rows)} URLs recorded in {out}", file=sys.stderr)
    return 0


def _get_json(url: str) -> dict:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.load(response)


def crossref(mailto: str, out: Path, rows_per_page: int = 1000) -> int:
    base = f"https://api.crossref.org/prefixes/{CROSSREF_PREFIX}/works"
    cursor = "*"
    rows: list[dict] = []
    while True:
        params = {"rows": rows_per_page, "cursor": cursor}
        if mailto:
            params["mailto"] = mailto
        data = _get_json(f"{base}?{urllib.parse.urlencode(params)}")["message"]
        items = data.get("items", [])
        for item in items:
            issued = item.get("issued", {}).get("date-parts", [[None]])[0][0]
            rows.append({
                "doi": item.get("DOI", ""),
                "type": item.get("type", ""),
                "resource_url": item.get("resource", {}).get("primary", {}).get("URL", ""),
                "year": issued or "",
                "title": " ".join(item.get("title", []))[:300],
            })
        print(f"{len(rows)} of {data.get('total-results')} DOIs", file=sys.stderr)
        cursor = data.get("next-cursor")
        if not items or not cursor:
            break
        time.sleep(1)

    _write_csv(out, rows, ["doi", "type", "resource_url", "year", "title"])
    print(f"Wrote {len(rows)} DOIs to {out}", file=sys.stderr)
    return 0


def _urls_from(path: Path) -> list[str]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        column = "resource_url" if "resource_url" in (reader.fieldnames or []) else "url"
        return [row[column] for row in reader if row.get(column)]


def check(files: list[Path], base: str, out: Path, delay: float) -> int:
    base = base.rstrip("/")
    urls: list[str] = []
    for path in files:
        for url in _urls_from(path):
            parts = urllib.parse.urlsplit(url)
            if parts.hostname in SITE_HOSTS and not _skip_fetch(url, NOT_CHECKED_PREFIXES):
                urls.append(url)
    urls = list(dict.fromkeys(urls))

    rows, failures = [], 0
    for url in urls:
        parts = urllib.parse.urlsplit(url)
        current = base + parts.path + (f"?{parts.query}" if parts.query else "")
        chain = []
        status = 0
        for _ in range(6):
            status, headers, _ = fetch(current, method="GET")
            chain.append(f"{status} {current}")
            location = headers.get("Location") if headers else None
            if status in (301, 302, 303, 307, 308) and location:
                current = urllib.parse.urljoin(current, location)
                if urllib.parse.urlsplit(current).netloc != urllib.parse.urlsplit(base).netloc:
                    status = 200  # hands over to file storage or another host
                    chain.append(f"off site {current}")
                    break
                continue
            break
        ok = status == 200
        failures += not ok
        rows.append({"old_url": url, "ok": ok, "final_status": status, "chain": " -> ".join(chain)})
        time.sleep(delay)

    _write_csv(out, rows, ["old_url", "ok", "final_status", "chain"])
    print(f"Checked {len(rows)} URLs: {len(rows) - failures} working, {failures} failing. Report: {out}",
          file=sys.stderr)
    return 1 if failures else 0


def _write_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    p_crawl = sub.add_parser("crawl", help="crawl the live site")
    p_crawl.add_argument("--start", default=DEFAULT_START)
    p_crawl.add_argument("--max-pages", type=int, default=20000)
    p_crawl.add_argument("--delay", type=float, default=0.3, help="seconds between requests")
    p_crawl.add_argument("--out", type=Path, default=Path("inventory/crawl.csv"))

    p_cr = sub.add_parser("crossref", help="list DOIs registered under the IGLC prefix")
    p_cr.add_argument("--mailto", default="", help="contact email for Crossref's polite pool")
    p_cr.add_argument("--out", type=Path, default=Path("inventory/crossref.csv"))

    p_check = sub.add_parser("check", help="check a new site against inventory files")
    p_check.add_argument("files", nargs="+", type=Path)
    p_check.add_argument("--base", required=True, help="for example http://localhost:8000")
    p_check.add_argument("--delay", type=float, default=0.0)
    p_check.add_argument("--out", type=Path, default=Path("inventory/check-report.csv"))

    args = parser.parse_args(argv)
    if args.command == "crawl":
        return crawl(args.start, args.max_pages, args.delay, args.out)
    if args.command == "crossref":
        return crossref(args.mailto, args.out)
    return check(args.files, args.base, args.out, args.delay)


if __name__ == "__main__":
    sys.exit(main())
