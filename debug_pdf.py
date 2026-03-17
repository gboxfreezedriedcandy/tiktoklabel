import PyPDF2
import re
import sys
from pdf_replace_text import parse_packing_slip, _norm


def extract_sku_qty(pdf_path):
    """
    Diagnostic tool for TikTok packing slip PDFs.
    Focuses on the Packing Slip page and shows exactly what PyPDF2 extracts
    so the parser in pdf_replace_text.py can be tuned to match.
    """
    with open(pdf_path, 'rb') as f:
        reader = PyPDF2.PdfReader(f)
        total = len(reader.pages)
        print(f"Total pages: {total}\n")

        for page_num, page in enumerate(reader.pages, start=1):
            raw = page.extract_text() or ""
            upper = raw.upper()

            is_packing_slip = "PACKING SLIP" in upper
            print(f"{'='*60}")
            print(f"PAGE {page_num}  {'<<< PACKING SLIP >>>' if is_packing_slip else '(not packing slip)'}")
            print(f"{'='*60}")

            # --- 1. Raw text with newlines preserved ---
            print("\n[1] RAW TEXT (newlines preserved):")
            print(raw)

            # --- 2. Line-by-line with highlights ---
            print("\n[2] LINE-BY-LINE (lines with G-BOX / HAKAM / QTY / SELLER SKU highlighted):")
            for i, line in enumerate(raw.split('\n')):
                tag = ""
                u = line.upper()
                if 'G-BOX' in u:
                    tag = " <<< G-BOX"
                elif 'HAKAM' in u:
                    tag = " <<< HAKAM"
                elif 'QTY' in u:
                    tag = " <<< QTY"
                elif 'SELLER SKU' in u:
                    tag = " <<< SELLER SKU"
                print(f"  {i:3d}: {line!r}{tag}")

            # --- 2b. parse_packing_slip() called directly ---
            print("\n[2b] parse_packing_slip() DIRECT OUTPUT:")
            print(f"  'Packing Slip' in raw text : {'Packing Slip' in raw}")
            upper_lines = [l.strip().upper() for l in raw.split('\n')]
            seller_sku_exact = [i for i, l in enumerate(upper_lines) if l == 'SELLER SKU']
            print(f"  Exact 'SELLER SKU' line(s) : {seller_sku_exact}")
            slip_items = parse_packing_slip(raw, debug=True)
            print(f"  Returned items             : {slip_items}")

            # --- 3. Simulate existing pdf_replace_text.py logic ---
            print("\n[3] EXISTING PARSER SIMULATION (newlines removed, uppercased):")
            flat = raw.replace("\n", "").upper()
            print(f"  flat text: {flat[:300]}{'...' if len(flat)>300 else ''}")

            found = re.search(r'QTY(.*)QTY', flat)
            if found:
                region = found.group(1)
                print(f"\n  QTY...QTY region: {region!r}")
                orders = region.split("G-BOX ")
                if orders and orders[0] == "":
                    orders.pop(0)
                print(f"\n  After split('G-BOX '): {orders}")
                for item in orders:
                    item_norm = _norm(item)
                    print(f"\n    item      : {item!r}")
                    print(f"    item_norm : {item_norm!r}")
            else:
                print("  *** QTY...QTY pattern NOT FOUND in flat text ***")

            # --- 4. Seller SKU column approach ---
            print("\n[4] SELLER SKU COLUMN APPROACH:")
            lines = raw.split('\n')
            in_sku_section = False
            for i, line in enumerate(lines):
                u = line.upper().strip()
                if 'SELLER SKU' in u and 'QTY' in u:
                    in_sku_section = True
                    print(f"  Found header row at line {i}: {line!r}")
                    continue
                if in_sku_section:
                    if re.search(r'TOTAL\s*QTY', u) or re.search(r'TOTAL\s*:\s*\d', u):
                        print(f"  End of items at line {i}: {line!r}")
                        in_sku_section = False
                        continue
                    gbox = re.search(r'(G-BOX[A-Z0-9\-]+)', line.upper())
                    qty = re.search(r'\b(\d+)\s*$', line.strip())
                    print(f"  Row {i}: {line!r}  =>  SKU={gbox.group(1) if gbox else 'NOT FOUND'}  QTY={qty.group(1) if qty else 'NOT FOUND'}")

            # --- 5. All G-BOX / HAKAM tokens found anywhere on page ---
            all_gbox = re.findall(r'G-BOX[A-Z0-9\-]+', upper)
            print(f"\n[5] ALL G-BOX TOKENS ON PAGE: {all_gbox}")
            all_hakam = re.findall(r'HAKAM[A-Z0-9\-]+', upper)
            print(f"[5b] ALL HAKAM TOKENS ON PAGE: {all_hakam}")

            # --- 6. All lines ending with a digit (likely qty column) ---
            print("\n[6] LINES ENDING WITH A DIGIT (candidate qty rows):")
            for i, line in enumerate(raw.split('\n')):
                if re.search(r'\d\s*$', line.strip()) and line.strip():
                    print(f"  {i:3d}: {line!r}")

            print()


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else "G-BOX-FD-ICE-CREAM-CUBES-VANILLA-M_20260316.pdf"
    print(f"Reading: {path}\n")
    extract_sku_qty(path)
