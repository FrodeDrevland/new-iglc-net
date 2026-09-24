# Paper submission and proceedings production (2028 onwards)

The target process once IGLC runs its own submission system. The 2027 process (with ConfTool)
will be a subset of this. Agreed with the General Secretary, September 2026.

## Principles

- Word is the only program that lays papers out exactly as authors and editors see them.
  Page counts and final PDFs therefore come from Word **on Windows**, run by the editors.
- The system never asks anyone to type headers, footers, page numbers or DOIs: it adds them.
- Every uploaded file is checked automatically, with rules set per submission stage.
- Every version of every paper is kept, with who uploaded it and why.

## Automatic checks

Each check is written once in code (apps/production). An admin page sets, for each
submission stage (abstract, full paper, revised paper, camera-ready), whether a check is:

| Level | Effect |
|---|---|
| off | not run |
| note | shown to the author, no action needed |
| warn | the author must confirm "submit anyway", and is told the paper may be sent back |
| reject | the upload is refused, with what to fix |

Some checks take settings (maximum pages, maximum abstract words, maximum keywords).
Some belong to certain stages only, for example anonymisation in review stages: no author
names in the Authors style, in the file properties or in self-identifying footnotes.

Camera-ready examples: missing Title/Authors style, missing affiliation footnotes, missing
mandatory headings and changed page setup are "reject"; long title, abstract over 200 words,
more than five keywords, missing ORCID and non-template styles are "warn".

## Camera-ready to publication

1. **Author uploads the camera-ready Word file.** The checks run at once (reject / warn and
   confirm / note). The system reads title, authors, affiliations, ORCIDs, abstract and
   keywords, and the author confirms or corrects them.
2. **Track chair(s) check for major issues**, meaning anything the editors cannot fix
   without changing content (for example a table that only fits if content is removed).
   They approve, or send the paper back to the author with comments. Can be switched off
   per conference if the automatic checks prove good enough.
3. **Editor checks and edits.** Editors download their papers (one by one or as a ZIP),
   edit them in Word, and upload the edited Word file together with a PDF of it, one by one
   or as a batch (files paired by paper number). The checks run again on every upload. An
   editor can send a paper back to the author with comments. The editor sets the track and
   approves the paper.
4. **PDF.** The PDF must be made by Word for Windows: by hand (Save As PDF) or with the IGLC
   conversion tool (a script, later a small app, both downloadable from the site). Its
   headers and footers do not matter: Word marks them in the PDF, and the system removes
   them on upload (tested on IGLC 34: removed cleanly, content and page count unchanged). A
   PDF without these marks, or with anything left in the header/footer areas, is refused
   with a request to use the conversion tool. The page count is taken from this PDF.
5. **Editors arrange the proceedings:** order of tracks and of papers within tracks. Page
   numbers follow from the PDFs and update when the order changes.
6. **Publication of the papers (before the conference; this is the deadline that matters):**
   the system prints headers, footers and page numbers on each PDF (first page: full
   reference with DOI link; even pages: title and conference line; odd pages: authors and
   track), assigns DOIs and publishes every paper in the archive.
7. **Authors check the published metadata**; then the Crossref deposit is made.
8. **The full proceedings (later, not urgent):** the system joins the papers' PDFs and adds
   the cover, front matter (title page, colophon with ISSN/ISBN, foreword, committees,
   table of contents) and back matter, and publishes the full proceedings PDF. The papers'
   page numbers are fixed in step 5, so the book can follow without changing the papers.

A paper replaced after step 5 goes through step 3 again; before publication, the following
papers are renumbered automatically. After publication the page numbers are cited and never
change: a correction must fit the paper's page range (see Corrections below).

## Corrections after publication

Errors are sometimes found after the papers are published. The editor uploads the corrected
Word file and PDF on the paper's page as usual; a chief editor then publishes the correction
with a short public note on what was corrected.

- The DOI and first page stay. The corrected paper may be shorter, but not longer, than its
  published page range: the following papers' page numbers are already cited.
- The new PDF gets the same running heads; the old PDF and all versions are kept.
- The archive record is updated from the corrected Word file (title, authors, affiliations,
  abstract, keywords), and the paper's page says "Corrected <date>" with the note.
- The ZIP of all papers is rebuilt. Once the Crossref deposit exists (step 6 in the build
  list), a changed title or author list is deposited again.

## Support for editors

- A guidelines page: what to check and fix, how to convert and upload, what each check
  message means.
- The conversion tool (tools/word_batch.ps1 now): converts all Word files in a folder with
  Word, empties headers and footers first, and writes page counts. Later a small Windows app
  that also downloads and uploads.

