import PyPDF2
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
import io
from reportlab.pdfgen import canvas
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfbase import pdfmetrics
from reportlab.lib.pagesizes import letter
import re

def _norm(s):
    """Normalize SKU for fuzzy matching: strip hyphens and spaces."""
    return re.sub(r'[-\s]+', '', s)


def parse_packing_slip(raw_text, debug=False, continuation=False):
    """
    Parse the new TikTok packing slip format (line-based).

    PyPDF2 extracts the table column-by-column with newlines, so a SKU like
    G-BOX-FD-ICE-CREAM-CUBES-VANILLA-M may span two lines:
        G-BOX-FD-ICE-CREAM-
        CUBES-VANILLA-M
    The qty appears on its own line immediately after the complete SKU.

    When continuation=True the function is called for a page that is a
    continuation of a multi-page packing slip. In that case the 'Packing Slip'
    header and 'SELLER SKU' column header may be absent, so both checks are
    skipped and scanning starts from line 0.

    Returns a list of (sku_upper, qty_str) tuples, or [] if this is not a
    packing slip page or no SKUs are found.
    """
    if not continuation and 'Packing Slip' not in raw_text:
        return []

    lines = raw_text.split('\n')
    upper_lines = [l.strip().upper() for l in lines]

    if continuation:
        start_idx = 0
    else:
        # Find the "Seller SKU" header line
        try:
            start_idx = next(i for i, l in enumerate(upper_lines) if l == 'SELLER SKU') + 1
        except StopIteration:
            return []

    results = []
    i = start_idx  # start scanning after the header (or from top on continuation)
    while i < len(upper_lines):
        line = upper_lines[i]

        # Footer: stop at Order ID line
        if line.startswith('ORDER ID:'):
            break

        # Detect start of a known SKU prefix (G-BOX or HAKAM)
        if line.startswith('G-BOX') or line.startswith('HAKAM'):
            sku = line
            # Join continuation lines when the accumulated SKU ends with '-'
            while sku.endswith('-') and i + 1 < len(upper_lines):
                i += 1
                sku += upper_lines[i].strip()

            # The next non-empty line after the complete SKU is the qty
            i += 1
            while i < len(upper_lines) and not upper_lines[i].strip():
                i += 1
            qty_line = upper_lines[i].strip() if i < len(upper_lines) else ''
            if qty_line.isdigit():
                if debug:
                    print(f"[packing_slip] SKU={sku}  QTY={qty_line}")
                results.append((sku, qty_line))
                i += 1
                continue

        i += 1

    return results


