
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.keys import Keys
from selenium.common.exceptions import (
    TimeoutException,
    StaleElementReferenceException,
    ElementClickInterceptedException,
    NoSuchElementException,
)
import time
import re
from tiktok_popover_extract import extract_items_from_product_popover
import tiktok_selectors as sel
from typing import List, Optional

# SKU -> weight (first duplicate kept)
SKU_WEIGHT_PAIRS = [
    ("G-BOX-GIFT-BOX-V1", 2),
    ("G-BOX-FD-CHOCOLATE-ECLAIR-M", 0.3),
    ("G-BOX-FD-CHOCOLATE-ECLAIR-L", 0.59375),
    ("G-BOX-SOUR-WORM-GUMMY", 0.24375),
    ("G-BOX-WORM-GUMMY", 0.2375),
    ("G-BOX-CROCODILES-GUMMY", 0.2375),
    ("G-BOX-FD-JELLO-SAMPLE-PACK", 1.75),
    ("G-BOX-FD-JELLO-WATERMELON-M", 0.19375),
    ("G-BOX-FD-JELLO-WATERMELON-L", 0.35625),
    ("G-BOX-FD-JELLO-CHERRY-L", 0.3625),
    ("G-BOX-FD-JELLO-CHERRY-M", 0.20625),
    ("G-BOX-FD-JELLO-LEMON-L", 0.38125),
    ("G-BOX-FD-JELLO-LEMON-M", 0.2125),
    ("G-BOX-FD-JELLO-PEACH-L", 0.375),
    ("G-BOX-FD-JELLO-PEACH-M", 0.2),
    ("G-BOX-FD-JELLO-STRAWBERRY-L", 0.375),
    ("G-BOX-FD-JELLO-STRAWBERRY-M", 0.20625),
    ("G-BOX-FD-JELLO-STRAWBERRY-PINK-L", 0.325),
    ("G-BOX-FD-JELLO-STRAWBERRY-PINK-M", 0.2),
    ("G-BOX-FD-JELLO-BLUEBERRY-L", 0.35625),
    ("G-BOX-FD-JELLO-BLUEBERRY-M", 0.20625),
    ("G-BOX-FD-JELLO-LIME-L", 0.36875),
    ("G-BOX-FD-JELLO-LIME-M", 0.19375),
    ("G-BOX-FD-JELLO-ORANGE-L", 0.4),
    ("G-BOX-FD-JELLO-ORANGE-M", 0.20625),
    ("G-BOX-FD-JELLO-PINEAPPLE-L", 0.3625),
    ("G-BOX-FD-JELLO-PINEAPPLE-M", 0.20625),
    ("RANCH-CUCUMBER-LARGE", 0.18125),
    ("G-BOX-PICKLES-SMALL", 0.11875),
    ("G-BOX-PICKLES-MEDIUM", 0.11875),
    ("G-BOX-PICKLES-LARGE", 0.18125),
    ("G-BOX-CHAMOY-PICKLES-LARGE", 0.2625),
    ("G-BOX-CHAMOY-PICKLES-SMALL", 0.14375),
    ("CHAMOY-CUCUMBER-LARGE", 0.2625),
    ("G-BOX-FRUIT-ROLL-UP-L", 0.375),
    ("G-BOX-FRUIT-ROLL-UP-M", 0.21875),
    ("G-BOX-FD-LEMONCANDY-8OZ", 0.625),
    ("LEMONCANDY-4OZ", 0.3125),
    ("G-BOX-FD-GUMMY-BEAR", 0.5625),
    ("G-BOX-FD-FROZEN-GUMMY-BEAR", 0.5625),
    ("G-BOX-FD-AIR-CRUNCH", 0.4),
    ("G-BOX-SOUR-FRETTLE-SMALL", 0.275),
    ("G-BOX-SOUR-MEDIUM", 0.41875),
    ("G-BOX-FD-FRETTLES-LARGE", 0.8),
    ("G-BOX-SOUR-FRETTLE-LARGE", 0.79375),
    ("G-BOX-FD-FRETTLES-SMALL", 0.275),
    ("G-BOX-FD-FRETTLES-MEDIUM", 0.4625),
    ("G-BOX-FD-WILDBERRY-SMALL", 0.23125),
    ("G-BOX-FD-MARSHMALLOWS-MINI", 0.3375),
    ("G-BOX-FD-MARSHMALLOWS-CAR-M", 0.35625),
    ("G-BOX-FD-MARSHMALLOWS-CAR-L", 0.5375),
    ("G-BOX-LARGE-GUMMY-CLUSTER", 0.4875),
    ("G-BOX-FD-ICECREAM-SANDWICH-3OZ", 0.3375),
    ("G-BOX-FD-ICECREAM-SANDWICH-7OZ", 0.59375),
    ("G-BOX-FD-STRAWBERRY-SHORTCAKE-S", 0.203125),
    ("G-BOX-FD-STRAWBERRY-SHORTCAKE-M", 0.2625),
    ("G-BOX-FD-STRAWBERRY-SHORTCAKE-L", 0.53125),
    ("G-BOX-FD-ICE-CREAM-CUBES-VANILLA-M", 0.24375),
    ("G-BOX-FD-ICE-CREAM-CUBES-VANILLA-L", 0.44375),
    ("G-BOX-FD-ICECREAMCUBESVANILLA-L", 0.44375),
    ("G-BOX-FD-ICE-CREAM-CUBES-CHOCOLATE-M", 0.2875),
    ("G-BOX-FD-ICE-CREAM-CUBES-CHOCOLATE-L", 0.43125),
    ("G-BOX-CHAMOY-FRETTLES-MEDIUM", 0.45625),
    ("G-BOX-CHAMOY-FRETTLES-LARGE", 0.8),
    ("G-BOX-CHAMOY-MEDIUM", 0.45625),
    ("G-BOX-CHAMOY-LARGE", 0.8),
    ("G-BOX-PEACH-RING", 0.33125),
    ("G-BOX-CHAMOY-PEACH-RING", 0.34375),
    ("G-BOX-FD-STRAWBERRY-GUMMY", 0.3),
    ("G-BOX-FD-WATERMELON-GUMMY", 0.475),
    ("G-BOX-FD-HONEY-CANDY", 0.475),
    ("G-BOX-SUBSCRIPTION-BOX-V1", 2),
    ("G-BOX-FD-FRETTLES-XLARGE", 1.5625),
    ("G-BOX-FD-GUMMY-FROGS-3", 0.21875),
    ("G-BOX-FD-TAFFY-COTTON-CANDY", 0.28125),
    ("G-BOX-FD-TAFFY-VANILLA", 0.33125),
    ("G-BOX-FD-TAFFY-WATERMELON", 0.25),
    ("G-BOX-FD-TAFFY-BANANA", 0.2375),
    ("G-BOX-FD-TAFFY-PEPPERMINT", 0.2625),
    ("G-BOX-FD-TAFFY-GREEN-APPLE", 0.28125),
    ("G-BOX-FD-TAFFY-SHAVED-ICE", 0.3125),
    ("G-BOX-FD-TAFFY-KIWI-STRAWBERRY", 0.28125),
    ("G-BOX-FD-TAFFY-BLACKBERRY-CRUMBLE", 0.325),
    ("G-BOX-FD-CHOCO-CRUNCH-L", 0.5),
    ("G-BOX-FD-CHOCO-CRUNCH-M", 0.24375),
    ("G-BOX-FD-FRETTLES-SOUR-XLARGE", 1.8125),
    ("G-BOX-SOUR-FRETTLE-MEDIUM", 0.35),
    ("G-BOX-FREESES-M", 0.3375),
    ("G-BOX-FREESES-L", 0.625),
    ("G-BOX-CHAMOY-FRETTLES-XL-JAR", 1.875),
    ("G-BOX-FD-JELLO-BB-LEMON-L", 0.35),
    ("G-BOX-FD-JELLO-BB-LEMON-M", 0.20625),
    ("G-BOX-FD-DUBAI-CHOCOLATE-L", 0.75625),
    ("G-BOX-FD-DUBAI-CHOCOLATE-M", 0.4125),
    ("G-BOX-FD-DUBAI-CHOCOLATE-S", 0.1875),
]

