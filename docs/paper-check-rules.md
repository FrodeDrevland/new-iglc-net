# The paper check: rules

<!-- Made from the code by `python manage.py check_rules_doc`; do not edit by hand. -->

The automatic check of IGLC papers runs on the website's “Check your paper” page (for authors) and on every upload by the proceedings editors. Each check finds one kind of problem. What happens when it does is set per stage:

- **Reject**: the paper must be fixed; the upload is refused.
- **Warn**: should be fixed; the author must confirm to submit anyway, and the paper may be sent back.
- **Note**: for information only.
- **–** (off): not checked at that stage.

The stages are the paper **for review** (full and revised papers, anonymous), the **camera-ready** paper, and the **editors' upload** (the edited Word file with the PDF made by Word). The levels below are the defaults in the code; the ones in force are set in the back office (Settings → Paper check rules), as are the limits (Settings → Paper check limits).

## Limits (defaults)

| Limit | Default |
|---|---|
| Maximum pages (without the submission checklist) | 12 |
| Maximum title length | 90 characters |
| Maximum abstract length | 200 words |
| Maximum keywords | 5 |
| Formatting set by hand: reported from | 10 pieces of text or paragraphs |
| Minimum picture resolution | 200 pixels per inch at the size shown |
| Longest paragraph | 250 words |
| Keywords from the suggested list | at least 3 |

## The checks

### File

| Check | How it is detected | Review | Camera-ready | Editors' upload |
|---|---|---|---|---|
| **The file is not a readable Word (.docx) file** (`not_docx`) | The upload cannot be opened as a Word .docx file (for example a .doc, a PDF or a damaged file). | **Reject** | **Reject** | **Reject** |
| **Tracked changes or comments in the file** (`track_changes_or_comments`) | The file contains tracked insertions or deletions, or comments. | Warn | **Reject** | **Reject** |

### Title and authors

| Check | How it is detected | Review | Camera-ready | Editors' upload |
|---|---|---|---|---|
| **No paragraph in the Title style** (`title_missing`) | No paragraph uses the Title style, and the first paragraph cannot be taken as the title. | **Reject** | **Reject** | **Reject** |
| **The title is in another style than Title** (`title_wrong_style`) | No Title style is used, but the first paragraph looks like the title (for example typed in the Authors style). | Warn | Warn | Warn |
| **The title is typed in capitals** (`title_capitals`) | More than 80% of the title's letters are typed as capitals (the Title style shows the title in capitals by itself). | Note | Warn | Warn |
| **The title is longer than the limit (characters)** (`title_long`) | The title has more characters than the limit (90), spaces included. | Warn | Warn | Warn |
| **No paragraph in the Authors style** (`authors_missing`) | No paragraph uses the Authors style. | **Reject** | **Reject** | **Reject** |
| **An author has no footnote with affiliation** (`author_no_affiliation`) | An author name in the Authors paragraph has no footnote. | – | **Reject** | **Reject** |
| **An author refers to a footnote that does not exist** (`footnote_missing`) | An author name refers to a footnote number that does not exist. | – | **Reject** | **Reject** |
| **No email address in an author's footnote** (`author_no_email`) | An author's footnote contains no email address. | – | Warn | Warn |
| **No ORCID iD in an author's footnote** (`author_no_orcid`) | An author's footnote contains no ORCID iD. | – | Warn | Warn |
| **An ORCID iD is not valid** (`orcid_invalid`) | An ORCID iD is written wrongly or its check digit is wrong (0000-0000-0000-0000 fails too). | – | Warn | Warn |
| **An author name includes a title (Dr, Prof …)** (`author_title_in_name`) | An author name contains Dr, Prof or PhD. | – | Warn | Warn |

### Abstract, keywords and headings

