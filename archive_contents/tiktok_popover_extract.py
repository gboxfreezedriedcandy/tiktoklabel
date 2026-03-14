
"""
tiktok_popover_extract.py - Robust Selenium helpers for TikTok Shop Arrange Shipment popover

Fixes:
  * Broader popover detection (data-tid='m4b_popover', role='tooltip', theme-arco-popover containers)
  * Groups product "blocks" by locating <main ...> sections instead of brittle class combos
  * Fallback regex parsing for "Seller SKU:" when DOM structure varies
  * Resilient QTY detection via nearest ancestor block's spinbutton

Public API:
  - wait_for_product_popover(driver, timeout=14)
  - extract_items_from_product_popover(driver, logger=None, timeout=14)
  - process_rows_and_extract(driver, logger=None, max_rows=None, per_row_delay=0.2, timeout=40)
"""

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.keys import Keys
from selenium.common.exceptions import TimeoutException, StaleElementReferenceException
import time, re


# ---------- Utilities ----------

def _scroll_into_view(driver, el):
    try:
        driver.execute_script("arguments[0].scrollIntoView({block:'center', inline:'nearest'});", el)
    except Exception:
        pass

def _text_or_none(el):
    try:
        return (el.text or "").strip()
    except Exception:
        return None

def _parse_int_safe(s, default=None):
    try:
        return int(str(s).strip())
    except Exception:
        m = re.search(r"-?\d+", str(s or ""))
        return int(m.group(0)) if m else default

# ---------- Popover detection ----------

def _first_visible(driver, xpaths, timeout_each=6):
    wait = WebDriverWait(driver, timeout_each)
    last_err = None
    for xp in xpaths:
        try:
            el = wait.until(EC.visibility_of_element_located((By.XPATH, xp)))
            return el
        except Exception as e:
            last_err = e
            continue
    if last_err:
        raise last_err
    raise TimeoutException("No matching visible element")