#above 4 container dimensions
WIDTH = 10
LENGTH = 12
HEIGHT = 6

SKU_WEIGHT_MAP = {}
for sku, weight in SKU_WEIGHT_PAIRS:
    # keep first seen if duplicates exist
    SKU_WEIGHT_MAP.setdefault(sku, weight)

def _scroll_into_view(driver, el):
    try:
        driver.execute_script("arguments[0].scrollIntoView({block:'center', inline:'nearest'});", el)
    except Exception:
        pass

def _click_safely(driver, el, timeout_each=8):
    """Try a normal click, then ActionChains, then JS click."""
    try:
        _scroll_into_view(driver, el)
        el.click()
        return True
    except Exception:
        pass

    try:
        _scroll_into_view(driver, el)
        ActionChains(driver).move_to_element(el).pause(0.05).click(el).perform()
        return True
    except Exception:
        pass

    try:
        driver.execute_script("arguments[0].click();", el)
        return True
    except Exception:
        return False

def _find_click_target_in_row(row):
    """Return the best clickable 'product cell' element inside the row (td or a descendant)."""
    # Priority 1: explicit cell_product marker
    try:
        cell_product = row.find_elements(By.XPATH, ".//td[.//div[@data-log_click_for='cell_product']]//div[@data-log_click_for='cell_product']")
        if cell_product:
            return cell_product[0]
    except Exception:
        pass

    # Priority 2: td with theme-arco-popover-open
    try:
        cells = row.find_elements(By.XPATH, ".//td[contains(@class,'theme-arco-popover-open')]")
        if cells:
            return cells[0]
    except Exception:
        pass

    # Priority 3: td with sc-cVMLIT (class from your snippet)
    try:
        cells = row.find_elements(By.XPATH, ".//td[contains(@class,'sc-')]")
        if cells:
            try:
                inner = cells[0].find_elements(By.XPATH, ".//button|.//a|.//*[@role='button']|.//*")
                if inner:
                    return inner[0]
            except Exception:
                pass
            return cells[0]
    except Exception:
        pass

    # Fallback: first table cell
    try:
        first_td = row.find_elements(By.XPATH, ".//td[1]")
        if first_td:
            return first_td[0]
    except Exception:
        pass

    return None

