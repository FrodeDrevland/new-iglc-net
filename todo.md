# To do

## Phase 1: rebuild the foundation
- [x] Route inventory from the legacy code (`docs/url-inventory.md`)
- [x] URL inventory script: crawl, Crossref and check (`tools/url_inventory.py`)
- [x] Crawl and Crossref inventory (`inventory/`)
- [x] Redirect `/Content/...` to blob storage
- [x] Upload the old Content folders to the `content` blob container (`docs/content-files.md`)
- [x] Check papers 55, 422 and 2226 (server errors on the old site) render on the new site
- [x] `url_inventory.py check` against the local site: every paper, conference, PDF, export and Crossref URL works; after the Links page and the Content upload, only the 9 links already broken on the old site fail
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
- [x] CMS content ported to Wagtail pages (`import_legacy_pages`)
- [x] Links page generated from the link database (`/links/`)
- [ ] Review the imported pages; some are out of date (IGLC33 templates, the 34th conference page)
- [ ] New visual design
- [x] Preview deployment files for Unraid behind SWAG (`docs/deploy-unraid.md`)
- [ ] Deploy the preview at https://iglc.drevland.net
- [ ] Production hosting decision (IGLC-controlled)
- [ ] Working version to show before switch-over
