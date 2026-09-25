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
- [x] Old user accounts: mostly bots, not migrated; people register anew on the new site
- [ ] Self-registration with protection against bots (email confirmation, rate limiting, honeypot field), when accounts have a use (phase 4 or 5)
- [x] Fix page ranges of papers 1647 and 1978 (first page after last page), and paper 1157
- [x] Full proceedings PDFs and ZIP downloads on conference pages (`link_blob_files`)
- [ ] Run `link_blob_files` and `link_full_proceedings` (docs/content-files.md), locally and on the preview
- [ ] Crossref deposit XML export in the new site, needed by July 2027 (IGLC 35 deposits); until then the old admin is used
- [x] Search: Postgres full-text search with ranking, year and conference filters, highlighting, paging
- [x] Author pages (AuthorPerson) with ORCID, co-authors; `group_authors` command and admin merge
- [ ] Review author grouping in the admin (merge "G. Ballard" style variants)
- [x] CMS content ported to Wagtail pages (`import_legacy_pages`)
- [x] Links page generated from the link database (`/links/`)
- [ ] Review the imported pages; some are out of date (IGLC33 templates, the 34th conference page)
- [ ] New visual design
- [x] Preview deployment files for Unraid behind SWAG (`docs/deploy-unraid.md`)
- [x] Deploy the preview at https://iglc.drevland.net
- [ ] Mailing list sign-up form (Sender.net) does not appear on the preview; check the form's allowed domains in Sender, or replace it in phase 4
- [ ] Production hosting decision (IGLC-controlled)
- [ ] Working version to show before switch-over

## Governance (pulled forward from phase 4)

- [x] Committees and officers page at /about/committees/, managed under Manage → Governance
- [x] Current officers and committee members loaded (`load_committee_members`, data in apps/governance/data/members.csv)
- [ ] Control Committee: second member and the two spares
- [ ] Exact ABM dates for 2029 (placeholder 1 July)

## Production on Azure

- [x] Container start script, health check, apex-to-www redirect, blob storage for uploads, logging
- [x] GitHub Actions: tests on PostgreSQL, deploy to App Service on push to main
- [x] docs/deploy-azure.md, docs/switch-over.md, docs/handover.md
- [ ] Create the Azure resources (deploy-azure.md steps 1-6) and copy the data (step 7)
- [ ] Fill in the unknowns in docs/handover.md (registrar, DNS, Crossref, Sender.net)
- [ ] Email for password resets and error reports (SMTP settings)
- [ ] Switch-over (docs/switch-over.md)

## Phase 2: manuscript pipeline

- [x] Read metadata from Word files by the template's styles (apps/production/docx_reader.py); tried on all 156 IGLC 34 camera-ready files
- [x] `read_manuscripts` command: problem report per file, comparison with the archive
- [x] Fixed HTML entities (&amp;) stored in titles, abstracts and affiliations
- [x] Write running headers, footers and first page number into papers (apps/production/stamp.py)
- [x] Page counts: LibreOffice differs from Word for 1 in 6 papers (also with the real fonts); page counts and PDFs come from Word (tools/word_batch.ps1)
- [x] Tried tools/word_batch.ps1 on the stamped IGLC 34 files: Word's page count matches the editors' for 156/156; the PDFs for 155/156 (131 came out one page longer). Page counts must be taken from the PDFs, and checked again after stamping
- [x] Data model: proceedings volume, editors, submissions, file versions; ConfTool import (step 1)
- [x] Step 2: editors' upload (batch and single), check report, metadata, page count, versions
- [ ] Step 3: arranging (order of tracks and papers, page numbers)
- [ ] Upload page for camera-ready files, with the problem report shown to the author
- [ ] Metadata check page for authors (confirm or correct title, authors, affiliations, ORCIDs)
- [ ] Proceedings PDF: front matter, table of contents, page numbering, headers/footers
- [ ] Crossref deposit XML
- [ ] Email: Azure Communication Services Email with iglc.net as custom domain (needs DNS access)
## Phase 3, step 2: the conference programme (docs/programme.md)

- [x] Step 1, back office: parts with editor groups, locations with map links, sessions, people, papers as talks or posters, checks, programme block on the conference pages
- [ ] Start the IGLC 35 programme on the preview and production; add the chairs and deans to their groups; add the Programme block to the existing IGLC 35 programme page
- [x] Step 2, registration backing: registration import, the two-paper rule, authors' confirmation links, warnings, withdrawal
- [ ] Email on iglc.net (SMTP settings), needed before the authors can be asked
- [x] Step 3, public programme: day, session, location and part views, grid on large screens, private link for non-public parts
- [ ] Step 4, at the venue: program.iglc.net, now and next, my programme, calendar files and feeds, QR room signs, change marks
- [ ] Step 5, later: PDF booklet, offline, drag-and-drop planning, slide uploads