def _find_weight_target_in_row(row):
    """Find the weight cell inside the row and return a clickable element for it."""
    # Primary: explicit package weight marker
    xps = [
        ".//td[.//div[@data-log_click_for='cell_package_weight']]//div[@data-log_click_for='cell_package_weight']",
        ".//td[.//div[@data-log_click_for='cell_package_weight']]",
        # Classes from the provided snippet
        ".//td[contains(@class,'sc-')]//div[@data-log_click_for='cell_package_weight']",
        ".//td[contains(@class,'sc-')]",
        # Last resort: any td containing text with units
        ".//td[.//*[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),' lb') or contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),' kg')]]",
    ]
    for xp in xps:
        try:
            els = row.find_elements(By.XPATH, xp)
            if els:
                el = els[0]
                # Prefer the innermost descendant if this is a td
                try:
                    inner = el.find_element(By.XPATH, ".//div[@data-log_click_for='cell_package_weight']")
                    return inner
                except Exception:
                    return el
        except Exception:
            continue
    return None

def _find_dimension_target_in_row(row):
    """Find the dimension (package size) cell inside the row."""
    xps = [
        ".//td[.//div[@data-log_click_for='cell_package_size']]//div[@data-log_click_for='cell_package_size']",
        ".//td[.//div[@data-log_click_for='cell_package_size']]",
        # Broad fallback: any td that contains 'Custom size' or ' x ' pattern
        ".//td[contains(@class,'sc-')]//div[@data-log_click_for='cell_package_size']",
        ".//td[contains(@class,'sc-')]",
        ".//td[.//*[contains(normalize-space(),'Product dimensions') or contains(normalize-space(),'Product dimensions')]]",
        ".//td[.//*[contains(normalize-space(),' x ') and contains(normalize-space(),'in')]]",
    ]
    for xp in xps:
        try:
            els = row.find_elements(By.XPATH, xp)
            if els:
                el = els[0]
                # prefer inner clickable div if present
                try:
                    inner = el.find_element(By.XPATH, ".//div[@data-log_click_for='cell_package_size']")
                    return inner
                except Exception:
                    return el
        except Exception:
            continue
    return None

def _clear_and_type(driver, inp, value):
    try:
        _scroll_into_view(driver, inp)
        driver.execute_script("arguments[0].focus();", inp)
    except Exception:
        pass
    time.sleep(0.05)
    try:
        inp.clear(); time.sleep(0.05)
    except Exception:
        pass
    try:
        inp.send_keys(Keys.CONTROL, "a"); inp.send_keys(Keys.BACK_SPACE)
    except Exception:
        pass
    try:
        inp.send_keys(Keys.COMMAND, "a"); inp.send_keys(Keys.BACK_SPACE)
    except Exception:
        pass
    try:
        driver.execute_script(
            "arguments[0].value='';"
            "arguments[0].dispatchEvent(new Event('input', {bubbles:true}));"
            "arguments[0].dispatchEvent(new Event('change', {bubbles:true}));",
            inp
        )
    except Exception:
        pass
    try:
        existing = (inp.get_attribute("value") or "").strip()
        if existing:
            for _ in range(len(existing) + 5):
                inp.send_keys(Keys.BACK_SPACE)
            time.sleep(0.02)
    except Exception:
        pass
    inp.send_keys(str(value))
    time.sleep(0.05)
    return True

