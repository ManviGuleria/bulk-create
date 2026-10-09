"""
Certificate PDF generation using ReportLab.

Design decision: A single predefined template is used. The template is
rendered entirely in code (no external template file) so the project is
self-contained. ReportLab's canvas API gives us precise pixel-level control
over layout, which is appropriate for certificate design.
"""

from __future__ import annotations

import os
from pathlib import Path
from datetime import date

from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader

from app.core.config import settings


# ---------------------------------------------------------------------------
# Colour palette
# ---------------------------------------------------------------------------
NAVY = colors.HexColor("#1B2A4A")
GOLD = colors.HexColor("#C9A84C")
LIGHT_GOLD = colors.HexColor("#F0D080")
OFF_WHITE = colors.HexColor("#FAFAF5")
DARK_GRAY = colors.HexColor("#333333")


def _draw_border(c: canvas.Canvas, width: float, height: float) -> None:
    """Draw a decorative double-line border around the page."""
    margin_outer = 12 * mm
    margin_inner = 15 * mm

    # Outer thick gold border
    c.setStrokeColor(GOLD)
    c.setLineWidth(3)
    c.rect(margin_outer, margin_outer, width - 2 * margin_outer, height - 2 * margin_outer)

    # Inner thin gold border
    c.setLineWidth(1)
    c.rect(margin_inner, margin_inner, width - 2 * margin_inner, height - 2 * margin_inner)


def _draw_corner_ornaments(c: canvas.Canvas, width: float, height: float) -> None:
    """Draw simple diamond ornaments at each corner of the inner border."""
    margin = 15 * mm
    ornament_size = 4 * mm
    corners = [
        (margin, margin),
        (width - margin, margin),
        (margin, height - margin),
        (width - margin, height - margin),
    ]
    c.setFillColor(GOLD)
    c.setStrokeColor(GOLD)
    c.setLineWidth(0.5)
    for cx, cy in corners:
        # Draw a small rotated square (diamond)
        p = c.beginPath()
        p.moveTo(cx, cy + ornament_size)
        p.lineTo(cx + ornament_size, cy)
        p.lineTo(cx, cy - ornament_size)
        p.lineTo(cx - ornament_size, cy)
        p.close()
        c.drawPath(p, fill=1, stroke=0)


def _draw_background(c: canvas.Canvas, width: float, height: float) -> None:
    """Fill the page with an off-white background and a subtle central vignette."""
    c.setFillColor(OFF_WHITE)
    c.rect(0, 0, width, height, fill=1, stroke=0)

    # Subtle horizontal gold band across the top and bottom
    band_height = 18 * mm
    c.setFillColor(NAVY)
    c.rect(0, height - band_height, width, band_height, fill=1, stroke=0)
    c.rect(0, 0, width, band_height, fill=1, stroke=0)


def _centered_text(
    c: canvas.Canvas,
    text: str,
    y: float,
    font: str,
    size: float,
    color: colors.Color,
    width: float,
) -> None:
    """Render *text* horizontally centred at vertical position *y*."""
    c.setFont(font, size)
    c.setFillColor(color)
    c.drawCentredString(width / 2, y, text)


