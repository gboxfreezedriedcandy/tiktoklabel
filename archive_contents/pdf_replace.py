
import io
import re
import os
import PyPDF2
from reportlab.pdfgen import canvas
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfbase import pdfmetrics

def _register_font_if_available(font_path: str, font_name: str = "SimSun") -> str:
    """Try to register a TTF for Chinese; fallback silently if missing."""
    try:
        if font_path and os.path.exists(font_path):
            pdfmetrics.registerFont(TTFont(font_name, font_path))
            return font_name
    except Exception:
        pass
    # Fallback to a common font
    return "Helvetica"

def replace_text_in_pdf(input_pdf_path, output_pdf_path, replacements, font_path: str = "simsun.ttf"):
    """
    Replace text in a PDF by overlaying translated strings at computed positions.
    The logic looks for the block between the first 'QTY' and the next 'QTY',
    parses 'G-BOX ...<qty>', and draws translated lines with ReportLab.

    Change: Always anchor the translated block at the bottom of the page so
    it appears below existing content (no overlapping heuristics by count).
    """
    font_name = _register_font_if_available(font_path)
    #print(replacements)
    with open(input_pdf_path, 'rb') as input_file:
        pdf_reader = PyPDF2.PdfReader(input_file)
        pdf_writer = PyPDF2.PdfWriter()

        previous_page = ""
        count = 0
        for page in pdf_reader.pages:
            count += 1
            text = page.extract_text()

            if text:
                text = text.replace("\n", "").upper()
                text = previous_page + text
                try:
                    found = re.search(r'QTY(.*)QTY', text)
                    #print(found)
                    if found:
                        previous_page = ""
                        start_x = 50
                        orders = found.group(1).split("G-BOX ")
                        if orders and orders[0] == "":
                            orders.pop(0)

                        # Build translated lines first so we can size/anchor block
                        translated_lines = []
                        for item in orders:
                            for old_text, new_text in replacements.items():
                                if old_text in item:
                                    match = re.search(old_text + r'(\d+)', item)
                                    if not match:
                                        continue
                                    order_qty = match.group(1)
                                    order_qty_text = f"({order_qty})" if order_qty.isdigit() and int(order_qty) > 1 else order_qty
                                    translated_lines.append(f"{order_qty_text} X {new_text}")

                        if translated_lines:
                            # Use actual page size for the overlay
                            try:
                                page_width = float(getattr(page.mediabox, 'width', page.mediabox.upper_right[0]))
                                page_height = float(getattr(page.mediabox, 'height', page.mediabox.upper_right[1]))
                            except Exception:
                                # Fallback to a standard letter size if anything goes wrong
                                page_width, page_height = 612.0, 792.0

                            packet = io.BytesIO()
                            can = canvas.Canvas(packet, pagesize=(page_width, page_height))
                            can.setFont(font_name, 22)

                            # Anchor block at bottom margin and draw upwards
                            line_height = 20
                            bottom_margin = 36  # half-inch
                            start_y = bottom_margin + (len(translated_lines) - 1) * line_height
                            for idx, line in enumerate(translated_lines):
                                y = start_y - idx * line_height
                                can.drawString(start_x, y, line)

                            can.save()
                            packet.seek(0)
                            new_pdf = PyPDF2.PdfReader(packet)
                            page.merge_page(new_pdf.pages[0])
                    else:
                        if previous_page == "":
                            previous_page = text
                except AttributeError:
                    pass  # pattern not found, skip

            pdf_writer.add_page(page)

        with open(output_pdf_path, 'wb') as output_file:
            pdf_writer.write(output_file)