def set_package_dimensions(driver, length_val: float, width_val: float, height_val: float) -> bool:
    """Set package L/W/H in whichever UI is present (inline inputs or drawer).
    Tries several selector patterns for Arco/pulse variants.
    """
    # Possible selectors for each input
    length_candidates = [
        "input#packageLength_input",
        "input[data-id='fulfillment.create_shipping_label.input.package_length']",
        "//label[@for='packageLength']/following::input[1]",
        "//label[.//span[normalize-space()='Length']]/following::input[1]",
        "//div[contains(@class,'package') and contains(translate(.,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'length')]//input",
    ]
    width_candidates = [
        "input#packageWidth_input",
        "input[data-id='fulfillment.create_shipping_label.input.package_width']",
        "//label[@for='packageWidth']/following::input[1]",
        "//label[.//span[normalize-space()='Width']]/following::input[1]",
        "//div[contains(@class,'package') and contains(translate(.,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'width')]//input",
    ]
    height_candidates = [
        "input#packageHeight_input",
        "input[data-id='fulfillment.create_shipping_label.input.package_height']",
        "//label[@for='packageHeight']/following::input[1]",
        "//label[.//span[normalize-space()='Height']]/following::input[1]",
        "//div[contains(@class,'package') and contains(translate(.,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'height')]//input",
    ]

    ok_any = False
    # For each, find and type
    try:
        print(" length")
        lin = _find_first(driver, length_candidates, timeout=6)
        _clear_and_type(driver, lin, length_val)
        ok_any = True
    except Exception:
        print("Exception length")
        pass
    try:
        print(" width")
        win = _find_first(driver, width_candidates, timeout=6)
        _clear_and_type(driver, win, width_val)
        ok_any = True
    except Exception:
        print("Exception width")
        pass
    try:
        print(" height")
        hin = _find_first(driver, height_candidates, timeout=6)
        _clear_and_type(driver, hin, height_val)
        ok_any = True
    except Exception:
        print("Exception height")
        pass

    # Blur the last field to ensure change events
    try:
        ActionChains(driver).send_keys(Keys.TAB).perform()
    except Exception:
        pass
    time.sleep(0.1)
    return ok_any

def wait_for_arrange_shipment_tbody(driver, timeout=40):
    """Wait until a tbody is present on the Arrange Shipment page; return the element or raise TimeoutException."""
    wait = WebDriverWait(driver, timeout)
    # Accept multiple table structures
    candidates = [
        (By.CSS_SELECTOR, "table tbody"),
        (By.XPATH, "//table//tbody"),
        (By.CSS_SELECTOR, ".arco-table-content table tbody, .pulse-table table tbody"),
    ]
    last_err = None
    for by, sel in candidates:
        try:
            return wait.until(EC.presence_of_element_located((by, sel)))
        except Exception as e:
            last_err = e
            continue
    # If none matched, bubble the last timeout
    if isinstance(last_err, Exception):
        raise last_err
    raise TimeoutException("Could not locate <tbody> on Arrange Shipment page.")

def visible_rows_in_tbody(tbody):
    """Return list of visible <tr> nodes (excludes display:none)."""
    try:
        return tbody.find_elements(By.XPATH, "./tr[not(contains(@style,'display: none'))]")
    except Exception:
        return tbody.find_elements(By.XPATH, "./tr")

