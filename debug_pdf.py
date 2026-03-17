import PyPDF2
import re
import sys


def extract_sku_qty(pdf_path):
    """
    Extract Seller SKU and Qty from a TikTok packing slip PDF.
    Also prints raw extracted text per page for debugging.

    Returns a list of (sku, qty) tuples found.
    """
    results = []

    with open(pdf_path, 'rb') as f:
        reader = PyPDF2.PdfReader(f)

        for page_num, page in enumerate(reader.pages, start=1):
            raw = page.extract_text()
            if not raw:
                continue

            print(f"\n========== PAGE {page_num} RAW TEXT ==========")
            print(raw)
            print(f"========== PAGE {page_num} NORMALIZED (newlines removed) ==========")
            normalized = raw.replace("\n", " ").upper()
            print(normalized)

            # Strategy 1: Find Seller SKU label followed by the SKU value
            # TikTok packing slips label this column "Seller SKU"
            sku_matches = re.findall(r'SELLER\s+SKU[:\s]+([A-Z0-9][A-Z0-9\-]+)', normalized)
            if sku_matches:
                print(f"\n[Strategy 1 - Seller SKU label] Found: {sku_matches}")

            # Strategy 2: Find QTY...QTY block (existing approach)
            qty_block = re.search(r'QTY(.*?)QTY', normalized, re.DOTALL)
            if qty_block:
                block = qty_block.group(1)
                print(f"\n[Strategy 2 - QTY block] Content: {block!r}")
                # Extract G-BOX SKUs and their trailing numbers
                sku_qty_pairs = re.findall(r'(G-BOX[A-Z0-9\-]+?)\s*(\d+)\b', block)
                print(f"[Strategy 2] SKU+Qty pairs: {sku_qty_pairs}")

            # Strategy 3: Scan all G-BOX-like tokens
            all_gbox = re.findall(r'G-BOX[A-Z0-9\-]+', normalized)
            if all_gbox:
                print(f"\n[Strategy 3 - all G-BOX tokens] {all_gbox}")

            # Strategy 4: Look for lines with SKU + digit at end
            for line in raw.upper().split('\n'):
                m = re.match(r'\s*(G-BOX[A-Z0-9\-]+)\s+(\d+)\s*$', line.strip())
                if m:
                    sku, qty = m.group(1), m.group(2)
                    print(f"\n[Strategy 4 - line scan] SKU={sku}  QTY={qty}")
                    results.append((sku, qty))

    return results


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else "G-BOX-FD-ICE-CREAM-CUBES-VANILLA-M_20260316.pdf"
    print(f"Reading: {path}\n")
    found = extract_sku_qty(path)
    print("\n========== SUMMARY ==========")
    if found:
        for sku, qty in found:
            print(f"  SKU: {sku}  QTY: {qty}")
    else:
        print("  No SKU+Qty pairs found via line scan. Check raw text above.")
