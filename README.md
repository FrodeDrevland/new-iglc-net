# new-iglc-net

The rebuild of [iglc.net](https://www.iglc.net), the website of the International Group for Lean Construction (IGLC).

The current site (ASP.NET MVC 5, 2014) is being replaced by a Django and Wagtail platform. The new platform covers the proceedings archive, a manuscript pipeline and proceedings build, Crossref deposits, conference sites on conference.iglc.net, membership and governance, and later submission and review.

The overhaul plan is a living document: [iglc.net overhaul plan](https://claude.ai/code/artifact/4eba9a7d-936c-4caa-affb-cbefeb7f422d).

## Status

Phase 1 (rebuild the foundation) is under way. See `todo.md`.

What works so far:

- The proceedings archive: conference list, conference pages, paper pages with Google Scholar metadata, PDF and presentation links, search, and BibTeX and RIS exports.
- Every old URL pattern redirects to its new address, and paper and conference URLs keep their paths (`docs/url-inventory.md`).
- Django admin for the archive at `/manage/`, and Wagtail for content pages at `/cms/`.
- A script to inventory the live site and the Crossref-registered URLs, and to check the new site against them (`tools/url_inventory.py`).

## Run it locally (Windows, PowerShell)

Requires Python 3.12 (3.10 or later works).

```powershell
py -3.12 -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
python manage.py makemigrations archive pages   # first time only; commit the new migration files
python manage.py migrate
python manage.py createsuperuser
python manage.py load_demo_data                 # fictional conferences 901 and 902
python manage.py test apps
python manage.py runserver
```

Then open http://localhost:8000, the archive admin at http://localhost:8000/manage/ and the CMS at http://localhost:8000/cms/.

With Docker instead: `copy .env.example .env`, then `docker compose up`, and run the same `manage.py` commands with `docker compose exec web python manage.py ...`.

## Layout

| Path | What it is |
| --- | --- |
| `config/` | Settings and top-level URLs |
| `apps/archive/` | Papers, authors, conferences, volumes, links; old-URL redirects (`legacy.py`); exports |
| `apps/pages/` | Wagtail page types for content pages |
| `templates/`, `static/` | Templates and CSS (a placeholder design) |
| `tools/url_inventory.py` | URL inventory and checking, standard library only |
| `docs/url-inventory.md` | Every old URL and where it goes |

## Related folders

- Legacy site: `My Drive (frode@drevcon.com)/80. Koding/Visual Studio/IGLC`
- Existing proceedings scripts: `My Drive (frode@drevcon.com)/80. Koding/IGLC-Proceedings`