def process_arrange_shipment_tbody_rows(driver, logger=None, max_rows=None, timeout=40, per_row_delay=0.2, click_weight=True, weight_click_delay=0.15):
    """
    Iterate table tbody rows on Arrange Shipment and click one target element per row.
    Then click the row's weight element (cell_package_weight) when available.
    Returns: dict with counts and per-row results.

    :param driver: Selenium WebDriver
    :param logger: optional logger with .info/.warning/.error
    :param max_rows: int or None; if set, process at most this many rows
    :param timeout: wait timeout for tbody discovery
    :param per_row_delay: delay after each primary click to let UI react
    :param click_weight: whether to click the weight cell after the first click
    :param weight_click_delay: delay after the weight click
    """
    results = {
        "processed": 0,
        "clicked": 0,
        "skipped": 0,
        "errors": 0,
        "weight_clicked": 0,
        "rows": [],  # list of dicts: {"index": i, "clicked": bool, "reason": str|None, "weight_clicked": bool, "weight_reason": str|None}
    }
    try:
        tbody = wait_for_arrange_shipment_tbody(driver, timeout=timeout)
    except TimeoutException as e:
        if logger: logger.error(f"[row_processor] tbody not ready: {e}")
        results["errors"] += 1
        return results

    # We re-query rows on each loop to avoid stale issues when the table updates dynamically.
    idx = 0
    while True:
        try:
            current_rows = visible_rows_in_tbody(tbody)
            #print("current rows")
        except StaleElementReferenceException:
            # tbody went stale, reacquire
            try:
                tbody = wait_for_arrange_shipment_tbody(driver, timeout=timeout)
                current_rows = visible_rows_in_tbody(tbody)
            except Exception as e:
                if logger: logger.warning(f"[row_processor] tbody stale and reacquire failed: {e}")
                results["errors"] += 1
                break

        if idx >= len(current_rows):
            break
        if max_rows is not None and results["processed"] >= max_rows:
            break

        row = current_rows[idx]
        row_info = {"index": idx+1, "clicked": False, "reason": None, "weight_clicked": False, "weight_reason": None}
        results["processed"] += 1
        #print(row)
        try:
            # Primary click (product cell)
            _scroll_into_view(driver, row)
            target = _find_click_target_in_row(row)
            if not target:
                row_info["reason"] = "no_click_target"
                results["skipped"] += 1
                if logger: logger.info(f"[row_processor] Row {idx+1}: no suitable click target")
            else:
                ok = _click_safely(driver, target)
                if not ok:
                    row_info["reason"] = "click_failed"
                    results["errors"] += 1
                    if logger: logger.warning(f"[row_processor] Row {idx+1}: click failed")
                else:
                    time.sleep(per_row_delay)
                    # after clicking the row's product cell and the popover appears
                    items = extract_items_from_product_popover(driver, logger=logger, timeout=60)
                    # -> [{'sku': 'G-BOX-FD-STRAWBERRY-SHORTCAKE-L', 'qty': 1, 'title': '...', 'variant': '7oz'}, ...]
                    #print(items)
                    total, count, missing = total_weight_from_items(items)
                    print("TOTAL =", total)       # sums mapped weight * qty
                    print("COUNT =", count)   # total count
                    print("MISSING =", missing)   # any SKUs not in the map
                    row_info["clicked"] = True
                    results["clicked"] += 1
                    if logger: logger.info(f"[row_processor] Row {idx+1}: clicked product cell")
                    time.sleep(per_row_delay)


                    # Optional follow-up: click weight cell
                    if click_weight:
                        try:
                            # If a popover opened and blocks clicks, try closing with ESC first

                            try:
                                ActionChains(driver).send_keys(Keys.ESCAPE).perform()
                                time.sleep(0.05)
                            except Exception:
                                pass


                            wtarget = _find_weight_target_in_row(row)
                            if wtarget is None:
                                row_info["weight_reason"] = "no_weight_target"
                                if logger: logger.info(f"[row_processor] Row {idx+1}: no weight cell found")
                            else:
                                wok = _click_safely(driver, wtarget)
                                if wok:
                                    row_info["weight_clicked"] = True
                                    results["weight_clicked"] += 1
                                    if logger: logger.info(f"[row_processor] Row {idx+1}: clicked weight cell")
                                    time.sleep(weight_click_delay)

                                    ok = set_weight_and_apply(driver, total)
                                    # After applying weight, the row may refresh; reacquire by index
                                    try:
                                        new_row = _reacquire_row_by_index(driver, idx)
                                        if new_row is not None:
                                            row = new_row
                                    except Exception:
                                        pass
                                else:
                                    row_info["weight_reason"] = "weight_click_failed"
                                    results["errors"] += 1
                                    if logger: logger.warning(f"[row_processor] Row {idx+1}: weight click failed")
                            time.sleep(per_row_delay)
                        except Exception as e:
                            row_info["weight_reason"] = f"exception:{type(e).__name__}"
                            results["errors"] += 1
                            if logger: logger.info(f"[row_processor] Row {idx+1}: weight exception: {e}")
                    
                    # If item count is large, set dimensions first
                    try:
                        if count >= 4:
                            time.sleep(weight_click_delay)
                            # Close any product popover first so clicks aren't blocked
                            try:
                                print("Escape Pressed")
                                ActionChains(driver).send_keys(Keys.ESCAPE).perform(); time.sleep(0.05)
                                time.sleep(0.05)
                            except Exception:
                                print("Exception 1")
                                pass
                            dtarget = _find_dimension_target_in_row(row)
                            if dtarget is not None:
                                print("Dimension Element Found")
                                time.sleep(weight_click_delay)
                                dok = _click_safely(driver, dtarget)
                                if dok:
                                    #row_info["dimension_clicked"] = True
                                    #results["dimension_clicked"] += 1
                                    time.sleep(weight_click_delay)
                                    set_package_dimensions(driver, LENGTH, WIDTH, HEIGHT)
                    except Exception:
                        pass
                    time.sleep(weight_click_delay)

        except (StaleElementReferenceException, ElementClickInterceptedException, NoSuchElementException) as e:
            row_info["reason"] = f"exception:{type(e).__name__}"
            results["errors"] += 1
            if logger: logger.info(f"[row_processor] Row {idx+1} exception: {e}")
        except Exception as e:
            row_info["reason"] = f"exception:{type(e).__name__}"
            results["errors"] += 1
            if logger: logger.error(f"[row_processor] Row {idx+1} unexpected: {e}")
        finally:
            results["rows"].append(row_info)
            idx += 1

    return results

