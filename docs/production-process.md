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
6. **The system builds everything:** prints headers, footers and page numbers on each PDF
   (first page: full reference with DOI link; even pages: title and conference line; odd
   pages: authors and track), assigns DOIs, builds front matter, table of contents and the
   full proceedings, and publishes the papers in the archive.
7. **Authors check the published metadata**; then the Crossref deposit is made.

A paper replaced after step 5 goes through step 3 again; before publication, the following
papers are renumbered automatically.

## Support for editors

- A guidelines page: what to check and fix, how to convert and upload, what each check
  message means.
- The conversion tool (tools/word_batch.ps1 now): converts all Word files in a folder with
  Word, empties headers and footers first, and writes page counts. Later a small Windows app
  that also downloads and uploads.

## Open

- The 2027 process with ConfTool, as a subset of this.
- Printing the headers onto the PDFs: font, size and position identical to the template.
