"""Room signs: one A4 page (landscape) per location, with its name and a QR code for its page on
the conference site (what is on in the room, and its map). Made with ReportLab."""

from __future__ import annotations

import io

from django.conf import settings
from reportlab.graphics import renderPDF
from reportlab.graphics.barcode.qr import QrCodeWidget
from reportlab.graphics.shapes import Drawing
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.units import cm
from reportlab.pdfgen import canvas

from .public import home_url


def _qr(c, value, x, y, size):
    widget = QrCodeWidget(value, barLevel="M")
    x0, y0, x1, y1 = widget.getBounds()
    drawing = Drawing(size, size, transform=[size / (x1 - x0), 0, 0, size / (y1 - y0), 0, 0])
    drawing.add(widget)
    renderPDF.draw(drawing, c, x, y)


def _fit(c, text, font, size, width):
    while size > 20 and c.stringWidth(text, font, size) > width:
        size -= 4
    return size


def room_signs(programme, locations, home) -> bytes:
    buffer = io.BytesIO()
    width, height = landscape(A4)
    c = canvas.Canvas(buffer, pagesize=(width, height))
    number = programme.conference.number
    c.setTitle(f"IGLC {number} room signs")
    venue = (settings.PROGRAMME_URL or "").replace("https://", "").replace("http://", "")
    for location in locations:
        url = f"{home_url(home)}programme/location/{location.pk}/"
        c.setFont("Helvetica-Bold", 22)
        c.drawString(2 * cm, height - 2.5 * cm, f"IGLC {number}")
        c.setFont("Helvetica", 16)
        c.drawString(2 * cm, height - 3.4 * cm, programme.conference.location)
        text_width = width - 16 * cm
        size = _fit(c, location.name, "Helvetica-Bold", 96, text_width)
        c.setFont("Helvetica-Bold", size)
        c.drawString(2 * cm, height / 2, location.name)
        c.setFont("Helvetica", 24)
        if location.building:
            c.drawString(2 * cm, height / 2 - 1.4 * cm, location.building)
        _qr(c, url, width - 12 * cm, height / 2 - 5 * cm, 10 * cm)
        c.setFont("Helvetica", 12)
        c.drawCentredString(width - 7 * cm, height / 2 - 5.6 * cm, "What is on in this room")
        c.setFont("Helvetica", 14)
        c.drawString(2 * cm, 2 * cm, f"The programme, now and next: {venue}" if venue else url)
        c.showPage()
    c.save()
    return buffer.getvalue()