'''
def process_arrange_shipment_tbody_rows(driver, logger=None, max_rows=None, timeout=40, per_row_delay=0.2, click_weight=True, weight_click_delay=0.15):
    """
    Iterate table tbody rows on Arrange Shipment and click one target element per row.
    Then click the row's weight element (cell_package_weight) when available.
    Returns: dict with counts and per-row results.

    :param driver: Selenium WebDriver
    :param logger: optional logger with .info/.warning/.error
    :param max_rows: int or None; if set, process at most this many rows
    :param timeout: wait timeout for tbody discovery
    :param per_row_delay: delay after each primary click to let UI react
    :param click_weight: whether to click the weight cell after the first click
    :param weight_click_delay: delay after the weight click
    """
    results = {
        "processed": 0,
        "clicked": 0,
        "skipped": 0,
        "errors": 0,
        "weight_clicked": 0,
        "rows": [],  # list of dicts: {"index": i, "clicked": bool, "reason": str|None, "weight_clicked": bool, "weight_reason": str|None}
    }
    try:
        tbody = wait_for_arrange_shipment_tbody(driver, timeout=timeout)
    except TimeoutException as e:
        if logger: logger.error(f"[row_processor] tbody not ready: {e}")
        results["errors"] += 1
        return results

    # We re-query rows on each loop to avoid stale issues when the table updates dynamically.
    idx = 0
    try:
        current_rows = visible_rows_in_tbody(tbody)
        #print("current rows")
    except StaleElementReferenceException:
        # tbody went stale, reacquire
        try:
            tbody = wait_for_arrange_shipment_tbody(driver, timeout=timeout)
            current_rows = visible_rows_in_tbody(tbody)
        except Exception as e:
            if logger: logger.warning(f"[row_processor] tbody stale and reacquire failed: {e}")
            results["errors"] += 1

    for row in current_rows:
        row = current_rows[idx]
        row_info = {"index": idx+1, "clicked": False, "reason": None, "weight_clicked": False, "weight_reason": None}
        results["processed"] += 1
        #print(row)
        try:
            # Primary click (product cell)
            #_scroll_into_view(driver, row)
            target = _find_click_target_in_row(row)
            if not target:
                print("no target row")
                row_info["reason"] = "no_click_target"
                results["skipped"] += 1
                if logger: logger.info(f"[row_processor] Row {idx+1}: no suitable click target")
            else:
                print("target row")
                ok = _click_safely(driver, target)
                if not ok:
                    row_info["reason"] = "click_failed"
                    results["errors"] += 1
                    if logger: logger.warning(f"[row_processor] Row {idx+1}: click failed")
                else:
                    #from tiktok_popover_extract import extract_items_from_product_popover

                    # after clicking the row's product cell and the popover appears
                    #items = extract_items_from_product_popover(driver, logger=logger, timeout=60)
                    # -> [{'sku': 'G-BOX-FD-STRAWBERRY-SHORTCAKE-L', 'qty': 1, 'title': '...', 'variant': '7oz'}, ...]
                    #print(items)
                    row_info["clicked"] = True
                    results["clicked"] += 1
                    if logger: logger.info(f"[row_processor] Row {idx+1}: clicked product cell")
                    time.sleep(per_row_delay)

                    # Optional follow-up: click weight cell
                    if click_weight:
                        try:
                            # If a popover opened and blocks clicks, try closing with ESC first
                            try:
                                ActionChains(driver).send_keys(Keys.ESCAPE).perform()
                                time.sleep(0.05)
                            except Exception:
                                pass

                            wtarget = _find_weight_target_in_row(row)
                            if wtarget is None:
                                row_info["weight_reason"] = "no_weight_target"
                                if logger: logger.info(f"[row_processor] Row {idx+1}: no weight cell found")
                            else:
                                wok = _click_safely(driver, wtarget)
                                if wok:
                                    row_info["weight_clicked"] = True
                                    results["weight_clicked"] += 1
                                    if logger: logger.info(f"[row_processor] Row {idx+1}: clicked weight cell")
                                    time.sleep(weight_click_delay)
                                else:
                                    row_info["weight_reason"] = "weight_click_failed"
                                    results["errors"] += 1
                                    if logger: logger.warning(f"[row_processor] Row {idx+1}: weight click failed")
                            time.sleep(per_row_delay)
                        except Exception as e:
                            row_info["weight_reason"] = f"exception:{type(e).__name__}"
                            results["errors"] += 1
                            if logger: logger.info(f"[row_processor] Row {idx+1}: weight exception: {e}")

        except (StaleElementReferenceException, ElementClickInterceptedException, NoSuchElementException) as e:
            row_info["reason"] = f"exception:{type(e).__name__}"
            results["errors"] += 1
            if logger: logger.info(f"[row_processor] Row {idx+1} exception: {e}")
        except Exception as e:
            row_info["reason"] = f"exception:{type(e).__name__}"
            results["errors"] += 1
            if logger: logger.error(f"[row_processor] Row {idx+1} unexpected: {e}")
        finally:
            results["rows"].append(row_info)
            idx += 1

    return results
'''

