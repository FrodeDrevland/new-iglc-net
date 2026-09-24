# Context for AI-assisted work on new-iglc-net

## What this is
A rebuild of iglc.net for the International Group for Lean Construction (IGLC). Frode Drevland is the general secretary and webmaster, and the main developer.
The full plan: https://claude.ai/code/artifact/4eba9a7d-936c-4caa-affb-cbefeb7f422d (read it before larger changes).

## Decisions made
- Stack: Python, Django (current LTS), Wagtail, Postgres, a background worker (Celery or Django-Q2), Docker. htmx rather than a JavaScript framework.
- One Django project with apps: archive, pages, production, crossref, conferences, submissions, accounts, community (membership, mailing list, governance).
- Five phases: 1 foundation (port archive and admin, migrate data, keep URLs), 2 production tools, 3 conference sites, 4 membership and governance, 5 submission and review.
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
- One back office: Wagtail's admin at /manage/. Archive, committees and production are Wagtail viewsets (apps/*/admin_views.py, wagtail_hooks.py); the production pages extend templates/production/editor/_base.html. Django's admin at /django-admin/ is a superuser-only fallback: do not build new features there.
- Fresh checkouts need `python manage.py makemigrations archive pages` once; commit the generated migrations.
- Old-URL redirects live in apps/archive/legacy.py; the full route list is docs/url-inventory.md. Update both together.
- tools/url_inventory.py uses only the standard library; run it where iglc.net and api.crossref.org are reachable.
