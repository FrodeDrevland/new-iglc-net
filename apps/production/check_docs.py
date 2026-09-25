"""docs/paper-check-rules.md, made from the checks in the code: what each check looks for, how
it is detected and its default level per stage. Regenerate with

    python manage.py check_rules_doc

A test fails when the file is out of date, so a new check cannot be added without it.
"""

from __future__ import annotations

from pathlib import Path

from .checks import LIMITS, PRODUCTION, RULE_LABELS, default_rules

DOC = Path(__file__).resolve().parents[2] / "docs" / "paper-check-rules.md"

# (group heading, codes) in the order of the document
GROUPS = [
    ("File", ["not_docx", "track_changes_or_comments"]),
    ("Title and authors", ["title_missing", "title_wrong_style", "title_capitals", "title_long", "authors_missing",
                           "author_no_affiliation", "footnote_missing", "author_no_email", "author_no_orcid",
                           "orcid_invalid", "author_title_in_name"]),
    ("Abstract, keywords and headings", ["abstract_missing", "abstract_long", "abstract_references",
                                         "keywords_missing", "keywords_many", "keywords_not_from_list",
                                         "heading_missing"]),
    ("Figures, tables and references", ["image_resolution", "figure_table_not_cited", "references_style",
                                        "references_order"]),
    ("Template and formatting", ["non_template_styles", "text_first_running", "styles_changed", "manual_formatting", "empty_paragraphs", "long_paragraphs",
                                 "page_setup_changed", "figure_floating", "caption_position"]),
    ("Submission checklist", ["checklist_missing", "checklist_present"]),
    ("Anonymity (papers under review)", ["not_anonymous", "file_properties_names"]),
    ("Pages and PDF", ["too_many_pages", "pdf_not_checked", "pdf_unreadable", "pdf_pages_differ"]),
    ("Editors' upload only (the PDF made by Word)", ["pdf_missing", "pdf_not_from_word", "pdf_running_left",
                                                     "reference_space_missing"]),
]