def total_weight_from_items(
    items: list[dict],
    sku_weights: dict[str, int] = SKU_WEIGHT_MAP,
    default_weight: int = 0,
    assume_qty_if_missing: int = 1,
):
    """
    items: list of dicts like {'sku': '...', 'qty': 2, ...}
    Returns (total_weight, missing_skus)
    """
    total = 0
    missing = []
    count = 0
    for it in items or []:
        sku = ((it.get("sku") or "").strip().strip('"').strip("'"))
        if not sku:
            continue
        qty = it.get("qty")
        if qty is None:
            qty = assume_qty_if_missing
        try:
            qty = int(qty)
        except Exception:
            qty = assume_qty_if_missing

        w = sku_weights.get(sku)
        if w is None:
            # try a sanitized key
            alt = sku.replace('“','"').replace('”','"').strip('"').strip("'")
            w = sku_weights.get(alt)
        if w is None:
            missing.append(sku)
            w = default_weight
        count = count + qty
        total += w * qty
    return total, count, missing

def total_weight_from_rows_summary(summary: dict, **kw):
    """
    Works with process_rows_and_extract(...) output where summary['items'] is a list of rows,
    each row is a list of item dicts.
    """
    flat = []
    for row_items in (summary or {}).get("items", []):
        flat.extend(row_items or [])
    return total_weight_from_items(flat, **kw)


def _find_first(driver, selectors: List[str], timeout: float = 10):
    end = time.time() + timeout

    def css_or_xpath(s):
        if s.startswith('//'):
            try:
                return driver.find_element(By.XPATH, s)
            except Exception:
                return None
        if ":has-text(" in s:
            import re
            m = re.search(r":has-text\(\s*(['\"])\s*(.*?)\s*\1\s*\)", s)
            if m:
                text = m.group(2)
            else:
                text = (s.split(":has-text(", 1)[1].split(")", 1)[0].strip().strip("'\""))
            base = s.split(":has-text(", 1)[0]
            try:
                els = driver.find_elements(By.CSS_SELECTOR, base)
            except Exception:
                els = []
            if not els and not base.startswith("//"):
                try:
                    els = driver.find_elements(By.XPATH, base)
                except Exception:
                    els = []
            for el in els:
                try:
                    if text.lower() in (el.text or "").lower():
                        return el
                except Exception:
                    continue
            return None
        try:
            return driver.find_element(By.CSS_SELECTOR, s)
        except Exception:
            try:
                return driver.find_element(By.XPATH, s)
            except Exception:
                return None

    while time.time() < end:
        for s in selectors:
            el = css_or_xpath(s)
            if el:
                return el
        time.sleep(0.25)
    raise TimeoutException(f"Could not find any of: {selectors}")