def replace_text_in_pdf(input_pdf_path, output_pdf_path, replacements, debug=False):
    pdfmetrics.registerFont(TTFont('SimSun', 'simsun.ttf'))  # Replace with the path to your Chinese font file
    """
    Replace text in a PDF file based on a key-value list of text replacements.

    Args:
        input_pdf_path (str): Path to the input PDF file.
        output_pdf_path (str): Path to save the modified PDF file.
        replacements (dict): A dictionary of text replacements {old_text: new_text}.

    Returns:
        None
    """
    # Open the input PDF
    with open(input_pdf_path, 'rb') as input_file:
        pdf_reader = PyPDF2.PdfReader(input_file)
        pdf_writer = PyPDF2.PdfWriter()

        # Loop through each page in the PDF
        previous_page = ""
        packing_slip_continuation = False
        count = 0
        for page in pdf_reader.pages:
            count = count + 1
            # Extract the text from the page
            text = page.extract_text()

            if text:
                print("---------")
                norm_map = [(_norm(k), k, v) for k, v in replacements.items()]
                translated_lines = []

                # --- Strategy 1: new line-based packing slip parser ---
                slip_items = parse_packing_slip(text, debug=debug)
                # If this looks like a continuation of a multi-page packing slip,
                # retry without requiring the 'Packing Slip' / 'SELLER SKU' headers.
                if not slip_items and packing_slip_continuation:
                    slip_items = parse_packing_slip(text, debug=debug, continuation=True)
                if slip_items:
                    packing_slip_continuation = True
                    previous_page = ""
                    for sku, qty_str in slip_items:
                        sku_norm = _norm(sku)
                        order_qty_text = '(' + qty_str + ')' if int(qty_str) > 1 else qty_str
                        matched = False
                        for key_norm, old_text, new_text in norm_map:
                            if key_norm not in sku_norm:
                                continue
                            translated_lines.append(order_qty_text + ' X ' + new_text)
                            matched = True
                            break
                        if not matched:
                            translated_lines.append(order_qty_text + ' X ' + '没有翻译')

                # --- Strategy 2: legacy QTY...QTY flat-text parser (fallback) ---
                if not translated_lines:
                    packing_slip_continuation = False
                    flat = text.replace("\n", "").upper()
                    flat = previous_page + flat
                    try:
                        found = re.search('QTY(.*)QTY', flat)
                        if found:
                            previous_page = ""
                            qty_region = found.group(1)
                            orders = qty_region.split("G-BOX ")
                            if orders and orders[0] == "":
                                orders.pop(0)

                            if debug:
                                print("=== LEGACY PARSER PAGE", count, "===")
                                print("=== QTY REGION ===", qty_region)
                                print("=== ITEMS ===", orders)

                            for item in orders:
                                item_norm = _norm(item)
                                matched = False
                                for key_norm, old_text, new_text in norm_map:
                                    if key_norm not in item_norm:
                                        continue
                                    qty_match = re.search(re.escape(key_norm) + r'(\d+)', item_norm)
                                    if not qty_match:
                                        continue
                                    order_qty = qty_match.group(1)
                                    order_qty_text = '(' + order_qty + ')' if order_qty.isdigit() and int(order_qty) > 1 else order_qty
                                    translated_lines.append(order_qty_text + ' X ' + new_text)
                                    matched = True
                                    break
                                if not matched:
                                    qty_match = re.search(r'(\d+)', item_norm)
                                    order_qty = qty_match.group(1) if qty_match else '?'
                                    order_qty_text = '(' + order_qty + ')' if order_qty.isdigit() and int(order_qty) > 1 else order_qty
                                    translated_lines.append(order_qty_text + ' X ' + '没有翻译')
                        else:
                            if previous_page == "":
                                previous_page = flat
                    except AttributeError:
                        pass

                # --- Render overlay if we have translations ---
                if translated_lines:
                    start_x = 50
                    try:
                        page_width = float(getattr(page.mediabox, 'width', page.mediabox.upper_right[0]))
                        page_height = float(getattr(page.mediabox, 'height', page.mediabox.upper_right[1]))
                    except Exception:
                        page_width, page_height = letter

                    packet = io.BytesIO()
                    can = canvas.Canvas(packet, pagesize=(page_width, page_height))
                    can.setFont('SimSun', 22)

                    line_height = 20
                    bottom_margin = 36
                    start_y = bottom_margin + (len(translated_lines) - 1) * line_height
                    for idx, translate in enumerate(translated_lines):
                        y = start_y - idx * line_height
                        can.drawString(start_x, y, translate)

                    can.save()
                    print(translated_lines[-1])
                    print(str(count))
                    packet.seek(0)
                    new_pdf = PyPDF2.PdfReader(packet)
                    page.merge_page(new_pdf.pages[0])

            # Add the modified page to the writer
            pdf_writer.add_page(page)

        # Write the modified content to the output PDF
        with open(output_pdf_path, 'wb') as output_file:
            pdf_writer.write(output_file)