def wait_for_product_popover(driver, timeout=14):
    """
    Return the visible popover container; prefer the top-level wrapper that contains the form.
    """
    # try multiple selector paths
    roots = [
        "//*[@data-tid='m4b_popover' and contains(@class,'theme-arco-popover')]",
        "//*[@role='tooltip' and contains(@class,'popover')]",
        "//*[contains(@class,'theme-arco-popover-content-inner') or contains(@class,'theme-arco-popover-inner-content')]/ancestor::*[contains(@class,'theme-arco-popover')][1]",
    ]
    pop = _first_visible(driver, roots, timeout_each=max(6, timeout//2))

    # ensure the form is present/visible inside
    try:
        WebDriverWait(driver, timeout).until(
            EC.presence_of_element_located((By.XPATH, ".//form[@data-tid='m4b_form']"))
        )
    except Exception:
        # content sometimes lags; continue with pop as the container
        pass

    # additional wait: Seller SKU or spinbutton present
    try:
        WebDriverWait(driver, timeout).until(
            lambda d: pop and (
                pop.find_elements(By.XPATH, ".//*[contains(normalize-space(.), 'Seller SKU:')]")
                or pop.find_elements(By.XPATH, ".//input[@role='spinbutton']")
            )
        )
    except Exception:
        pass

    return pop

# ---------- Extraction ----------


def _extract_one_from_block(block):
    # Title
    title = None
    try:
        # text node that looks like product title (avoid Seller SKU rows)
        el = block.find_element(By.XPATH, ".//*[contains(@class,'text-p4-regular') and not(contains(normalize-space(.),'Seller SKU:'))]")
        title = _text_or_none(el)
    except Exception:
        pass

    # Variant (short label)
    variant = None
    try:
        el = block.find_element(By.XPATH, ".//*[contains(@class,'sc-') and string-length(normalize-space(.)) <= 20]")
        variant = _text_or_none(el)
    except Exception:
        pass

    # SKU
    sku = None
    try:
        sku_el = block.find_element(By.XPATH, ".//*[starts-with(normalize-space(.), 'Seller SKU:')]")
        sku_text = _text_or_none(sku_el) or ""
        if "Seller SKU:" in sku_text:
            sku = sku_text.split("Seller SKU:", 1)[1].strip() or None
    except Exception:
        # Fallback: regex over innerText
        try:
            inner = block.get_attribute("innerText") or ""
            m = re.search(r"Seller SKU:\s*(.+)", inner)
            if m:
                sku = m.group(1).strip()
        except Exception:
            pass

    # QTY
    qty = None
    # (1) Prefer spinbutton inside the same block
    try:
        qty_el = block.find_element(By.XPATH, ".//input[@role='spinbutton']")
        aria = qty_el.get_attribute("aria-valuenow")
        val = qty_el.get_attribute("value")
        qty = _parse_int_safe(aria, default=_parse_int_safe(val, default=None))
    except Exception:
        pass

    # (2) Fallback: plain text like "× 1" or "x 1" within the same block
    if qty is None:
        try:
            candidates = block.find_elements(By.XPATH, ".//div[contains(@class,'dXdoFT') or contains(normalize-space(.), '×') or contains(normalize-space(.), 'x ')]")
            for c in candidates:
                t = _text_or_none(c) or ""
                m = re.search(r"[×x]\s*(\d+)", t)
                if m:
                    qty = int(m.group(1))
                    break
        except Exception:
            pass

    return {"sku": sku, "qty": qty, "title": title, "variant": variant}

def extract_items_from_product_popover(driver, logger=None, timeout=14):
    pop = wait_for_product_popover(driver, timeout=timeout)

    # locate the true content container (form or pop itself)
    container = None
    try:
        container = pop.find_element(By.XPATH, ".//form[@data-tid='m4b_form']")
        print("yes container")
    except Exception:
        print("no container")
        container = pop

    # group products by <main ...> sections
    mains = container.find_elements(By.XPATH, ".//main[contains(@class,'sc-')]")
    items = []

    if not mains:
        print("no mains")
        # fallback: use blocks that contain a spinbutton
        blocks = container.find_elements(By.XPATH, ".//*[.//input[@role='spinbutton']]")
        if not blocks:
            # extreme fallback: parse entire popover text for a single SKU
            inner = _text_or_none(container) or ""
            m = re.search(r"Seller SKU:\s*(.+)", inner)
            if m:
                items.append({"sku": m.group(1).strip(), "qty": None, "title": None, "variant": None})
            return items

        # dedupe blocks by their closest 'data-relative=true' ancestor if present
        uniq_blocks = []
        seen = set()
        for b in blocks:
            try:
                anc = b.find_element(By.XPATH, ".//ancestor::*[@data-relative='true'][1]")
            except Exception:
                anc = b
            key = anc.id
            if key in seen:
                continue
            seen.add(key)
            uniq_blocks.append(anc)
        for b in uniq_blocks:
            items.append(_extract_one_from_block(b))
        return items

    # for each <main>, lift to its nearest block container and parse
    for m in mains:
        try:
            try:
                block = m.find_element(By.XPATH, ".//ancestor::*[@data-relative='true'][1]")
                print("yes block")
            except Exception:
                block = m.find_element(By.XPATH, ".//ancestor::*[contains(@class,'sc-')][1]")
        except Exception:
            block = m
        items.append(_extract_one_from_block(block))

    return items

# ---------- Row iteration (unchanged public API) ----------

def _wait_for_tbody(driver, timeout=40):
    wait = WebDriverWait(driver, timeout)
    for by, sel in [(By.CSS_SELECTOR, "table tbody"),
                    (By.XPATH, "//table//tbody"),
                    (By.CSS_SELECTOR, ".arco-table-content table tbody, .pulse-table table tbody")]:
        try:
            return wait.until(EC.presence_of_element_located((by, sel)))
        except Exception:
            continue
    raise TimeoutException("tbody not found")

def _rows_visible(tbody):
    try:
        return tbody.find_elements(By.XPATH, "./tr[not(contains(@style,'display: none'))]")
    except Exception:
        return tbody.find_elements(By.XPATH, "./tr")

def _find_row_click_target(row):
    for xp in [".//td[.//div[@data-log_click_for='cell_product']]//div[@data-log_click_for='cell_product']",
               ".//td[contains(@class,'theme-arco-popover-open')]",
               ".//td[contains(@class,'sc-')]",
               ".//td[1]"]:
        els = row.find_elements(By.XPATH, xp)
        if els:
            try:
                return els[0].find_element(By.XPATH, ".//*")
            except Exception:
                return els[0]
    return None

def process_rows_and_extract(driver, logger=None, max_rows=None, per_row_delay=0.2, timeout=40):
    """
    Click each visible tbody row, extract items from the popover, close it (ESC), and continue.
    Returns dict with 'items': list[list[dict]] per row; and counters.
    """
    results = {
        "processed": 0,
        "clicked": 0,
        "skipped": 0,
        "errors": 0,
        "items": [],
    }
    try:
        tbody = _wait_for_tbody(driver, timeout=timeout)
    except TimeoutException as e:
        if logger: logger.error(f"[rows_extract] tbody not ready: {e}")
        results["errors"] += 1
        return results

    idx = 0
    while True:
        try:
            rows = _rows_visible(tbody)
        except StaleElementReferenceException:
            try:
                tbody = _wait_for_tbody(driver, timeout=timeout)
                rows = _rows_visible(tbody)
            except Exception as e:
                if logger: logger.warning(f"[rows_extract] tbody stale and reacquire failed: {e}")
                results["errors"] += 1
                break

        if idx >= len(rows):
            break
        if max_rows is not None and results["processed"] >= max_rows:
            break

        row = rows[idx]
        results["processed"] += 1

        try:
            target = _find_row_click_target(row)
            if not target:
                results["skipped"] += 1
                results["items"].append([])
                idx += 1
                continue

            _scroll_into_view(driver, target)
            ActionChains(driver).move_to_element(target).pause(0.05).click(target).perform()
            results["clicked"] += 1

            items = extract_items_from_product_popover(driver, logger=logger, timeout=14)
            results["items"].append(items)

            # Close popover (ESC)
            try:
                ActionChains(driver).send_keys(Keys.ESCAPE).perform()
            except Exception:
                pass

            time.sleep(per_row_delay)
        except Exception as e:
            if logger: logger.info(f"[rows_extract] Row {idx+1} exception: {e}")
            results["errors"] += 1
            results["items"].append([])
        finally:
            idx += 1

    return results