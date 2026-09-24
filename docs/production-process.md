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
papers are renumbered automatically.

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
- Editor accounts: Manage → Users → add user, tick "Staff status", group "Proceedings
  editors"; then add the person to the production (Manage → Proceedings productions).

## Open

- Template for IGLC 35: Title style 40 pt space before (was 18 pt) and a one-line note in the
  first-page header (tools/reserve_reference_space.py). Tested on five IGLC 34 papers with 3-5
  line references: the title always starts at the same place, 18 pt below a 5-line reference,
  and no page count changed.
- Fonts on the server: Times New Roman from Microsoft's redistributable core fonts in the
  container image.
