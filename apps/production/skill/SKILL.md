---
name: iglc-paper-check
description: Check a paper for the IGLC conference (International Group for Lean Construction) against the IGLC Word template, explain what to fix, and optionally make the purely mechanical fixes. Use when an author asks to check, prepare or fix an IGLC paper (.docx) for review or camera-ready submission.
---

# IGLC paper check

This skill runs the same automatic checks as the IGLC website's "Check your paper" page
(https://www.iglc.net/for-authors/check-your-paper/) and helps the author fix what they find.
The website's check is the official one: tell the author to run it before submitting.

## 1. Run the check

The script needs only Python 3.9 or later (no packages; `pypdf` only for the optional PDF).

```bash
python scripts/check_paper.py PAPER.docx --stage camera_ready      # or: --stage review
python scripts/check_paper.py PAPER.docx --stage camera_ready --pdf PAPER.pdf   # also checks the page count
```

Ask the author which stage it is if unclear: **review** = the anonymous full paper for peer
review; **camera_ready** = the final version after acceptance. It prints what was read (title,
authors, affiliations, abstract, keywords) and the findings, grouped as:

- **Must be fixed** – the paper will be rejected by the submission check until fixed.
- **Should be fixed** – the editors may send the paper back.
- **For information**.

Report the findings to the author in plain language, most serious first, and show what was
read, so they can see whether the metadata (title, authors, affiliations, ORCIDs) is right.

## 2. Explain how to fix each finding (in Word)

| Finding | How to fix |
|---|---|
| No paragraph with the Title / Authors style | Put the cursor in the title (author line) and apply the **Title** (**Authors**) style from the Styles pane. |
| Title in capitals | Type the title in normal case; the Title style shows it in capitals. |
| Title longer than 90 characters | Shorten the title. This is the author's decision: suggest options, do not choose. |
| Author has no footnote with affiliation | After each author name, Insert → Footnote: "Position, Department, Institution, City, Country, email, orcid.org/0000-0000-0000-0000". Co-authors with the same affiliation still each get their own footnote. |
| No email / no ORCID / invalid ORCID | Add them to the author's footnote; ORCID iDs are at https://orcid.org. |
| Abstract over 200 words; more than five keywords | Shorten. Content decisions are the author's: suggest, do not decide. |
| Missing heading (Abstract, Keywords, Introduction, References) | Add the heading with the **Heading 1** style. |
| Paragraphs in a style that is not a template style (often "Normal") | Apply the template's styles: **Text First** for the first paragraph after a heading, **Text Running** for the following ones, **Table body** in tables, **Figure caption** / **Table caption** for captions, **References** for the reference list. |
| Page size or margins changed | Layout → Margins → 2.5 cm on all sides; Layout → Size → A4. |
| Too many pages | At most 12 pages, including references; the submission checklist at the end does not count. Shortening is the author's decision. |
| Submission checklist missing | Copy the checklist from the end of the IGLC template to the end of the paper and tick the boxes that apply. |
| Reference in the abstract | Rewrite the sentence without the citation. The wording is the author's decision. |
| Empty paragraphs | Delete the empty lines (Home → ¶ shows them); the styles give the space between paragraphs. |
| Figure not "In line with text" | Right-click the picture → Wrap Text → In Line with Text, in its own paragraph in the **Figure** style. |
| Caption in the wrong place or style | Table captions go directly above the table (**Table caption**), figure captions directly below the figure (**Figure caption**). |
| Formatting set by hand | Select the text and press Ctrl+Space (character formatting) and Ctrl+Q (paragraph formatting) so the style decides font, size and spacing. |
| Style definitions changed | Start again from the current IGLC template and paste the text in with "Keep Text Only", or copy the template's styles with the Organizer (Developer → Document Template → Organizer). |
| Not anonymous (review stage) | Replace author names with XXXX and remove the footnotes' contents; File → Info → Check for Issues → Inspect Document → remove Document Properties and Personal Information. |
| Tracked changes or comments | Review → Accept all changes; delete all comments. |

## 3. Mechanical fixes (only if the author asks)

If the environment can edit .docx files, you may make **only** these changes, in a copy saved
as `PAPER-checked.docx`, never in the original:

- apply template styles to paragraphs in Normal or foreign styles (Text First after a heading,
  Text Running otherwise, the caption styles for captions);
- apply the Title and Authors styles;
- delete empty paragraphs between paragraphs;
- clear character and paragraph formatting set by hand (keep bold, italic, superscript and subscript);
- accept tracked changes and remove comments, if the author confirms;
- remove personal information from the file properties (review stage).

Never change the text itself: wording, title, abstract, keywords, references, figures or
tables. List every change you made. Then run the check again on the copy, and remind the
author to check the result in Word and to run the official check on the website.