# Example usage
replacements = {
    "G-BOX-GIFT-BOX-V1":"礼盒",
    "G-BOX-FD-CHOCOLATE-ECLAIR-M":"中(新品)巧克力雪糕",
    "G-BOX-FD-CHOCOLATE-ECLAIR-L":"大(新品)巧克力雪糕",
    "G-BOX-SOUR-WORM-GUMMY":"酸虫软糖",
    "G-BOX-WORM-GUMMY":"水果虫软糖",
    "G-BOX-CROCODILES-GUMMY":"鳄鱼软糖",
    "G-BOX-FD-JELLO-SAMPLE-PACK":"果冻礼盒",
    "G-BOX-FD-JELLO-WATERMELON-M": "中西瓜果冻",
    "G-BOX-FD-JELLO-WATERMELON-L": "大西瓜果冻",
    "CHERRY-L": "大樱桃果冻",
    "CHERRY-M": "中樱桃果冻",
    "ORANGE-L": "大橙子果冻",
    "ORANGE-M": "中橙子果冻",
    "LEMON-L-NM" : "大柠檬果冻",
    "LEMON-M-NM" : "中柠檬果冻",
    "G-BOX-FD-JELLO-LEMON-L": "大柠檬果冻",
    "G-BOX-FD-JELLO-LEMON-M": "中柠檬果冻",
    "G-BOX-FD-JELLO-LEMON-S": "小柠檬果冻",
    "G-BOX-FD-JELLO-PEACH-L" : "大桃子果冻",
    "G-BOX-FD-JELLO-PEACH-S" : "小桃子果冻",
    "G-BOX-FD-JELLO-PEACH-M" : "中桃子果冻",
    "LIME-L" : "大青柠檬果冻",
    "LIME-M" : "中青柠檬果冻",
    "G-BOX-FD-JELLO-STRAWBERRY-L" : "大草莓果冻",
    "G-BOX-FD-JELLO-STRAWBERRY-M" : "中草莓果冻",
    "G-BOX-FD-JELLO-STRAWBERRY-S" : "小草莓果冻",
    "G-BOX-FD-JELLO-STRAWBERRY-PINK-L" : "大粉色草莓果冻",
    "G-BOX-FD-JELLO-STRAWBERRY-PINK-M" : "中粉色草莓果冻",
    "G-BOX-FD-JELLO-STRAWBERRY-PINK-S" : "小粉色草莓果冻",
    "G-BOX-FD-JELLO-BLUEBERRY-L" : "大蓝莓果冻",
    "G-BOX-FD-JELLO-BLUEBERRY-M" : "中蓝莓果冻",
    "G-BOX-FD-JELLO-BLUEBERRY-S" : "小蓝莓果冻",
    "G-BOX-FD-JELLO-PINEAPPLE-L" : "大菠萝果冻",
    "G-BOX-FD-JELLO-PINEAPPLE-M" : "中菠萝果冻",
    "RANCH-CUCUMBER-LARGE" : "大沙拉黄瓜",
    "G-BOX-PICKLES-SMALL" : "小酸黄瓜",
    "G-BOX-PICKLES-MEDIUM" : "中酸黄瓜",
    "G-BOX-PICKLES-LARGE" : "大酸黄瓜",
    "G-BOX-CHAMOY-PICKLES-LARGE" : "大辣的酸黄瓜",
    "G-BOX-CHAMOY-PICKLES-LARGE" : "大辣的酸黄瓜",
    "G-BOX-CHAMOY-PICKLES-SMALL" : "小辣的酸黄瓜",
    "CHAMOY-CUCUMBER-LARGE": "大辣的黄瓜",
    "G-BOX-FRUIT-ROLL-UP-L-CHQT " : "大彩虹卷糖",
    "G-BOX-FRUIT-ROLL-UP-M-CHQT " : "中彩虹卷糖",
    "G-BOX-FRUIT-ROLL-UP-L" : "大彩虹卷糖",
    "G-BOX-FRUIT-ROLL-UP-M" : "中彩虹卷糖",
    "G-BOX-FD-LEMONCANDY-8OZ": "大柠檬糖",
    "LEMONCANDY-4OZ": "中柠檬糖",
    "G-BOX-FD-GUMMY-BEAR": "大熊软糖",
    "G-BOX-FD-FROZEN-GUMMY-BEAR": "大熊软糖",
    "G-BOX-FD-AIR-CRUNCH-BBT": "大扁扁糖",
    "G-BOX-FD-AIR-CRUNCH": "大扁扁糖",
    "G-BOX-SOUR-FRETTLE-SMALL":"小酸彩虹糖",
    "FREEZE DRIEDFRETTLES SOUR FLAVORAIR-TIGHT SEALED IN ADELI CONTAINERDEFAULT":"小酸彩虹糖",
    "G-BOX-SOUR-MEDIUM":"中酸彩虹糖",
    "G-BOX-FD-FRETTLES-LARGE":"大原味彩虹糖",
    "G-BOX-SOUR-FRETTLE-LARGE": "大酸彩虹糖",
    "G-BOX-FD-FRETTLES-SMALL":"小原味彩虹糖",
    "G-BOX-FD-FRETTLES-MEDIUM":"中原味彩虹糖",
    "G-BOX-FD-WILDBERRY-SMALL": "小野梅彩虹糖",
    "G-BOX-FD-MARSHMALLOWS-MINI":"大棉花糖",
    "G-BOX-FD-MARSHMALLOWS-CAR-M":"（焦）中棉花焦糖",
    "G-BOX-FD-MARSHMALLOWS-CAR-L":"（焦）大棉花焦糖",
    "LARGE-FD-MARSHMALLOWS-CAR":"（焦）大棉花焦糖",
    "G-BOX-LARGE-GUMMY-CLUSTER": "大红色点点糖",
    "G-BOX-FD-ICECREAM-SANDWICH-3OZ":"中三明治雪糕",
    "G-BOX-FD-ICECREAM-SANDWICH-7OZ":"大三明治雪糕",
    "G-BOX-FD-STRAWBERRY-SHORTCAKE-S":"小碎块草莓雪糕(碎块)",
    "G-BOX-FD-STRAWBERRY-SHORTCAKE-M":"中草莓雪糕",
    "G-BOX-FD-STRAWBERRY-SHORTCAKE-L":"大草莓雪糕",
    "G-BOX-FD-ICE-CREAM-CUBES-VANILLA-M":"中香草方块",
    "G-BOX-FD-ICE-CREAM-CUBES-VANILLA-L" : "大香草方块",
    "G-BOX-FD-ICECREAMCUBESVANILLA-L" : "大香草方块",
    "G-BOX-FD-ICE-CREAMCUBES-VANILLA-M": "中香草方块",
    "G-BOX-FD-ICE-CREAMCUBES-VANILLA-L": "大香草方块",
    "G-BOX-FD-ICE-CREAM-CUBES-CHOCOLATE-M":"中巧克力方块",
    "G-BOX-FD-ICE-CREAM-CUBES-CHOCOLATE-L":"大巧克力方块",
    "G-BOX-FD-ICE-CREAMCUBES-CHOCOLATE-M": "中巧克力方块",
    "G-BOX-FD-ICE-CREAMCUBES-CHOCOLATE-L": "大巧克力方块",
    "G-BOX-CHAMOY-FRETTLES-MEDIUM":"中辣彩虹糖",
    "G-BOX-CHAMOY-FRETTLES-LARGE": "大辣彩虹糖",
    "G-BOX-CHAMOY-MEDIUM":"中辣彩虹糖",
    "G-BOX-CHAMOY-LARGE": "大辣彩虹糖",
    "G-BOX-PEACH-RING" : "大原味桃圈圈糖",
    "G-BOX-CHAMOY-PEACH-RING":"大辣味桃圈圈糖",
    "G-BOX-FD-STRAWBERRY-GUMMY":"大草莓软糖",
    "G-BOX-FD-WATERMELON-GUMMY":"大西瓜软糖",
    "G-BOX-FD-HONEY-CANDY":"大棕色蜜蜂圆糖",
    "G-BOX-SUBSCRIPTION-BOX-V1":"大礼盒",
    "G-BOX-FD-FRETTLES-XLARGE":"特大原味彩虹糖",
    "FREEZE DRIEDSKITTLES SMOOTHIEFLAVOR AIR-TIGHT SEALEDIN A DELI CONTAINERDEFAULT":"小粉红冰沙彩虹糖",
    "G-BOX-FD-GUMMY-FROGS-3": "青蛙3只包装",
    "G-BOX-FD-TAFFY-COTTON-CANDY": "粉太妃糖",
    "G-BOX-FD-TAFFY-VANILLA":"香草太妃糖-白色",
    "G-BOX-FD-TAFFY-WATERMELON": "西瓜太妃糖",
    "G-BOX-FD-TAFFY-BANANA": "香蕉太妃糖",
    "G-BOX-FD-TAFFY-PEPPERMINT": "薄荷太妃糖",
    "G-BOX-FD-TAFFY-GREEN-APPLE": "青苹果太妃糖",
    "G-BOX-FD-TAFFY-SHAVED-ICE" : "刨冰太妃糖",
    "G-BOX-FD-TAFFY-KIWI-STRAWBERRY" : "草莓太妃糖",
    "G-BOX-FD-TAFFY-BLACKBERRY-CRUMBLE" : "莓子太妃糖",
    "G-BOX-FD-CHOCO-CRUNCH-L":"大巧克力饼干糖",
    "G-BOX-FD-CHOCO-CRUNCH-M":"小巧克力饼干糖",
    "G-BOX-FD-FRETTLES-SOUR-XLARGE":"酸特大彩虹糖(酸)",
    "G-BOX-SOUR-FRETTLE-MEDIUM":"中酸彩虹糖（酸）",
    "G-BOX-FREESES-M" : "中花生雪糕",
    "G-BOX-FREESES-L" : "大花生雪糕",
    "G-BOX-CHAMOY-FRETTLES-XL-JAR" : "特大辣彩虹糖(辣)",
    "G-BOX-FD-DUBAI-CHOCOLATE-M":"中迪拜巧克力",
    "G-BOX-FD-JELLO-BB-LEMON-L":"大蓝绿混合果冻",
    "G-BOX-FD-JELLO-BB-LEMON-M":"中蓝绿混合果冻",
    "G-BOX-FD-DUBAI-CHOCOLATE-L":"大迪拜巧克力",
    "G-BOX-FDS-ORI-CANDY-CANE-10": "10条原味拐杖",
    "G-BOX-CANDY-CANE-VARIETY-10": "10条混合拐杖",
    "G-BOX-CANDY-CANE-CAR-MARSH-10": "10条白棉花拐杖",
    "HAKAM-MEDIUM-ORIGINAL-FRETTLES": "中原味彩虹糖",
    "HAKAM-SMALL-ORIGINAL-FRETTLES": "小原味彩虹糖",
    "HAKAM-LARGE-ORIGINAL-FRETTLES": "大原味彩虹糖",
    "G-BOX-FD-JELLO-CHERRY-L": "大樱桃果冻",
    "G-BOX-FD-JELLO-CHERRY-S": "小樱桃果冻",
    "G-BOX-FD-JELLO-CHERRY-M": "中樱桃果冻",
    "G-BOX-SOUR-SMALL": "小酸彩虹糖",
    "G-BOX-SOUR-LARGE": "大酸彩虹糖",
    "G-BOX-FRETTLES-LARGE": "大原味彩虹糖",
    "G-BOX-FRETTLES-SMALL": "小原味彩虹糖",
    "G-BOX-FRETTLES-MEDIUM": "中原味彩虹糖",
    "G-BOX-FD-WATERMELON-GUMMY-CANDY": "大西瓜软糖",
    "G-BOX-FD-TAFFY-WATERMELON-CANDY": "西瓜太妃糖",
    "G-BOX-FD-DUBAI-CHOCOLATE-S": "小迪拜巧克力(碎块)",
    "G-BOX-FD-GUMMY-SOUR-WORM": "酸虫软糖",
    "G-BOX-FD-CANDY-CORN-L": "万圣玉米糖",
    "G-BOX-FD-CANDY-CO": "万圣玉米糖",
    "G-BOX-FD-ICE-CREAM-CUBES-VANILLA-S": "小香草方块（碎块）",
    "G-BOX-FD-CC-ICECREAM-SANDWICH-WHOLE": "小三明治",
}