| Check | How it is detected | Review | Camera-ready | Editors' upload |
|---|---|---|---|---|
| **No Abstract heading** (`abstract_missing`) | No Heading 1 paragraph reads “Abstract”. | **Reject** | **Reject** | **Reject** |
| **The abstract is longer than the limit (words)** (`abstract_long`) | The abstract has more words than the limit (200). | Warn | Warn | Warn |
| **References cited in the abstract** (`abstract_references`) | The abstract contains a citation: (Author, 2020), Author (2020), “et al.” or a numbered reference such as [12]. Years alone, such as (1993–2025), are not counted. | Warn | Warn | Warn |
| **No Keywords heading** (`keywords_missing`) | No Heading 1 paragraph reads “Keywords”. | **Reject** | **Reject** | **Reject** |
| **More keywords than the limit** (`keywords_many`) | More keywords than the limit (5), counted by commas and semicolons. | Warn | Warn | Warn |
| **Too few keywords from the suggested IGLC list** (`keywords_not_from_list`) | Fewer than 3 keywords match the list of suggested IGLC keywords (spelling variants such as -ise/-ize and abbreviations in brackets are accepted). | Note | Note | – |
| **A mandatory heading (Introduction, References) is missing** (`heading_missing`) | No Heading 1 paragraph reads “Introduction” or “References”. | **Reject** | **Reject** | **Reject** |

### Figures, tables and references

| Check | How it is detected | Review | Camera-ready | Editors' upload |
|---|---|---|---|---|
| **Pictures with too low a resolution for their size** (`image_resolution`) | A picture (PNG, JPEG, GIF, BMP) has fewer pixels than the limit (200 pixels per inch) at the width it is shown in the paper. Vector pictures (EMF, SVG …) pass. | Note | Warn | Warn |
| **Figures or tables not mentioned in the text** (`figure_table_not_cited`) | A caption numbered “Figure n” or “Table n” has no mention of that number in the text (“Figure 3”, “Fig. 3”, “Figures 2 and 3”, “Tables 1–4” all count). | Warn | Warn | Note |
| **Reference list entries not in the References style** (`references_style`) | Paragraphs after the References heading that are not in the References style. | Note | Warn | Warn |
| **Reference list not in alphabetical order** (`references_order`) | Two neighbouring entries of the reference list whose first authors are not in alphabetical order (accents ignored). | Warn | Warn | Warn |

### Template and formatting

| Check | How it is detected | Review | Camera-ready | Editors' upload |
|---|---|---|---|---|
| **Paragraphs in styles that are not the template's** (`non_template_styles`) | Paragraphs with text use a style that is not one of the template's (often Normal or a style from another template, or Heading 4 and lower). One finding per style, with the number of paragraphs. | Warn | Warn | Warn |
| **Body paragraphs in the wrong one of Text First / Text Running** (`text_first_running`) | A body paragraph that follows another body paragraph must be in Text Running; one that follows anything else (a heading, figure, table, list, quote or caption) in Text First. Paragraphs after one in a non-template style (often Normal) are not judged; those are reported by the style check. | Note | Warn | Warn |
| **Style definitions differ from the current template** (`styles_changed`) | The definition of a template style (font, size, bold/italic/capitals, spacing, indents, alignment) or the default font differs from the IGLC 35 template. Papers written in an older template are caught here (its Title style has less space above). | Note | Warn | Note |
| **Formatting set by hand (reported from the limit upwards)** (`manual_formatting`) | Font, font size, spacing or indents set by hand to something else than the style says, counted per piece of text or paragraph; reported from the limit (10) upwards. Bold, italic, superscript, symbols and equations are not counted. | Note | Warn | Note |
| **Empty paragraphs between paragraphs** (`empty_paragraphs`) | Empty paragraphs between the paper's paragraphs, tables and figures. Empty paragraphs at the very end, page breaks and section breaks are not counted. | Note | Warn | Note |
| **Paragraphs longer than the limit (words)** (`long_paragraphs`) | A Text First or Text Running paragraph has more words than the limit (250). | Note | Note | – |
| **Page size or margins differ from the template** (`page_setup_changed`) | A section's page size is not A4 (landscape A4 is accepted) or its margins are not 2.5 cm. | **Reject** | **Reject** | **Reject** |
| **Figures not placed “In line with text”** (`figure_floating`) | A picture or drawing object is not placed “In line with text” (it floats, wrapped around text or in front of/behind it). | Warn | Warn | Warn |
| **Captions not above tables / below figures, or in the wrong style** (`caption_position`) | A table caption is not directly above a table, a figure caption not directly below a figure, or a caption starting “Table …” is in the Figure caption style (or the other way round). | Warn | Warn | Warn |

### Submission checklist