## Headers and footers on the PDF (tested on IGLC 34)

apps/production/pdf_running.py removes Word's header and footer content from the PDF (all 156
papers) and prints new ones: same font, size and position as Word's, justified, the DOI as a
blue underlined link. Line breaks in the first-page reference match Word's in about 3 of 4
papers; the others break a word earlier or later, which is fine.

**Template requirement:** the first-page reference takes 3 to 5 lines. In Word a longer header
pushes the text down, but in the new process the PDF is made with empty headers, so the
template's first page must reserve room for 5 header lines (fixed height), or the reference
would overlap the title. The same reserved height also keeps the page count independent of
the reference's length.

## 2027: with ConfTool

ConfTool still handles submission, review and the authors' camera-ready uploads; the track
chairs' check happens outside our system. Our site starts where the editors take over, and
from there follows steps 3-7 above.

1. **Before the call for papers:** the IGLC 35 template with reserved space for the reference
   (see below); the call asks authors to run "Check your paper" and upload the PDF report
   with their camera-ready paper in ConfTool.
2. **Import from ConfTool:** the accepted papers (ConfTool ID, title, track, authors and
   their email addresses) from ConfTool's export. The Word file is the source of the
   published metadata; ConfTool's names and affiliations often differ slightly, so
   differences are shown to the editors as information, not errors. ConfTool's email
   addresses are used to reach the authors.
3. **Editors** download the papers from ConfTool (named by ConfTool ID), edit them in Word,
   make PDFs with the conversion script, and upload Word files and PDFs to the site, in
   batches or one by one. The site checks each upload, reads the metadata, removes the PDF's
   headers and footers and counts the pages. Papers can be uploaded again as often as
   needed; every version is kept.
4. **Editors** approve each paper and order tracks and papers; page numbers follow.
5. **Before the conference, the site publishes the papers:** headers, footers and page
   numbers, DOIs (10.24928/2027/ConfTool ID), and every paper in the archive.
6. **The site emails each paper's authors** a personal link to check the metadata; after the
   check, the Crossref deposit is made.
7. **Afterwards, the full proceedings:** the papers joined, with cover, front and back matter.

Needed: sending email through Azure Communication Services Email (decided; setup in
docs/deploy-azure.md, needs the iglc.net DNS), and a ConfTool export of accepted papers.

## Built so far

**Step 1 (productions, papers, editors):** apps/production/models.py

- *Production* per conference (status, first page number): the making of its proceedings.
  Not the same as a *volume*, which in the archive is a published book (older proceedings
  were printed in several); when published, the papers go into the volume(s) by page.
- *Production editors*: chief editors see and arrange everything; editors see the papers of their tracks, or all papers.
- *Submission*: an accepted paper (ConfTool ID, registered title, track, registered authors
  with email addresses, status, editor, position in its track, first page, DOI
  10.24928/year/ConfTool ID, and later the published archive paper).
- *Paper version*: every upload (Word file, PDF, page count, what was read, the check), kept.
- Tracks have an order in the proceedings.
- `import_conftool 35 export.xlsx` creates or updates the production from ConfTool's export of
  accepted papers (columns found by their headings, or named with --column);
  `import_conftool 34 --from-archive` builds one from the archive for trying out.
- Editor accounts: Manage → Settings → Users → add user; then on the production's page,
  "Editors and settings", add the person as editor or chief editor. That role is what lets them
  into the back office (no group needed). Publishers: add the user to the group "Publishers".
- New productions: Manage → Proceedings production → "Start a production", from ConfTool's
  export of accepted papers or from a conference already published (superusers and publishers).