hakam_replacements = {
    "G-BOX-FD-STRAWBERRY-SHORTCAKE-M":"中草莓雪糕",
    "G-BOX-FD-STRAWBERRY-SHORTCAKE-L":"大草莓雪糕",
    "G-BOX-FD-ICE-CREAM-CUBES-VANILLA-M":"中香草方块",
    "G-BOX-FD-ICE-CREAM-CUBES-VANILLA-L":"大香草方块",
    "G-BOX-FD-ICE-CREAMCUBES-VANILLA-M": "中香草方块",
    "G-BOX-FD-ICE-CREAMCUBES-VANILLA-L": "大香草方块",
    "G-BOX-FD-ICE-CREAM-CUBES-CHOCOLATE-M":"中巧克力方块",
    "G-BOX-FD-ICE-CREAM-CUBES-CHOCOLATE-L":"大巧克力方块",
    "G-BOX-FD-ICE-CREAMCUBES-CHOCOLATE-M": "中巧克力方块",
    "G-BOX-FD-ICE-CREAMCUBES-CHOCOLATE-L": "大巧克力方块",
    "HAKAM-SMALL-ORIGINAL-FRETTLES":"小原味彩虹糖",
    "HAKAM-MEDIUM-ORIGINAL-FRETTLES":"中原味彩虹糖",
    "HAKAM-LARGE-ORIGINAL-FRETTLES":"大原味彩虹糖",
    "G-BOX-SOUR-SMALL": "小酸彩虹糖",
    "G-BOX-SOUR-MEDIUM": "中酸彩虹糖",
    "G-BOX-SOUR-LARGE": "大酸彩虹糖",
    "G-BOX-FD-JELLO-LEMON-L": "大柠檬果冻",
    "G-BOX-FD-JELLO-LEMON-M": "中柠檬果冻",
    "G-BOX-FD-JELLO-LEMON-S": "小柠檬果冻",
    "G-BOX-FD-JELLO-PINEAPPLE-L" : "大菠萝果冻",
    "G-BOX-FD-JELLO-PINEAPPLE-S" : "小菠萝果冻",
    "G-BOX-FD-JELLO-PINEAPPLE-M" : "中菠萝果冻",
    "G-BOX-FD-JELLO-CHERRY-L": "大樱桃果冻",
    "G-BOX-FD-JELLO-CHERRY-S": "小樱桃果冻",
    "G-BOX-FD-JELLO-CHERRY-M": "中樱桃果冻",
    "G-BOX-FD-JELLO-ORANGE-L": "大橙子果冻",
    "G-BOX-FD-JELLO-ORANGE-S": "小橙子果冻",
    "G-BOX-FD-JELLO-ORANGE-M": "中橙子果冻",
    "G-BOX-FD-JELLO-LIME-L" : "大青柠檬果冻",
    "G-BOX-FD-JELLO-LIME-S" : "小青柠檬果冻",
    "G-BOX-FD-JELLO-LIME-M" : "中青柠檬果冻",
    "G-BOX-FD-JELLO-STRAWBERRY-L": "大草莓果冻",
    "G-BOX-FD-JELLO-STRAWBERRY-S": "小草莓果冻",
    "G-BOX-FD-JELLO-STRAWBERRY-M": "中草莓果冻",
    "G-BOX-FD-JELLO-WATERMELON-S": "小西瓜果冻",
    "G-BOX-FD-JELLO-WATERMELON-M": "中西瓜果冻",
    "G-BOX-FD-JELLO-WATERMELON-L": "大西瓜果冻",
    "G-BOX-FD-FRETTLES-XLARGE":"特大原味彩虹糖",
    "G-BOX-SUBSCRIPTION-BOX-V1":"大礼盒",
    "G-BOX-FD-STRAWBERRY-GUMMY":"大草莓软糖",
    "G-BOX-FD-WATERMELON-GUMMY":"大西瓜软糖",
    "G-BOX-FD-TAFFY-COTTON-CANDY": "粉太妃",
    "G-BOX-FD-TAFFY-WATERMELON-CANDY": "西瓜味太妃糖-粉红加绿色",
    "G-BOX-FD-TAFFY-VANILLA-CANDY":"香草太妃糖-白色",
    "G-BOX-FD-HONEY-CANDY":"大棕色蜜蜂圆糖",
    "G-BOX-FD-GUMMY-BEAR": "大熊软糖",
    "G-BOX-FD-FROZEN-GUMMY-BEAR": "大冷冻熊软糖",
    "G-BOX-FD-FRETTLES-SOUR-XLARGE":"酸特大彩虹糖(酸)",
    "G-BOX-FD-AIR-CRUNCH-BBT": "大扁扁糖",
    "G-BOX-FD-GUMMY-WORM":"水果虫软糖",
    "G-BOX-FREESES-M" : "中花生雪糕",
    "G-BOX-FREESES-L" : "大花生雪糕",
    "G-BOX-FD-JELLO-BLUEBERRY-M":"中蓝莓果冻",
    "G-BOX-FD-JELLO-STRAWBERRY-PINK-M":"中粉红草莓果冻",
    "G-BOX-FD-DUBAI-CHOCOLATE-M":"中迪拜巧克力",
    "G-BOX-FD-JELLO-BB-LEMON-L":"大蓝绿混合果冻",
    "G-BOX-FD-JELLO-BB-LEMON-M":"中蓝绿混合果冻",
    "G-BOX-FD-DUBAI-CHOCOLATE-L":"大迪拜巧克力"
}