| Check | How it is detected | Review | Camera-ready | Editors' upload |
|---|---|---|---|---|
| **The submission checklist is missing** (`checklist_missing`) | The heading “IGLC Paper Submission Checklist” from the end of the template is not in the file. | Warn | Warn | – |
| **The submission checklist is still in the file** (`checklist_present`) | The checklist is still in the file at the editors' upload; it must not be published. | – | – | **Reject** |

### Anonymity (papers under review)

| Check | How it is detected | Review | Camera-ready | Editors' upload |
|---|---|---|---|---|
| **Author names or emails in a paper under review** (`not_anonymous`) | In a paper under review: the author names are not placeholders (XXXX, “Anonymous”, “Author”), or a footnote contains an email address. | **Reject** | – | – |
| **Names in the file properties of a paper under review** (`file_properties_names`) | In a paper under review: the file's Author or Last modified by property contains a name. | Warn | – | – |

### Pages and PDF

| Check | How it is detected | Review | Camera-ready | Editors' upload |
|---|---|---|---|---|
| **More pages than the limit (the checklist not counted)** (`too_many_pages`) | The PDF (saved from Word) has more pages than the limit (12); the pages of the submission checklist are not counted. | **Reject** | **Reject** | **Reject** |
| **No PDF uploaded, so the pages were not counted** (`pdf_not_checked`) | No PDF was uploaded with the Word file, so the pages were not counted. | Note | Note | Note |
| **The PDF could not be read** (`pdf_unreadable`) | The uploaded PDF could not be read. | Warn | Warn | Warn |
| **The PDF has another number of pages than Word counts** (`pdf_pages_differ`) | Word's own page count, stored in the file, differs from the PDF's. Word lays some papers out differently when making the PDF. Not checked when Word stored no count. | Note | Warn | **Reject** |

### Editors' upload only (the PDF made by Word)

| Check | How it is detected | Review | Camera-ready | Editors' upload |
|---|---|---|---|---|
| **No PDF with the Word file (editors' upload)** (`pdf_missing`) | The editors uploaded a Word file without its PDF. | – | – | Warn |
| **The PDF was not made by Word (no marked headers/footers)** (`pdf_not_from_word`) | The PDF has no headers or footers marked by Word, so it was not saved from Word for Windows (or was printed to PDF). | – | – | **Reject** |
| **Text left in the header or footer area of the PDF** (`pdf_running_left`) | Text in the header or footer area of the PDF that is not a Word header or footer; it would collide with the running heads printed at publication. | – | – | **Reject** |
| **No room for the reference above the title on page 1** (`reference_space_missing`) | Text within 100 pt of the top of page 1: no room for the reference printed above the title (the paper does not use the IGLC 35 Title style). | – | – | **Reject** |

## Not checked automatically (yet)

Items in the template's submission checklist, and a few others, that no check covers. The effort is a rough guess.

| Item | How it could be checked | Effort |
|---|---|---|
| Pages 11 and 12 contain only references | From the PDF: find the References heading and check that no page after page 10 has text before it. | Moderate |
| Tables do not break across pages | From the PDF: find each table's rows and check they are on one page. | Moderate |
| Every in-text citation in the reference list, and the other way round | Match (Author, Year) citations against the reference list entries. | Moderate, with false alarms |
| References in APA 7th edition | Pattern checks on each reference (authors, (year), title, source, DOI as https://doi.org/…). Only the most common mistakes can be caught. | Hard |
| UK or US English used consistently | Count spelling pairs (organisation/organization, colour/color …) and note papers that mix both. | Moderate |
| Metric units | Look for imperial units (ft, feet, inch, lb, sq ft, gallon, °F) without a metric value nearby. | Moderate |
| Self-citations that reveal the authors (review) | Look for “our previous work (…)” and similar phrases next to citations. | Hard |
| Plagiarism report and rate below 15% | Needs a plagiarism service; the report is uploaded to ConfTool. | Not automatic |
| Relevance to lean construction; academic paper; cites the lean construction literature | Needs the chairs' judgement (citations of IGLC papers could be counted as a hint). | Not automatic |
| Language quality and spelling | Needs people (or a language tool; results vary). | Not automatic |
| Readable in black and white | Needs people. | Not automatic |
| Rebuttal table and all reviewers' comments addressed | Handled in ConfTool by the chairs. | Not automatic |