def generate_certificate_pdf(
    *,
    recipient_name: str,
    recipient_email: str,
    course_name: str,
    completion_date: str,
    output_path: str,
) -> str:
    """
    Generate a single PDF certificate and save it to *output_path*.

    Parameters
    ----------
    recipient_name:  Full name to appear on the certificate.
    recipient_email: Email address (shown in small print for reference).
    course_name:     Name of the course / event.
    completion_date: ISO-8601 date string (YYYY-MM-DD).
    output_path:     Absolute path where the PDF should be written.

    Returns
    -------
    The absolute path of the written PDF.

    Raises
    ------
    ValueError  – if *completion_date* cannot be parsed as a date.
    OSError     – if the output directory cannot be created or the file
                  cannot be written.
    """

    # Validate / parse the date so we can format it nicely
    try:
        parsed_date = date.fromisoformat(completion_date)
        formatted_date = parsed_date.strftime("%B %d, %Y")  # e.g. "October 08, 2026"
    except ValueError as exc:
        raise ValueError(
            f"Invalid completion_date {completion_date!r}: expected YYYY-MM-DD"
        ) from exc

    # Ensure output directory exists
    output_dir = Path(output_path).parent
    output_dir.mkdir(parents=True, exist_ok=True)

    page_width, page_height = landscape(A4)  # 297 mm × 210 mm

    c = canvas.Canvas(output_path, pagesize=landscape(A4))
    c.setTitle(f"Certificate – {recipient_name}")
    c.setAuthor(settings.CERTIFICATE_ISSUER)

    # --- Background ---
    _draw_background(c, page_width, page_height)

    # --- Decorative borders ---
    _draw_border(c, page_width, page_height)
    _draw_corner_ornaments(c, page_width, page_height)

    # --- Issuer name (top band) ---
    _centered_text(
        c,
        settings.CERTIFICATE_ISSUER,
        page_height - 12 * mm,
        "Helvetica-Bold",
        14,
        LIGHT_GOLD,
        page_width,
    )

    # --- Main heading ---
    _centered_text(
        c,
        settings.CERTIFICATE_TITLE,
        page_height - 42 * mm,
        "Times-Bold",
        36,
        NAVY,
        page_width,
    )

    # Decorative gold rule under heading
    rule_y = page_height - 47 * mm
    c.setStrokeColor(GOLD)
    c.setLineWidth(1.5)
    c.line(60 * mm, rule_y, page_width - 60 * mm, rule_y)

    # --- "This is to certify that" ---
    _centered_text(
        c,
        "This is to certify that",
        page_height - 62 * mm,
        "Times-Italic",
        16,
        DARK_GRAY,
        page_width,
    )

    # --- Recipient name (the star of the show) ---
    _centered_text(
        c,
        recipient_name,
        page_height - 82 * mm,
        "Times-Bold",
        30,
        NAVY,
        page_width,
    )

    # Underline the recipient name
    name_y = page_height - 84 * mm
    c.setStrokeColor(GOLD)
    c.setLineWidth(0.8)
    c.line(70 * mm, name_y, page_width - 70 * mm, name_y)

    # --- "has successfully completed" ---
    _centered_text(
        c,
        "has successfully completed",
        page_height - 98 * mm,
        "Times-Italic",
        16,
        DARK_GRAY,
        page_width,
    )

    # --- Course name ---
    _centered_text(
        c,
        course_name,
        page_height - 114 * mm,
        "Times-Bold",
        22,
        GOLD,
        page_width,
    )

    # --- Completion date ---
    _centered_text(
        c,
        f"on  {formatted_date}",
        page_height - 130 * mm,
        "Times-Roman",
        13,
        DARK_GRAY,
        page_width,
    )

    # --- Signature line ---
    sig_x_left = 60 * mm
    sig_x_right = page_width - 60 * mm
    sig_y = 38 * mm
    c.setStrokeColor(NAVY)
    c.setLineWidth(0.6)
    c.line(sig_x_left, sig_y, sig_x_right, sig_y)

    _centered_text(
        c,
        settings.CERTIFICATE_ISSUER,
        sig_y - 5 * mm,
        "Helvetica",
        10,
        DARK_GRAY,
        page_width,
    )
    _centered_text(
        c,
        "Authorised Signatory",
        sig_y - 10 * mm,
        "Helvetica-Oblique",
        9,
        DARK_GRAY,
        page_width,
    )

    # --- Small-print footer (bottom band) ---
    _centered_text(
        c,
        f"Issued to: {recipient_email}",
        8 * mm,
        "Helvetica",
        8,
        LIGHT_GOLD,
        page_width,
    )

    c.save()
    return output_path