gboxcandyshop_replacement = {
    "G-BOX-FD-HONEY-CANDY":"大棕色蜜蜂圆糖",
    "G-BOX-FD-JELLO-WATERMELON-S": "小西瓜果冻",
    "G-BOX-FRUIT-ROLL-UP-L" : "大彩虹卷卷卷糖",
    "G-BOX-FRUIT-ROLL-UP-M" : "中彩虹卷卷卷糖",
    "G-BOX-FD-JELLO-WATERMELON-M": "中西瓜果冻",
    "G-BOX-FD-JELLO-WATERMELON-L": "大西瓜果冻",
    "G-BOX-FD-JELLO-CHERRY-L": "大樱桃果冻",
    "G-BOX-FD-JELLO-CHERRY-M": "中樱桃果冻",
    "G-BOX-FD-JELLO-ORANGE-L": "大橙子果冻",
    "G-BOX-FD-JELLO-ORANGE-M": "中橙子果冻",
    "G-BOX-FD-JELLO-PEACH-L" : "大桃子果冻",
    "G-BOX-FD-JELLO-PEACH-M" : "中桃子果冻",
    "G-BOX-FD-JELLO-LEMON-L" : "大柠檬果冻",
    "G-BOX-FD-JELLO-LEMON-M" : "中柠檬果冻",
    "G-BOX-FD-JELLO-LIME-L" : "大青柠檬果冻",
    "G-BOX-FD-JELLO-LIME-M" : "中青柠檬果冻",
    "G-BOX-FD-JELLO-STRAWBERRY-L" : "大草莓果冻",
    "G-BOX-FD-JELLO-STRAWBERRY-M" : "中草莓果冻",
    "G-BOX-FD-JELLO-PINEAPPLE-L" : "大菠萝果冻",
    "G-BOX-FD-JELLO-PINEAPPLE-M" : "中菠萝果冻",
    "RANCH-CUCUMBER-LARGE" : "大沙拉黄瓜",
    "G-BOX-PICKLES-SMALL" : "小酸黄瓜",
    "G-BOX-PICKLES-LARGE" : "大酸黄瓜",
    "G-BOX-CHAMOY-PICKLES-LARGE" : "大辣的酸黄瓜",
    "G-BOX-CHAMOY-PICKLES-SMALL" : "小辣的酸黄瓜",
    "CHAMOY-CUCUMBER-LARGE": "大辣的黄瓜",
    "FRUIT-ROLL-UP-L-CHQT" : "大彩虹卷卷卷糖",
    "FRUIT-ROLL-UP-M-CHQT" : "小彩虹卷卷卷糖",
    "LEMONCANDY-8OZ": "大柠檬糖",
    "LEMONCANDY-4OZ": "中柠檬糖",
    "G-BOX-FD-GUMMY-BEAR": "大熊软糖",
    "G-BOX-FD-FROZEN-GUMMY-BEAR": "大冷冻熊软糖",
    "G-BOX-FD-AIR-CRUNCH-BBT": "大扁扁糖",
    "G-BOX-SOUR-SMALL":"小酸彩虹糖",
    "G-BOX-SOUR-MEDIUM":"中酸彩虹糖",
    "G-BOX-SOUR-LARGE": "大酸彩虹糖",
    "G-BOX-FRETTLES-SMALL":"小原味彩虹糖",
    "G-BOX-FRETTLES-MEDIUM":"中原味彩虹糖",
    "G-BOX-FRETTLES-LARGE": "大原味彩虹糖",
    "G-BOX-CRC-SMALL":"小原味彩虹糖",
    "G-BOX-CRC-MEDIUM":"中原味彩虹糖",
    "G-BOX-CRC-LARGE": "大原味彩虹糖",
    "G-BOX-FD-WILDBERRY-SMALL": "小野梅彩虹糖",
    "LARGE-FD-MARSHMALLOWS-MINI":"大棉花糖",
    "SMALL-FD-MARSHMALLOWS-CAR":"（焦）小棉花焦糖",
    "LARGE-FD-MARSHMALLOWS-CAR":"（焦）大棉花焦糖",
    "G-BOX-LARGE-GUMMY-CLUSTER": "大红色点点糖",
    "G-BOX-FD-ICECREAM-SANDWICH-3OZ":"小雪糕饼干",
    "G-BOX-FD-ICECREAM-SANDWICH-7OZ":"大雪糕饼干",
    "G-BOX-FD-STRAWBERRY-SHORTCAKE-S":"小草莓雪糕雪条",
    "G-BOX-FD-STRAWBERRY-SHORTCAKE-M":"中草莓雪糕雪条",
    "G-BOX-FD-STRAWBERRY-SHORTCAKE-L":"大草莓雪糕雪条",
    "G-BOX-FD-ICE-CREAM-CUBES-VANILLA-M":"中香草雪糕方块",
    "G-BOX-FD-ICE-CREAM-CUBES-VANILLA-L":"大香草雪糕方块",
    "G-BOX-FD-ICE-CREAMCUBES-VANILLA-M": "中香草雪糕方块",
    "G-BOX-FD-ICE-CREAMCUBES-VANILLA-L": "大香草雪糕方块",
    "G-BOX-FD-ICE-CREAM-CUBES-CHOCOLATE-M":"中巧克力雪糕方块",
    "G-BOX-FD-ICE-CREAM-CUBES-CHOCOLATE-L":"大巧克力雪糕方块",
    "G-BOX-FD-ICE-CREAMCUBES-CHOCOLATE-M": "中巧克力雪糕方块",
    "G-BOX-FD-ICE-CREAMCUBES-CHOCOLATE-L": "大巧克力雪糕方块",
    "G-BOX-CHAMOY-MEDIUM":"中辣彩虹糖",
    "G-BOX-CHAMOY-LARGE": "大辣彩虹糖",
    "G-BOX-PEACH-RING" : "大原味桃圈圈糖",
    "G-BOX-CHAMOY-PEACH-RING":"大辣味桃圈圈糖",
    "G-BOX-PEACH-RING-CHAMOY":"大辣味桃圈糖",
    "G-BOX-FD-STRAWBERRY-GUMMY":"大草莓软糖",
    "G-BOX-FD-WATERMELON-GUMMY":"大西瓜软糖",
    "G-BOX-SUBSCRIPTION-BOX-V1":"大礼盒",
    "FREEZE DRIEDFRETTLES IN JARCONTAINER 22OZ":"特大原味彩虹糖",
    "G-BOX-FD-FRETTLES-XLARGE":"特大原味彩虹糖",
    "G-BOX-FD-FRETTLES-SOUR-XLARGE":"酸特大彩虹糖酸",
    "CRUNCHYRAINBOW CANDY FREEZEDRIED FRETTLES ORIGINALFLAVOR IN TUB JARCONTAINER SNACKBONBONDEFAULT":"特大彩虹糖",
    "FREEZE DRIEDSKITTLES SMOOTHIEFLAVOR AIR-TIGHT SEALEDIN A DELI CONTAINERDEFAULT":"小粉红冰沙彩虹糖",
    "G-BOX-FD-GUMMY-FROGS-3": "青蛙3只包装",
    "G-BOX-FD-CHOCO-CRUNCH-L":"大巧克力饼干糖",
    "G-BOX-FD-CHOCO-CRUNCH-M":"小巧克力饼干糖",
    "G-BOX-FD-TAFFY-COTTON-CANDY": "粉太妃",
    "G-BOX-FD-TAFFY-VANILLA":"香草太妃糖-白色",
    "G-BOX-FD-TAFFY-WATERMELON": "西瓜太妃糖-粉红加绿色",
    "G-BOX-FD-TAFFY-BANANA": "香蕉太妃糖-黄加粉红色",
    "G-BOX-FD-TAFFY-PEPPERMINT": "薄荷太妃糖-白加粉红色",
    "G-BOX-FD-TAFFY-GREEN-APPLE": "青苹果太妃糖-绿色",
    "G-BOX-FD-TAFFY-SHAVED-ICE" : "刨冰太妃糖",
    "G-BOX-FD-TAFFY-KIWI-STRAWBERRY" : "草莓太妃糖",
    "G-BOX-FD-TAFFY-BLACKBERRY-CRUMBLE" : "莓子太妃糖",
    "G-BOX-FREESES-M" : "中花生雪糕",
    "G-BOX-FREESES-L" : "大花生雪糕",
    "G-BOX-FD-DUBAI-CHOCOLATE-M":"中迪拜巧克力",
    "G-BOX-FD-JELLO-BB-LEMON-L":"大蓝绿混合果冻",
    "G-BOX-FD-JELLO-BB-LEMON-M":"中蓝绿混合果冻",
    "G-BOX-FD-DUBAI-CHOCOLATE-L":"大迪拜巧克力"
}

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Overlay Chinese product name translations onto a PDF shipping label.")
    parser.add_argument("input", help="Input PDF path")
    parser.add_argument("output", help="Output PDF path")
    parser.add_argument("--store", choices=["gbox", "hakam", "gboxcandyshop"], default="gbox",
                        help="Which replacement dictionary to use (default: gbox)")
    parser.add_argument("--debug", action="store_true",
                        help="Print raw extracted text and parsed items per page")
    args = parser.parse_args()

    store_map = {
        "gbox": replacements,
        "hakam": hakam_replacements,
        "gboxcandyshop": gboxcandyshop_replacement,
    }
    replace_text_in_pdf(args.input, args.output, store_map[args.store], debug=args.debug)
