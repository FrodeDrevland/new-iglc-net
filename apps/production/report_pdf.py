"""The template check report as a PDF, for authors to attach to their submission."""

import io

from .checks import LEVELS


def report_pdf(check, stage_label: str, url: str) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import cm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    from xml.sax.saxutils import escape

    styles = getSampleStyleSheet()
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=2.2 * cm, rightMargin=2.2 * cm,
                            topMargin=2 * cm, bottomMargin=2 * cm, title="IGLC template check")
    story = [
        Paragraph("IGLC paper template check", styles["Title"]),
        Paragraph(("<font color='#1a7f37'><b>Passed</b></font>" if check.passed
                   else "<font color='#b42318'><b>Not passed</b></font>")
                  + f" &nbsp;·&nbsp; {escape(stage_label)}", styles["Heading2"]),
    ]
    facts = [
        ["Paper", escape(check.title or "(no title found)")],
        ["File", escape(check.file_name)],
        ["Checked", check.created.strftime("%d %B %Y, %H:%M UTC")],
        ["Check ID", check.short_id],
        ["File fingerprint", check.sha256],
    ]
    if check.pdf_sha256:
        facts.append(["PDF fingerprint", check.pdf_sha256])
    table = Table([[Paragraph(f"<b>{a}</b>", styles["Normal"]), Paragraph(b, styles["Normal"])] for a, b in facts],
                  colWidths=[3.6 * cm, 13 * cm])
    table.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]))
    story += [table, Spacer(1, 10)]
    if not check.findings:
        story.append(Paragraph("No problems found.", styles["Normal"]))
    for level, label in LEVELS.items():
        items = [f for f in check.findings if f["level"] == level]
        if items:
            story.append(Paragraph(f"{label} ({len(items)})", styles["Heading3"]))
            for item in items:
                story.append(Paragraph("• " + escape(item["message"]), styles["Normal"]))
    story += [Spacer(1, 14), Paragraph(
        f"The report can be verified at <link href='{escape(url)}' color='blue'>{escape(url)}</link>. "
        "The fingerprint identifies the exact file that was checked; the file itself was not kept.",
        styles["Italic"])]
    doc.build(story)
    return buffer.getvalue()