**Step 2 (editors' upload):** /production/ (link in the admin bar)

- The production's paper list: filter by track, status or own papers; download the current
  Word files (and PDFs) of chosen papers as a ZIP named by ConfTool ID.
- Upload: any number of Word files and PDFs, or ZIP files; matched to papers by the ConfTool
  ID at the start of the name. A PDF alone goes with the paper's current Word file. Every
  upload becomes a new version, is checked (camera-ready rules, plus the PDF's layout: made by
  Word, nothing left in the header/footer areas, room for the reference on page 1), and its
  pages are counted from the PDF.
- A paper's page: the check, the metadata read from the paper next to what was registered in
  ConfTool (differences highlighted), all versions with their files, upload of a new version,
  approve / needs more work with a comment, track and editor, and the history.
- Editors see only their tracks' papers; chief editors see all. Files are private and only
  downloaded through the site.

**Step 3 (order and page numbers):** /production/<n>/arrange/

- Chief editors drag tracks and papers (also between tracks); page numbers run consecutively
  from the first page, from the PDFs' page counts, and are recalculated after every upload.
  Numbering stops at the first paper without a PDF.
- Tested on IGLC 34: in the published order, all 156 page ranges came out as in the book
  (one paper, 131, was corrected after publication and is one page shorter there).

**Step 4 (publishing the papers):** /production/<n>/publish/

- Ready when every paper is approved, has a PDF, and has its title in sentence case, and the
  conference has its dates and city. The page lists what is missing.
- *Title and names* on each paper's page: the title as the reference prints it (sentence
  case; a suggestion is made, or the editors' own header text on older files is used) and how
  each name splits into first and last name. Kept across new versions while the Word title
  and the names are unchanged.
- Publishing runs ten papers per request (the page repeats until done, and can be resumed).
  Each paper gets its archive record (matched by DOI, so publishing again updates it) and its
  PDF: Word's headers and footers removed, the IGLC running heads and page numbers printed,
  PDF metadata set. The PDF is public (papers/iglc<n>/<id>.pdf).
- From the first published paper, the order is locked. When all are published: new authors
  are linked to the people in the archive, the conference is shown in the proceedings list,
  and a ZIP of all papers is linked from its page.
- Tested on IGLC 34 (156 papers, about 0.6 s per paper, 20 s for the ZIP and author linking).
- Corrections as described above, on the paper's page.

**Roles**

- *Editors* (per production): the papers of their tracks, or all papers.
- *Chief editors* (per production): everything in the production. They stage publication:
  they ask for the papers to be published, send corrections, and submit the full proceedings.
- *Publishers* (site-wide, group "Publishers"): every production. They approve and carry out
  publication of the papers, corrections and the full proceedings, and enter the ISBNs. IGLC is
  registered as a publisher in Norway; the ISBNs are requested by whoever holds this role,
  a more permanent position than a proceedings editor.
- *Superusers*: everything, as chief editor and publisher.

**Step 5 (the full proceedings):** /production/<n>/book/

- Structure (based on IGLC 32): front cover (uploaded), colophon (generated: editors,
  copyright, ISSN/ISBN), title page (generated), front matter sections, table of contents
  (generated, by track with track chairs, linked to the papers), the papers as published,
  author index (generated, linked), back matter sections, back cover (uploaded).
- Sections are open-ended: any number, in the front or back matter, in the order the editors
  set. Templates: conference organisation, message (e.g. from the conference chair or the host
  institution), foreword, list of reviewers, sponsors, and a general one for anything else.
- Every section must be made from its IGLC Word template (Times New Roman throughout, the
  template's styles, empty header and footer: the system prints the page numbers, roman in the
  front matter). Uploads are checked and refused if they do not comply: A4, only Times New
  Roman in the text (logos and figures are pictures and not checked), nothing in the header or
  footer areas, text within the margins. Covers must be one A4 page. The foreword template is
  prefilled: papers per country (the first author's), papers per track (submitted column to fill
  in from ConfTool), track chairs, the editors' signature.
- Blank pages are added so the title page and page 1 are right-hand pages. Page labels make a
  viewer show the printed numbers; bookmarks for the parts, tracks and papers.
- Chief editors make drafts (private) and submit one; the publisher enters the ISBNs and
  approves: the final book is made with the ISBNs, published, linked from the conference page
  (as "Full proceedings") and recorded as volume 1 with its ISBN.
- Conferences published before these tools (e.g. IGLC 28, IGLC 34): Manage → Proceedings production →
  "From a conference already published", or `adopt_published 28`. The papers
  come from the archive as published (pages, tracks, PDFs); the PDFs are fetched on the Full
  proceedings page, checking each page count. Tracks missing in the archive (IGLC 28) can be
  read from the PDFs' footers first: `read_tracks --conference 28` and `import_tracks`.
- Tested on IGLC 34: 1,878 pages in 29 s; 125 MB (the papers' own PDFs take 140 MB).

## Open

- Template for IGLC 35: Title style 40 pt space before (was 18 pt) and a one-line note in the
  first-page header (tools/reserve_reference_space.py). Tested on five IGLC 34 papers with 3-5
  line references: the title always starts at the same place, 18 pt below a 5-line reference,
  and no page count changed.
- Fonts on the server: copy times.ttf, timesi.ttf and timesbd.ttf from a Windows PC (C:\Windows\Fonts) into
  the private files under fonts/ (Unraid: /mnt/user/appdata/iglc/private/fonts/; Azure: the
  "production" container, folder fonts). Without them the publish page says so.