# How each check decides; plain language for authors, chairs and editors.
DETAILS = {
    "not_docx": "The upload cannot be opened as a Word .docx file (for example a .doc, a PDF or a damaged file).",
    "track_changes_or_comments": "The file contains tracked insertions or deletions, or comments.",
    "title_missing": "No paragraph uses the Title style, and the first paragraph cannot be taken as the title.",
    "title_wrong_style": "No Title style is used, but the first paragraph looks like the title (for example typed "
                         "in the Authors style).",
    "title_capitals": "More than 80% of the title's letters are typed as capitals (the Title style shows the "
                      "title in capitals by itself).",
    "title_long": "The title has more characters than the limit ({title_chars}), spaces included.",
    "authors_missing": "No paragraph uses the Authors style.",
    "author_no_affiliation": "An author name in the Authors paragraph has no footnote.",
    "footnote_missing": "An author name refers to a footnote number that does not exist.",
    "author_no_email": "An author's footnote contains no email address.",
    "author_no_orcid": "An author's footnote contains no ORCID iD.",
    "orcid_invalid": "An ORCID iD is written wrongly or its check digit is wrong (0000-0000-0000-0000 fails "
                     "too).",
    "author_title_in_name": "An author name contains Dr, Prof or PhD.",
    "abstract_missing": "No Heading 1 paragraph reads “Abstract”.",
    "abstract_long": "The abstract has more words than the limit ({abstract_words}).",
    "abstract_references": "The abstract contains a citation: (Author, 2020), Author (2020), “et al.” or a "
                           "numbered reference such as [12]. Years alone, such as (1993–2025), are not counted.",
    "keywords_missing": "No Heading 1 paragraph reads “Keywords”.",
    "keywords_many": "More keywords than the limit ({keywords}), counted by commas and semicolons.",
    "heading_missing": "No Heading 1 paragraph reads “Introduction” or “References”.",
    "non_template_styles": "Paragraphs with text use a style that is not one of the template's (often Normal or "
                           "a style from another template, or Heading 4 and lower). One finding per style, with the "
                           "number of paragraphs.",
    "text_first_running": "A body paragraph that follows another body paragraph must be in Text Running; one "
                          "that follows anything else (a heading, figure, table, list, quote or caption) in "
                          "Text First. Paragraphs after one in a non-template style (often Normal) are not "
                          "judged; those are reported by the style check.",
    "image_resolution": "A picture (PNG, JPEG, GIF, BMP) has fewer pixels than the limit ({min_image_dpi} pixels "
                        "per inch) at the width it is shown in the paper. Vector pictures (EMF, SVG …) pass.",
    "figure_table_not_cited": "A caption numbered “Figure n” or “Table n” has no mention of that number in the "
                              "text (“Figure 3”, “Fig. 3”, “Figures 2 and 3”, “Tables 1–4” all count).",
    "references_style": "Paragraphs after the References heading that are not in the References style.",
    "references_order": "Two neighbouring entries of the reference list whose first authors are not in "
                        "alphabetical order (accents ignored).",
    "keywords_not_from_list": "Fewer than {keywords_from_list} keywords match the list of suggested IGLC keywords "
                              "(spelling variants such as -ise/-ize and abbreviations in brackets are accepted).",
    "long_paragraphs": "A Text First or Text Running paragraph has more words than the limit ({paragraph_words}).",
    "styles_changed": "The definition of a template style (font, size, bold/italic/capitals, spacing, indents, "
                      "alignment) or the default font differs from the IGLC 35 template. Papers written in an "
                      "older template are caught here (its Title style has less space above).",
    "manual_formatting": "Font, font size, spacing or indents set by hand to something else than the style "
                         "says, counted per piece of text or paragraph; reported from the limit "
                         "({manual_formatting}) upwards. Bold, italic, superscript, symbols and equations are "
                         "not counted.",
    "empty_paragraphs": "Empty paragraphs between the paper's paragraphs, tables and figures. Empty paragraphs at "
                        "the very end, page breaks and section breaks are not counted.",
    "page_setup_changed": "A section's page size is not A4 (landscape A4 is accepted) or its margins are not "
                          "2.5 cm.",
    "figure_floating": "A picture or drawing object is not placed “In line with text” (it floats, wrapped "
                       "around text or in front of/behind it).",
    "caption_position": "A table caption is not directly above a table, a figure caption not directly below a "
                        "figure, or a caption starting “Table …” is in the Figure caption style (or the other "
                        "way round).",
    "checklist_missing": "The heading “IGLC Paper Submission Checklist” from the end of the template is not in "
                         "the file.",
    "checklist_present": "The checklist is still in the file at the editors' upload; it must not be published.",
    "not_anonymous": "In a paper under review: the author names are not placeholders (XXXX, “Anonymous”, "
                     "“Author”), or a footnote contains an email address.",
    "file_properties_names": "In a paper under review: the file's Author or Last modified by property contains "
                             "a name.",
    "too_many_pages": "The PDF (saved from Word) has more pages than the limit ({max_pages}); the pages of the "
                      "submission checklist are not counted.",
    "pdf_not_checked": "No PDF was uploaded with the Word file, so the pages were not counted.",
    "pdf_unreadable": "The uploaded PDF could not be read.",
    "pdf_pages_differ": "Word's own page count, stored in the file, differs from the PDF's. Word lays some papers "
                        "out differently when making the PDF. Not checked when Word stored no count.",
    "pdf_missing": "The editors uploaded a Word file without its PDF.",
    "pdf_not_from_word": "The PDF has no headers or footers marked by Word, so it was not saved from Word for "
                         "Windows (or was printed to PDF).",
    "pdf_running_left": "Text in the header or footer area of the PDF that is not a Word header or footer; it "
                        "would collide with the running heads printed at publication.",
    "reference_space_missing": "Text within 100 pt of the top of page 1: no room for the reference printed "
                               "above the title (the paper does not use the IGLC 35 Title style).",
}

# Things the template's checklist asks for that no check covers yet, and how they could be checked.
CANDIDATES = [
    ("Pages 11 and 12 contain only references", "From the PDF: find the References heading and check that no "
     "page after page 10 has text before it.", "Moderate"),
    ("Tables do not break across pages", "From the PDF: find each table's rows and check they are on one page.",
     "Moderate"),
    ("Every in-text citation in the reference list, and the other way round", "Match (Author, Year) citations "
     "against the reference list entries.", "Moderate, with false alarms"),
    ("References in APA 7th edition", "Pattern checks on each reference (authors, (year), title, source, DOI "
     "as https://doi.org/…). Only the most common mistakes can be caught.", "Hard"),
    ("UK or US English used consistently", "Count spelling pairs (organisation/organization, "
     "colour/color …) and note papers that mix both.", "Moderate"),
    ("Metric units", "Look for imperial units (ft, feet, inch, lb, sq ft, gallon, °F) without a metric value "
     "nearby.", "Moderate"),
    ("Self-citations that reveal the authors (review)", "Look for “our previous work (…)” and similar "
     "phrases next to citations.", "Hard"),
    ("Plagiarism report and rate below 15%", "Needs a plagiarism service; the report is uploaded to ConfTool.",
     "Not automatic"),
    ("Relevance to lean construction; academic paper; cites the lean construction literature",
     "Needs the chairs' judgement (citations of IGLC papers could be counted as a hint).", "Not automatic"),
    ("Language quality and spelling", "Needs people (or a language tool; results vary).", "Not automatic"),
    ("Readable in black and white", "Needs people.", "Not automatic"),
    ("Rebuttal table and all reviewers' comments addressed", "Handled in ConfTool by the chairs.",
     "Not automatic"),
]

