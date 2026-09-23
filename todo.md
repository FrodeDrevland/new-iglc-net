# To do

## Phase 1: rebuild the foundation
- [x] Route inventory from the legacy code (`docs/url-inventory.md`)
- [x] URL inventory script: crawl, Crossref and check (`tools/url_inventory.py`)
- [x] Crawl and Crossref inventory (`inventory/`)
- [ ] Move the 19 files under `/Content/Proceedings/` and `/Content/Documents/` to storage, and redirect the old paths
- [ ] Check papers 55, 422 and 2226 (server errors on the old site) render on the new site
- [ ] Run `url_inventory.py check` against the local site
- [x] Django and Wagtail skeleton with the archive app; models ported from the legacy C# classes
- [x] Old-URL redirects and exports
- [ ] First local run: `makemigrations`, `migrate`, `test`; commit the migrations
- [ ] Repository on GitHub
- [x] Get a copy of the production database (.bacpac in inventory/, not in Git)
- [x] Repeatable import from the .bacpac, keeping IDs, with count checks (`import_legacy`)
- [ ] Decide what to do with the 4,760 old user accounts (only 1 admin and 26 punchers have roles; none are imported)
- [ ] Fix page ranges of papers 1647 and 1978 (first page after last page)
- [ ] Full proceedings PDFs and ZIP downloads on conference pages (blob containers `proceedings` and `papers-zipped`)
- [ ] Postgres full-text search for the archive
- [ ] Author pages (AuthorPerson) with ORCID
- [ ] CMS content ported to Wagtail pages with the slugs in `docs/url-inventory.md`
- [ ] New visual design
- [ ] Hosting decision and test deployment
- [ ] Working version to show before switch-over
