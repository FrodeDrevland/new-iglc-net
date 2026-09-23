# To do

## Phase 1: rebuild the foundation
- [x] Route inventory from the legacy code (`docs/url-inventory.md`)
- [x] URL inventory script: crawl, Crossref and check (`tools/url_inventory.py`)
- [ ] Run the crawl and Crossref inventory on a machine that can reach iglc.net; commit the CSV files to `inventory/`
- [x] Django and Wagtail skeleton with the archive app; models ported from the legacy C# classes
- [x] Old-URL redirects and exports
- [ ] First local run: `makemigrations`, `migrate`, `test`; commit the migrations
- [ ] Repository on GitHub
- [ ] Get a copy of the production database (SQL Server on Azure) for the migration script
- [ ] Repeatable migration script from SQL Server to Postgres, keeping IDs, with automatic checks
- [ ] Full proceedings PDFs and ZIP downloads on conference pages (blob containers `proceedings` and `papers-zipped`)
- [ ] Postgres full-text search for the archive
- [ ] Author pages (AuthorPerson) with ORCID
- [ ] CMS content ported to Wagtail pages with the slugs in `docs/url-inventory.md`
- [ ] New visual design
- [ ] Hosting decision and test deployment
- [ ] Working version to show before switch-over