LEVEL_NAMES = {"off": "–", "note": "Note", "warn": "Warn", "reject": "**Reject**"}


def render(discussion: bool = False) -> str:
    """The document; with discussion=True, an empty column for the chairs' decision."""
    rules = default_rules()
    covered = [code for _, codes in GROUPS for code in codes]
    missing = [code for code in RULE_LABELS if code not in covered]
    if missing:
        raise ValueError(f"Checks not placed in a group in check_docs.GROUPS: {', '.join(missing)}")
    lines = [
        "# The paper check: rules",
        "",
        *([] if discussion else ["<!-- Made from the code by `python manage.py check_rules_doc`; do not edit by hand. -->", ""]),
        "The automatic check of IGLC papers runs on the website's “Check your paper” page (for authors) "
        "and on every upload by the proceedings editors. Each check finds one kind of problem. What happens "
        "when it does is set per stage:",
        "",
        "- **Reject**: the paper must be fixed; the upload is refused.",
        "- **Warn**: should be fixed; the author must confirm to submit anyway, and the paper may be sent back.",
        "- **Note**: for information only.",
        "- **–** (off): not checked at that stage.",
        "",
        "The stages are the paper **for review** (full and revised papers, anonymous), the **camera-ready** "
        "paper, and the **editors' upload** (the edited Word file with the PDF made by Word). The levels below "
        "are the defaults in the code; the ones in force are set in the back office (Settings → Paper check "
        "rules), as are the limits (Settings → Paper check limits).",
        "",
        "## Limits (defaults)",
        "",
        "| Limit | Default |",
        "|---|---|",
        f"| Maximum pages (without the submission checklist) | {LIMITS['max_pages']} |",
        f"| Maximum title length | {LIMITS['title_chars']} characters |",
        f"| Maximum abstract length | {LIMITS['abstract_words']} words |",
        f"| Maximum keywords | {LIMITS['keywords']} |",
        f"| Formatting set by hand: reported from | {LIMITS['manual_formatting']} pieces of text or paragraphs |",
        f"| Minimum picture resolution | {LIMITS['min_image_dpi']} pixels per inch at the size shown |",
        f"| Longest paragraph | {LIMITS['paragraph_words']} words |",
        f"| Keywords from the suggested list | at least {LIMITS['keywords_from_list']} |",
        "",
        "## The checks",
        "",
    ]
    for heading, codes in GROUPS:
        extra = (" Decision |", "---|") if discussion else ("", "")
        lines += [f"### {heading}", "", "| Check | How it is detected | Review | Camera-ready | Editors' upload |" + extra[0],
                  "|---|---|---|---|---|" + extra[1]]
        for code in codes:
            levels = rules[code]
            detail = DETAILS.get(code, "").format(**LIMITS)
            lines.append(f"| **{RULE_LABELS[code]}** (`{code}`) | {detail} | {LEVEL_NAMES[levels['review']]} | "
                         f"{LEVEL_NAMES[levels['camera_ready']]} | {LEVEL_NAMES[levels[PRODUCTION]]} |" + ("  |" if discussion else ""))
        lines.append("")
    lines += [
        "## Not checked automatically (yet)",
        "",
        "Items in the template's submission checklist, and a few others, that no check covers. The effort "
        "is a rough guess.",
        "",
        "| Item | How it could be checked | Effort |",
        "|---|---|---|",
    ]
    lines += [f"| {item} | {how} | {effort} |" for item, how, effort in CANDIDATES]
    lines.append("")
    return "\n".join(lines)


def write() -> Path:
    DOC.write_text(render(), encoding="utf-8")
    return DOC
