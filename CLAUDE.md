# Context for AI-assisted work on new-iglc-net

## What this is
A rebuild of iglc.net for the International Group for Lean Construction (IGLC). Frode Drevland is the general secretary and webmaster, and the main developer.
The full plan: https://claude.ai/code/artifact/4eba9a7d-936c-4caa-affb-cbefeb7f422d (read it before larger changes).

## Decisions made
- Stack: Python, Django (current LTS), Wagtail, Postgres, a background worker (Celery or Django-Q2), Docker. htmx rather than a JavaScript framework.
- One Django project with apps: archive, pages, production, crossref, conferences, submissions, accounts, community (membership, mailing list, governance).
- Six phases: 1 foundation (port archive and admin, migrate data, keep URLs), 2 production tools, 3 conference sites (with the conference programme, possibly on program.iglc.net), 4 membership and governance, 5 submission and review (its own mini-site), 6 students and the PhD summer school (applications separate from paper submission; a student mini-site such as student.iglc.net).
- Metadata is extracted from the DOCX using the template's paragraph styles (python-docx), not from the PDF.
- Workflow: publish papers on iglc.net, authors check their metadata, then proceedings build and Crossref deposit.
- conference.iglc.net serves the current conference; conference.iglc.net/<year>/ holds each year's site.
- Registration and payment are out of scope.
- The member register and the mailing list are separate; unsubscribing does not affect the right to vote.
- Old user accounts (4,760, mostly bots) are not migrated; people create new accounts. Registration must be protected against bots.
- Governance follows the IGLC Charter and Operating Procedures: https://www.iglc.net/Home/CharterAndOperatingProcedures

## Hard constraints
- Never break existing URLs: /papers/details/{id} and /papers/conference/{id} (with /pdf and /presentation), case-insensitive. DOIs point to them.
- Keep existing database IDs for papers, authors and conferences when migrating.
- Use permissively licensed libraries only (pypdf, pikepdf, pdfplumber, Typst, WeasyPrint). No AGPL (PyMuPDF, iText).
- Copyright: papers' copyright is transferred to the proceedings editors; papers may be freely distributed in their original form (see /copyright/ and /for-authors/copyright-policy/). Do not label papers with a Creative Commons licence. Charter section 11.4 (CC BY-NC-SA 3.0 or stricter) covers IGLC's own intellectual property; how it applies to site content is for the IGLC to decide.
- The member register must never be shared; restrict and log access.

## Writing conventions
- British English in all user-facing text and documentation. The committee is the "Standardisation Committee".
- No em dashes in text; use spaced en dashes sparingly for asides.

## Legacy code
The old site is in Frode's Google Drive under 80. Koding/Visual Studio/IGLC (ASP.NET MVC 5, EF6, SQL Server, Azure App Service and Blob Storage). Useful references: Models/*.cs, Helpers/CrossrefXmlCreator.cs, Areas/Admin/Controllers/ImportController.cs and ProceedingsController.cs.

## Working notes
- One back office: Wagtail's admin at /manage/. Conferences, archive, committees and production are Wagtail viewsets (apps/*/admin_views.py, wagtail_hooks.py); the production pages extend templates/production/editor/_base.html. Django's admin at /django-admin/ is a superuser-only fallback: do not build new features there.
- Fresh checkouts need `python manage.py makemigrations archive pages` once; commit the generated migrations.
- Conference websites (apps/conferences, docs/conference-sites.md): Wagtail pages in a second Wagtail Site at CONFERENCE_HOST (conference.<site host>), with their own URLconf (config/conference_urls.py) set by ConferenceHostMiddleware. Templates there must not reverse main-site URL names; link to the main site with main_site_url.
- Conferences in the back office (apps/conferences; docs/conference-sites.md): the IGLC administration's menu "Conferences" (hook register_conferences_menu_item, admin_views.py) holds All conferences (the archive's Conference model: list and edit form), Programmes, Proceedings production and Website standard pages. Each conference has a workspace at /manage/<number>/ (workspace.py builds its sidebar through construct_main_menu; workspace_views.py: overview, website, branding, people, actions). Roles per conference are in roles.py (groups "IGLC nn …"); people with only conference roles never see the full menu. Delete a conference only through its delete view (it cascades through Wagtail's page delete; a plain CASCADE on the foreign key would break the page tree).
- Conference programme (apps/programme, docs/programme.md): its own back-office pages under /manage/programme/ (function views like the production's). Permissions come from groups per conference: conference chairs, organisers (locations only) and one editors group per part; see apps/programme/access.py.
- archive get_absolute_url() reverses with ROOT_URLCONF so it works on the conference host too; prefix it with main_site_url there.
- Old-URL redirects live in apps/archive/legacy.py; the full route list is docs/url-inventory.md. Update both together.
- Documents in docs/ can be read in the back office (Help → Site documentation). A new document must be added to DOCS in apps/core/help.py, with who may read it (everyone, editors, superusers); a test checks every listed file exists. Write them in CommonMark (markdown-it-py renders them).
- tools/url_inventory.py uses only the standard library; run it where iglc.net and api.crossref.org are reachable.