def click_if_present(driver, selectors: List[str], timeout=3):
    try:
        el = _find_first(driver, selectors, timeout)
        try:
            driver.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
        except Exception:
            pass
        time.sleep(0.1)
        try:
            el.click()
        except Exception:
            driver.execute_script("arguments[0].click();", el)
        time.sleep(0.5)
        return True
    except Exception:
        return False
    
def _wait_for_loading_to_finish(driver, timeout: float = 10.0):
    """Best-effort wait for global loading spinners to disappear."""
    end = time.time() + timeout
    while time.time() < end:
        try:
            # Look for any of the generic loading indicators defined in selectors
            spinners = []
            for s in (sel.SHIP_LOADING + sel.LOADING):
                try:
                    # find_elements returns [] if none
                    if s.startswith('//'):
                        found = driver.find_elements(By.XPATH, s)
                    else:
                        found = driver.find_elements(By.CSS_SELECTOR, s)
                except Exception:
                    found = []
                spinners.extend(found or [])
            # If any displayed spinner, keep waiting
            any_vis = False
            for el in spinners:
                try:
                    if el.is_displayed():
                        any_vis = True
                        break
                except Exception:
                    # stale/hidden is fine
                    continue
            if not any_vis:
                return True
        except Exception:
            pass
        time.sleep(0.2)
    return False


def _reacquire_row_by_index(driver, index: int, timeout: float = 8.0):
    """After a refresh, reacquire tbody and return the row at given index (0-based)."""
    try:
        tbody = wait_for_arrange_shipment_tbody(driver, timeout=timeout)
    except Exception:
        return None
    # Poll a moment for rows to stabilize
    end = time.time() + timeout
    last_len = -1
    stable = 0
    rows = []
    while time.time() < end:
        try:
            rows = visible_rows_in_tbody(tbody)
        except StaleElementReferenceException:
            try:
                tbody = wait_for_arrange_shipment_tbody(driver, timeout=timeout)
                rows = visible_rows_in_tbody(tbody)
            except Exception:
                time.sleep(0.2)
                continue
        if len(rows) == last_len and len(rows) > 0:
            stable += 1
        else:
            stable = 0
            last_len = len(rows)
        if stable >= 3:
            break
        time.sleep(0.2)
    if 0 <= index < len(rows):
        return rows[index]
    return None


def set_weight_and_apply(driver, weight_value: float) -> bool:
    """Set weight in the inline editor, then apply/save and wait for the row refresh.

    Handles both inline Enter-submit and explicit Apply button flows.
    Returns True if input was set and an apply action was attempted.
    """
    try:
        inp = _find_first(driver, sel.SINGLE_WEIGHT_INPUT, timeout=8)

        try:
            driver.execute_script("arguments[0].scrollIntoView({block:'center'});", inp)
            driver.execute_script("arguments[0].focus();", inp)
        except Exception:
            pass
        time.sleep(0.1)

        # Thoroughly clear the input before typing
        try:
            inp.clear(); time.sleep(0.05)
        except Exception:
            pass

        try:
            inp.send_keys(Keys.CONTROL, "a"); inp.send_keys(Keys.BACK_SPACE)
        except Exception:
            pass
        try:
            inp.send_keys(Keys.COMMAND, "a"); inp.send_keys(Keys.BACK_SPACE)
        except Exception:
            pass

        try:
            driver.execute_script(
                "arguments[0].value='';"
                "arguments[0].dispatchEvent(new Event('input', {bubbles:true}));"
                "arguments[0].dispatchEvent(new Event('change', {bubbles:true}));",
                inp
            )
        except Exception:
            pass

        try:
            existing = (inp.get_attribute("value") or "").strip()
            if existing:
                for _ in range(len(existing) + 5):
                    inp.send_keys(Keys.BACK_SPACE)
                time.sleep(0.05)
        except Exception:
            pass

        inp.send_keys(str(weight_value))
        time.sleep(0.15)

        # Try Enter to submit inline editor (common pattern)
        try:
            inp.send_keys(Keys.ENTER)
            time.sleep(0.15)
        except Exception:
            pass

        # Try explicit Apply button(s) if present
        try:
            click_if_present(driver, sel.BATCH_EDIT_APPLY, timeout=2)
        except Exception:
            pass

        # Best-effort wait for any loading and DOM stabilization
        _wait_for_loading_to_finish(driver, timeout=8.0)
        time.sleep(0.2)
        return True

    except Exception:
        return False
