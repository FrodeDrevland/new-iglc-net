# new-iglc-net

The rebuild of [iglc.net](https://www.iglc.net), the website of the International Group for Lean Construction (IGLC).

The current site (ASP.NET MVC 5, 2014) is being replaced by a Django and Wagtail platform. The new platform covers the proceedings archive, a manuscript pipeline and proceedings build, Crossref deposits, conference sites on conference.iglc.net, membership and governance, and later submission and review.

The overhaul plan is a living document: [iglc.net overhaul plan](https://claude.ai/code/artifact/4eba9a7d-936c-4caa-affb-cbefeb7f422d).

## Status

Phase 1 (rebuild the foundation) is under way. See `todo.md`.

What works so far:

- The proceedings archive: conference list, conference pages, paper pages with Google Scholar metadata, PDF and presentation links, ranked search with filters, author pages, and BibTeX and RIS exports. After importing papers, run `python manage.py group_authors` to build the author pages.
- Every old URL pattern redirects to its new address, and paper and conference URLs keep their paths (`docs/url-inventory.md`).
- One back office at `/manage/` (Wagtail): pages, the archive, committees, proceedings production and users. Django's admin at `/django-admin/` is a superuser-only fallback.
- A script to inventory the live site and the Crossref-registered URLs, and to check the new site against them (`tools/url_inventory.py`).

## Run it locally (Windows, PowerShell)

Requires Python 3.10 or later. Calling the virtual environment's own `python` avoids mixing up several Python installations.

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
copy .env.example .env
.venv\Scripts\python manage.py migrate
.venv\Scripts\python manage.py test apps
.venv\Scripts\python manage.py import_legacy inventory\iglc_db-2026-9-23-18-7.bacpac --replace   # or load_demo_data
.venv\Scripts\python manage.py createsuperuser
.venv\Scripts\python manage.py runserver
```

Then open http://localhost:8000 and the back office at http://localhost:8000/manage/.

With Docker instead: `copy .env.example .env`, then `docker compose up`, and run the same `manage.py` commands with `docker compose exec web python manage.py ...`.

## Fonts

The site uses Source Serif 4 and Source Sans 3, served from `static/fonts/` rather than from Google.
To (re)build them: download both families from fonts.google.com ("Get font" > "Download all"), then

```powershell
.venv\Scripts\python -m pip install fonttools brotli
.venv\Scripts\python tools\build_fonts.py <Source_Serif_4.zip> <Source_Sans_3.zip>
```

## Layout

| Path | What it is |
| --- | --- |
| `config/` | Settings and top-level URLs |
| `apps/archive/` | Papers, authors, conferences, volumes, links; old-URL redirects (`legacy.py`); exports |
| `apps/pages/` | Wagtail page types for content pages |
| `apps/governance/` | Committees and officers |
| `apps/core/` | Health check and host redirects for hosting |
| `templates/`, `static/` | Templates, CSS and fonts |
| `tools/url_inventory.py` | URL inventory and checking, standard library only |
| `docs/url-inventory.md` | Every old URL and where it goes |
| `docs/deploy-azure.md` | Production on Azure App Service, deployment from GitHub, backups |
| `docs/switch-over.md` | Checklist for moving iglc.net to the new site |
| `docs/handover.md` | The accounts behind the site and how to hand them over |
| `docs/deploy-unraid.md` | The preview on a home server |

## Related folders

- Legacy site: `My Drive (frode@drevcon.com)/80. Koding/Visual Studio/IGLC`
- Existing proceedings scripts: `My Drive (frode@drevcon.com)/80. Koding/IGLC-Proceedings`
