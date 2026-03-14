
# [PATCHED v5.5.4] Pre-handle custom flag --mix-order to avoid argparse errors
try:
    import sys, os
    _argv = list(sys.argv)
    if '--mix-order' in _argv:
        i = _argv.index('--mix-order')
        _val = (_argv[i+1] if i+1 < len(_argv) else 'yes').lower()
        os.environ['MIX_ORDER'] = '1' if _val in ('yes','y','1','true','on') else '0'
        # remove the flag + value so other parsers don't error
        del _argv[i: i+2 if i+1 < len(_argv) else i+1]
        sys.argv = _argv
    if 'MIX_ORDER' not in os.environ:
        os.environ['MIX_ORDER'] = '0'
except Exception:
    pass
import os
import argparse
import json
import sys
import time
import requests
from pdf_replace import replace_text_in_pdf
# --- PDF download config ---
ENABLE_PDF_DOWNLOAD = True
PDF_DOWNLOAD_DIR = 'downloads'
PDF_APPEND_PRODUCT = True
PDF_PRODUCT_NAME = None

from datetime import datetime
from pathlib import Path
from typing import List, Optional
import logging
from logging.handlers import RotatingFileHandler

from selenium import webdriver
from selenium.common.exceptions import TimeoutException, WebDriverException, StaleElementReferenceException
from selenium.webdriver.chrome.service import Service as ChromeService
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains

import boto3
from pathlib import Path
from config import (
    LOGIN_URL, USERNAME, PASSWORD, COOKIES_JSON, SCREENSHOTS_DIR, HEADLESS,
    USER_DATA_DIR, PROFILE_DIR, ORDERS_PATHS, ARTIFACTS, base_origin
)
import tiktok_selectors as sel
from aws_lambda_powertools import Logger
logger = Logger()  # level via env: LOG_LEVEL=INFO

__VERSION__ = "v5.4"

PDF_REPLACE = True
PDF_REPLACE_JSON = "./replacements.json"
PDF_FONT_PATH = "./artifacts/SimSun.ttf"


def upload_screenshots():
    bucket = os.getenv("ARTIFACTS_S3_BUCKET")
    if not bucket:
        return
    root = Path(os.getenv("TT_ARTIFACTS_DIR", "/tmp/tiktok_artifacts")) / "screenshots"
    if not root.exists():
        return
    s3 = boto3.client("s3")
    for shot in root.glob("*.png"):
        key = f"screenshots/{shot.name}"
        s3.upload_file(str(shot), bucket, key)

def _options():
    from selenium.webdriver.chrome.options import Options
    opts = Options()
    '''
    if HEADLESS:
        opts.add_argument("--headless=new")
    opts.add_argument("--start-maximized")
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_argument("--disable-notifications")
    opts.add_experimental_option("excludeSwitches", ["enable-automation"])
    opts.add_experimental_option("useAutomationExtension", False)
    opts.add_argument("--disable-gpu")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    if USER_DATA_DIR:
        opts.add_argument(f"--user-data-dir={USER_DATA_DIR}")
    if PROFILE_DIR:
        opts.add_argument(f"--profile-directory={PROFILE_DIR}")
    opts.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
    chrome_binary = os.getenv("CHROME_BINARY")
    if chrome_binary:
        opts.binary_location = chrome_binary
    '''
    opts.binary_location = os.getenv("CHROME_BINARY", "/opt/chrome/chrome")
    opts.add_argument("--headless=chrome")
    opts.add_argument("--window-size=1280,720")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--disable-software-rasterizer")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-dev-tools")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-setuid-sandbox")
    opts.add_argument("--disable-extensions")
    opts.add_argument("--disable-features=VizDisplayCompositor,TranslateUI")
    opts.add_argument("--single-process")
    opts.add_argument("--remote-debugging-port=9222")

    profile_root = os.path.join("/tmp", "chrome-profile")
    os.makedirs(profile_root, exist_ok=True)
    opts.add_argument(f"--user-data-dir={profile_root}")
    opts.add_argument(f"--data-path={os.path.join(profile_root, 'data')}")
    opts.add_argument(f"--disk-cache-dir={os.path.join(profile_root, 'cache')}")

    prefs = {
        "download.default_directory": PDF_DOWNLOAD_DIR,
        "download.prompt_for_download": False,
        "download.directory_upgrade": True,
        "plugins.always_open_pdf_externally": False  # True = send to system viewer; False = retain in Chrome
    }
    opts.add_experimental_option("prefs", prefs)

    return opts




def setup_logging():
    from config import LOG_DIR, LOG_LEVEL, LOG_MAX_BYTES, LOG_BACKUP_COUNT
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = LOG_DIR / f"run_{ts}.log"
    err_path = LOG_DIR / "errors.log"

    logger = logging.getLogger()
    logger.setLevel(getattr(logging, LOG_LEVEL, logging.INFO))
    # File handler (rotating)
    fh = RotatingFileHandler(log_path, maxBytes=LOG_MAX_BYTES, backupCount=LOG_BACKUP_COUNT)
    fh.setLevel(getattr(logging, LOG_LEVEL, logging.INFO))
    fmt = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")
    fh.setFormatter(fmt)
    logger.addHandler(fh)
    # Error file handler
    eh = RotatingFileHandler(err_path, maxBytes=LOG_MAX_BYTES, backupCount=LOG_BACKUP_COUNT)
    eh.setLevel(logging.ERROR)
    eh.setFormatter(fmt)
    logger.addHandler(eh)
    # Console
    ch = logging.StreamHandler()
    ch.setLevel(getattr(logging, LOG_LEVEL, logging.INFO))
    ch.setFormatter(fmt)
    logger.addHandler(ch)
    logging.info("Logging initialized. File: %s", log_path)
    return log_path

def dump_browser_logs(driver, label="browser_last"):
    from config import LOG_DIR, BROWSER_LOGS
    if not BROWSER_LOGS:
        return None
    out = LOG_DIR / f"{label}.log"
    try:
        logs = driver.get_log('browser') if driver else []
    except Exception:
        logs = []
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        with open(out, "w", encoding="utf-8") as f:
            for entry in logs or []:
                ts = entry.get("timestamp")
                lvl = entry.get("level")
                msg = entry.get("message")
                f.write(f"{ts} | {lvl} | {msg}\n")
        logging.info("Wrote browser console logs to %s", out)
    except Exception as e:
        logging.debug("Could not write browser logs: %s", e)
    return out
def _driver():
    opts = _options()
    try:
        driver = webdriver.Chrome(options=opts)
    except WebDriverException as first_error:
        logging.warning("Selenium Manager failed to provision ChromeDriver automatically: %s", first_error)
        driver_path = os.getenv("CHROMEDRIVER_BINARY")
        if driver_path:
            logging.info("Falling back to ChromeDriver at %s", driver_path)
        else:
            driver_version = os.getenv("CHROMEDRIVER_VERSION")
            try:
                driver_path = ChromeDriverManager(version=driver_version).install()
            except Exception as manager_error:
                logging.error("webdriver-manager could not supply ChromeDriver: %s", manager_error)
                raise first_error
        service = ChromeService(driver_path)
        driver = webdriver.Chrome(service=service, options=opts)
    driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
        "source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
    })
    return driver


def save_screenshot(driver, label: str):
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = SCREENSHOTS_DIR / f"{label}_{ts}.png"
    driver.save_screenshot(str(path))
    return path

def save_screenshot2(driver, label: str):
    #ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    #path = SCREENSHOTS_DIR / f"{label}_{ts}.png"
    #driver.save_screenshot(str(path))
    #return path
    pass


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


def _find_first_visible(driver, selectors: List[str], timeout: float = 10):
    """Locate the first displayed element matching any selector."""
    end = time.time() + timeout

    def _iter_candidates(selector):
        if selector.startswith('//'):
            try:
                return driver.find_elements(By.XPATH, selector)
            except Exception:
                return []
        if ":has-text(" in selector:
            import re
            m = re.search(r":has-text\(\s*(['\"])\s*(.*?)\s*\1\s*\)", selector)
            if m:
                text = m.group(2)
            else:
                text = (selector.split(":has-text(", 1)[1].split(")", 1)[0].strip().strip("'\""))
            base = selector.split(":has-text(", 1)[0]
            try:
                elements = driver.find_elements(By.CSS_SELECTOR, base)
            except Exception:
                elements = []
            if not elements and base.startswith("//"):
                try:
                    elements = driver.find_elements(By.XPATH, base)
                except Exception:
                    elements = []
            matches = []
            for el in elements:
                try:
                    if text.lower() in (el.text or "").lower():
                        matches.append(el)
                except Exception:
                    continue
            return matches
        try:
            elements = driver.find_elements(By.CSS_SELECTOR, selector)
        except Exception:
            elements = []
        if not elements:
            try:
                elements = driver.find_elements(By.XPATH, selector)
            except Exception:
                elements = []
        return elements

    while time.time() < end:
        for selector in selectors:
            for el in _iter_candidates(selector):
                try:
                    if not el:
                        continue
                    if not el.is_displayed():
                        continue
                    aria_hidden = (el.get_attribute("aria-hidden") or "").lower()
                    if aria_hidden == "true":
                        continue
                    if el.get_attribute("disabled") is not None:
                        continue
                    return el
                except Exception:
                    continue
        time.sleep(0.25)
    raise TimeoutException(f"Could not find a visible element for any of: {selectors}")


def _safe_click(driver, element, *, allow_actions: bool = True) -> bool:
    """Attempt multiple headless-friendly click strategies."""
    if not element:
        return False
    try:
        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", element)
    except Exception:
        pass
    try:
        driver.execute_script("arguments[0].focus();", element)
    except Exception:
        pass

    attempts = [
        lambda: element.click(),
        lambda: driver.execute_script("arguments[0].click();", element),
    ]
    if allow_actions:
        attempts.append(lambda: ActionChains(driver).move_to_element(element).pause(0.05).click().perform())

    for attempt in attempts:
        try:
            attempt()
            return True
        except Exception:
            continue

    if allow_actions:
        try:
            ActionChains(driver).move_to_element(element).pause(0.05).send_keys(Keys.SPACE).perform()
            return True
        except Exception:
            pass

    try:
        element.send_keys(Keys.SPACE)
        return True
    except Exception:
        pass

    try:
        driver.execute_script(
            "const el = arguments[0];"
            "el.dispatchEvent(new MouseEvent('click', {bubbles:true, cancelable:true, view:window}));",
            element,
        )
        return True
    except Exception:
        pass

    return False

def _safe_click_check(driver, element, selector, *, allow_actions: bool = True) -> bool:
    """Attempt multiple headless-friendly click strategies."""
    if not element:
        return False
    try:
        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", element)
    except Exception:
        pass
    try:
        driver.execute_script("arguments[0].focus();", element)
    except Exception:
        pass

    attempts = [
        lambda: element.click(),
        lambda: driver.execute_script("arguments[0].click();", element),
    ]
    if allow_actions:
        attempts.append(lambda: ActionChains(driver).move_to_element(element).pause(0.05).click().perform())

    for attempt in attempts:
        try:
            attempt()
            if wait_for_selector(driver, selector, timeout=10):
                return True
        except Exception:
            continue

    if allow_actions:
        try:
            ActionChains(driver).move_to_element(element).pause(0.05).send_keys(Keys.SPACE).perform()
            if wait_for_selector(driver, selector, timeout=10):
                return True
        except Exception:
            pass

    try:
        element.send_keys(Keys.SPACE)
        if wait_for_selector(driver, selector, timeout=10):
            return True
    except Exception:
        pass

    try:
        driver.execute_script(
            "const el = arguments[0];"
            "el.dispatchEvent(new MouseEvent('click', {bubbles:true, cancelable:true, view:window}));",
            element,
        )
        print("execute_script")
        if wait_for_selector(driver, selector, timeout=10):
            return True
    except Exception:
        pass

    return False

def _safe_click_checkbox(driver, element, inp, should_check, *, allow_actions: bool = True) -> bool:
    """Attempt multiple headless-friendly click strategies."""
    if not element:
        return False
    try:
        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", element)
    except Exception:
        pass
    try:
        driver.execute_script("arguments[0].focus();", element)
    except Exception:
        pass

    attempts = [
        lambda: element.click(),
        lambda: driver.execute_script("arguments[0].click();", element),
    ]
    if allow_actions:
        attempts.append(lambda: ActionChains(driver).move_to_element(element).pause(0.05).click().perform())

    for attempt in attempts:
        try:
            attempt()
            if inp.is_selected() == should_check:
                return True
        except Exception:
            continue

    if allow_actions:
        try:
            ActionChains(driver).move_to_element(element).pause(0.05).send_keys(Keys.SPACE).perform()
            print("allow_actions")
            if inp.is_selected() == should_check:
                return True
        except Exception:
            pass

    try:
        element.send_keys(Keys.SPACE)
        print("send key")
        if inp.is_selected() == should_check:
            return True
    except Exception:
        pass

    try:
        driver.execute_script(
            "const el = arguments[0];"
            "el.dispatchEvent(new MouseEvent('click', {bubbles:true, cancelable:true, view:window}));",
            element,
        )
        if inp.is_selected() == should_check:
            return True
    except Exception:
        pass

    return False


def _set_input_value(driver, element, value: str) -> bool:
    """Set an input's value via the native setter and dispatch input/change events."""
    try:
        driver.execute_script(
            "const input = arguments[0];"
            "const newValue = arguments[1];"
            "const nativeInputValueSetter = Object.getOwnPropertyDescriptor(input.__proto__, 'value').set;"
            "nativeInputValueSetter.call(input, newValue);"
            "input.setAttribute('value', newValue);"
            "input.dispatchEvent(new Event('input', { bubbles: true }));"
            "input.dispatchEvent(new Event('change', { bubbles: true }));",
            element,
            value,
        )
        return True
    except Exception:
        return False


def _wait_until(predicate, timeout: float = 3.0, interval: float = 0.12) -> bool:
    """Poll `predicate` until it returns True or timeout elapses."""
    end = time.time() + timeout
    while time.time() < end:
        try:
            if predicate():
                return True
        except Exception:
            pass
        time.sleep(interval)
    try:
        return bool(predicate())
    except Exception:
        return False


def _xpath_literal(text: str) -> str:
    """Return an XPath literal representing `text`. Handles quotes safely."""
    if "'" not in text:
        return f"'{text}'"
    if '"' not in text:
        return f'"{text}"'
    parts = text.split("'")
    segments = []
    for i, part in enumerate(parts):
        if part:
            segments.append(f"'{part}'")
        if i != len(parts) - 1:
            segments.append("\"'\"")
    return "concat(" + ", ".join(segments) + ")"


def load_cookies(driver):
    logger.info("Checking Cookies")
    if COOKIES_JSON.exists():
        logger.info("Yes Cookies")
        try:
            with open(COOKIES_JSON, "r", encoding="utf-8") as f:
                cookies = json.load(f)
            for c in cookies:
                try:
                    driver.add_cookie(c)
                except Exception:
                    pass
            return True
        except Exception:
            return False
    logger.info("No Cookies")
    return False


def dump_cookies(driver):
    try:
        cookies = driver.get_cookies()
        with open(COOKIES_JSON, "w", encoding="utf-8") as f:
            json.dump(cookies, f, ensure_ascii=False, indent=2)
        return True
    except Exception:
        return False


def is_logged_in(driver) -> bool:
    try:
        if driver.find_elements(By.CSS_SELECTOR, "nav[class*='sidebar']"):
            return True
    except Exception:
        pass
    try:
        if driver.find_elements(By.CSS_SELECTOR, "img[alt*='avatar'], div[class*='avatar']"):
            return True
    except Exception:
        pass
    return False


def wait_for_login_or_manual(driver, total_wait=240):
    start = time.time()
    while time.time() - start < total_wait:
        if is_logged_in(driver):
            return True
        time.sleep(2)
    return False


def click_if_present(driver, selectors: List[str], timeout=3):
    try:
        el = _find_first_visible(driver, selectors, timeout)
    except Exception:
        return False

    if not _safe_click(driver, el):
        return False

    time.sleep(0.5)
    return True


def login_flow(driver, username: str, password: str) -> bool:
    print(f"[{__VERSION__}] Launching login...")
    logger.info("Launching login...")
    driver.get(LOGIN_URL)
    time.sleep(2)
    save_screenshot(driver, "login_flow")
    upload_screenshots()
    if load_cookies(driver):
        driver.refresh()
        time.sleep(2)
        if is_logged_in(driver):
            print("Loaded session cookies.")
            return True

    click_if_present(driver, [
        "button:has-text('Use phone / email / username')",
        "div[role='tab']:has-text('Email')",
        "div[role='tab']:has-text('Phone / Email')",
        "button:has-text('Email / Phone')",
    ], timeout=3)

    def fill(selector_list, value):
        for s in selector_list:
            try:
                el = _find_first_visible(driver, [s], timeout=3)
                try:
                    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
                except Exception:
                    pass
                try:
                    driver.execute_script("arguments[0].focus();", el)
                except Exception:
                    pass
                try:
                    el.clear()
                except Exception:
                    pass
                el.send_keys(value)
                return True
            except Exception:
                continue
        return False

    fill(["input[name='email']", "input[autocomplete='username']", "input[placeholder*='email']"], username)
    fill(["input[name='password']", "input[type='password']", "input[placeholder*='password']"], password)

    click_if_present(driver, ["button[type='submit']", "button:has-text('Log in')", "button:has-text('Sign in')"], timeout=5)

    if wait_for_login_or_manual(driver, total_wait=240):
        dump_cookies(driver)
        return True

    save_screenshot(driver, "login_failure")
    return False


# --------------------- Navigation to Orders ---------------------

def open_orders_menu_and_click_manage(driver) -> bool:
    """Expand left 'Orders' menu and click 'Manage orders'."""
    try:
        hdr = _find_first_visible(driver, sel.ORDERS_MENU_HEADER, timeout=8)
    except Exception:
        return False

    try:
        expanded = (hdr.get_attribute("aria-expanded") or "").lower() == "true"
    except Exception:
        expanded = False
    if not expanded:
        if not _safe_click(driver, hdr):
            return False
        time.sleep(0.4)

    try:
        lnk = _find_first_visible(driver, sel.ORDERS_MANAGE_LINK, timeout=8)
        if not _safe_click(driver, lnk):
            return False
        time.sleep(1.0)
        return True
    except Exception:
        return False


def navigate_to_orders(driver) -> bool:
    # 1) Left menu: Orders -> Manage orders
    if open_orders_menu_and_click_manage(driver):
        time.sleep(1)
        return True

    # 2) Any visible Orders link
    if click_if_present(driver, sel.ORDERS_NAV_LINK, timeout=4):
        time.sleep(1)
        return True

    # 3) Fallback: direct path
    origin = base_origin()
    for path in ORDERS_PATHS:
        try:
            driver.get(origin + path)
            time.sleep(1)
            return True
        except Exception:
            continue
    return False


# --------------------- Filter Drawer ---------------------

def wait_for_drawer(driver, timeout=10) -> bool:
    try:
        _find_first_visible(driver, sel.DRAWER, timeout)
        return True
    except Exception:
        return False
    
def wait_for_selector(driver, selector, timeout=10) -> bool:
    try:
        _find_first_visible(driver, selector, timeout)
        return True
    except Exception:
        return False


def open_filter_drawer(driver) -> bool:
    """Open the filter drawer using JS-friendly clicks (headless-safe) and wait for it to appear."""
    try:
        btn = _find_first_visible(driver, sel.FILTER_TOGGLE, timeout=6)
    except Exception as e:
        return False
    if not _safe_click_check(driver, btn, sel.DRAWER):
        return False
    time.sleep(0.2)
    return wait_for_drawer(driver, timeout=10)



















def pick_from_select_by_placeholder(driver, placeholder: str, option_text: str) -> bool:
    """Open the combobox by placeholder and select option_text."""
    option_text = (option_text or "").strip()
    if not option_text:
        return False
    option_lower = option_text.lower()

    combo_xpath = f"//div[@role='combobox' and .//input[@placeholder='{placeholder}']]"
    try:
        combo = _find_first_visible(driver, [combo_xpath], timeout=8)
    except Exception:
        return False

    def selection_confirmed() -> bool:
        try:
            view_value = combo.find_element(By.XPATH, ".//*[contains(@class,'core-select-view-value')]")
            text = (view_value.text or '').strip().lower()
            if text and option_lower in text:
                return True
        except Exception:
            pass
        try:
            summary = ((combo.text or '') + ' ' + (combo.get_attribute('innerText') or '')).lower()
            if option_lower in summary:
                return True
        except Exception:
            pass
        try:
            chips = combo.find_elements(By.XPATH, ".//*[contains(@class,'tag') or contains(@class,'selected') or @data-selected='true']")
            for chip in chips:
                try:
                    txt = (chip.text or '').strip().lower()
                    if option_lower in txt:
                        return True
                except Exception:
                    continue
        except Exception:
            pass
        return False

    portal_xpath = "//div[contains(@class,'core-select-popup') or contains(@class,'pulse-select-popup')][@data-tid='m4b_select']"

    def dropdown_open() -> bool:
        try:
            if (combo.get_attribute('aria-expanded') or '').lower() == 'true':
                return True
        except Exception:
            pass
        try:
            for portal in driver.find_elements(By.XPATH, portal_xpath):
                try:
                    if portal.is_displayed():
                        return True
                except Exception:
                    continue
        except Exception:
            pass
        return False

    def ensure_dropdown_open() -> bool:
        targets = [combo]
        for xpath in (
            ".//*[contains(@class,'core-select-suffix') or contains(@class,'core-select-arrow-icon')]",
            ".//span[contains(@class,'core-select-view-selector')]"):
            try:
                target = combo.find_element(By.XPATH, xpath)
                if target:
                    targets.append(target)
            except Exception:
                continue
        try:
            parent = combo.find_element(By.XPATH, "./ancestor::div[@data-log_click_for='filter_select'][1]")
            if parent:
                targets.append(parent)
        except Exception:
            pass
        for _ in range(6):
            if dropdown_open():
                return True
            for tgt in targets:
                try:
                    _safe_click(driver, tgt, allow_actions=False)
                except Exception:
                    continue
                if dropdown_open():
                    return True
            try:
                driver.execute_script(
                    "arguments[0].dispatchEvent(new MouseEvent('mousedown', {bubbles:true,cancelable:true}));"
                    "arguments[0].dispatchEvent(new MouseEvent('mouseup', {bubbles:true,cancelable:true}));"
                    "arguments[0].dispatchEvent(new MouseEvent('click', {bubbles:true,cancelable:true}));",
                    combo,
                )
            except Exception:
                pass
            if dropdown_open():
                return True
            for key in (Keys.SPACE, Keys.ENTER, Keys.ARROW_DOWN):
                try:
                    combo.send_keys(key)
                except Exception:
                    continue
                if dropdown_open():
                    return True
            time.sleep(0.1)
        return dropdown_open()

    if not ensure_dropdown_open():
        return False

    js_select = """
const placeholder = arguments[0];
const optionLower = arguments[1];
function visible(el){
  if (!el) return false;
  const style = window.getComputedStyle(el);
  if (!style || style.display === 'none' || style.visibility === 'hidden') return false;
  const rect = el.getBoundingClientRect();
  return rect.width > 0 && rect.height > 0;
}
const combos = Array.from(document.querySelectorAll('div[role="combobox"]'));
const combo = combos.find(c => c.querySelector(`input[placeholder="${placeholder}"]`));
if (!combo) return false;
combo.scrollIntoView({block:'center'});
const selector = combo.querySelector('.core-select-view-selector') || combo;
['mousedown','mouseup','click'].forEach(evt => selector.dispatchEvent(new MouseEvent(evt, {bubbles:true,cancelable:true})));
const portals = Array.from(document.querySelectorAll('.core-select-popup[data-tid="m4b_select"], .pulse-select-popup[data-tid="m4b_select"]'));
let options = [];
if (portals.length){
  portals.forEach(p => options.push(...Array.from(p.querySelectorAll('[role="option"], li[role="option"]'))));
}
if (!options.length){
  options = Array.from(combo.querySelectorAll('[role="option"], li[role="option"]'));
}
const candidate = options.find(opt => {
  if (!visible(opt)) return false;
  const t = (opt.innerText || '').trim().toLowerCase();
  return t && (t === optionLower || t.includes(optionLower));
});
if (!candidate) return false;
const label = candidate.querySelector('label');
const radio = candidate.querySelector('input[type="radio"]');
const target = label || radio || candidate;
['mouseenter','mouseover','mousedown','mouseup','click'].forEach(evt => target.dispatchEvent(new MouseEvent(evt, {bubbles:true,cancelable:true})));
if (radio){
  radio.checked = true;
  radio.dispatchEvent(new Event('input', {bubbles:true}));
  radio.dispatchEvent(new Event('change', {bubbles:true}));
}
return true;
"""

    used_js = False
    try:
        used_js = driver.execute_script(js_select, placeholder, option_lower)
    except Exception:
        used_js = False
    if used_js:
        time.sleep(0.2)
        if selection_confirmed():
            return True

    # JS failed; fallback to Selenium search
    option = None
    try:
        portals = driver.find_elements(By.XPATH, portal_xpath)
    except Exception:
        portals = []
    search_roots = [p for p in portals if p and p.is_displayed()] or [combo]

    for root in search_roots:
        try:
            options = root.find_elements(By.XPATH, ".//*[@role='option']")
        except Exception:
            options = []
        for opt in options:
            try:
                text = (opt.text or '').strip().lower()
                if not text:
                    text = (opt.get_attribute('innerText') or '').strip().lower()
            except Exception:
                text = ''
            if text and (text == option_lower or option_lower in text):
                option = opt
                break
        if option:
            break

    if not option:
        return False

    click_targets = []
    try:
        label = option.find_element(By.XPATH, ".//label")
        click_targets.append(label)
    except Exception:
        pass
    try:
        radio = option.find_element(By.XPATH, ".//input[@type='radio']")
    except Exception:
        radio = None
    if radio:
        click_targets.append(radio)
    click_targets.append(option)

    clicked = False
    for target in click_targets:
        try:
            if _safe_click(driver, target, allow_actions=False):
                clicked = True
                break
        except Exception:
            try:
                driver.execute_script("arguments[0].click();", target)
                clicked = True
                break
            except Exception:
                continue
    if not clicked and radio:
        try:
            driver.execute_script(
                "arguments[0].checked = true;"
                "arguments[0].dispatchEvent(new Event('input', {bubbles:true}));"
                "arguments[0].dispatchEvent(new Event('change', {bubbles:true}));",
                radio,
            )
            clicked = True
        except Exception:
            pass
    if not clicked:
        return False

    time.sleep(0.2)

    if selection_confirmed():
        return True

    try:
        combo.send_keys(Keys.TAB)
        time.sleep(0.1)
    except Exception:
        pass
    return selection_confirmed()


def focus_customer_username_input(driver) -> bool:
    selectors = [
        "//input[@placeholder='Customer username']",
        "//span[contains(@class,'core-input-group-prefix') and normalize-space()='Customer username']/following::input[1]",
        "input[data-tid='m4b_input'][placeholder='Customer username']",
    ]
    try:
        inp = _find_first_visible(driver, selectors, timeout=6)
    except Exception:
        return False
    return _safe_click(driver, inp, allow_actions=False)


def set_product_in_drawer(driver, product: str) -> bool:
    """Enter the product value, pick a suggestion if available, and ensure it persists."""
    product = (product or "").strip()
    if not product:
        return False
    target_lower = product.lower()

    input_selectors = [
        "//span[normalize-space()='Product']/following::input[contains(@class,'core-input')][1]",
        "//input[@data-tid='m4b_input' and contains(@placeholder,'product')]",
        "//input[contains(@placeholder,'product name') or contains(@placeholder,'seller SKU') or contains(@placeholder,'SKU ID')]",
    ]

    option_selectors = [
        "//*[@role='option' and normalize-space()='{text}']",
        "//*[@role='option' and contains(translate(normalize-space(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'), '{lower}')]",
        "//div[contains(@class,'option')][normalize-space()='{text}']",
        "//*[contains(@class,'option')]//*[normalize-space()='{text}']",
        "//*[contains(@class,'option')]//*[contains(translate(normalize-space(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'), '{lower}')]",
        "//li[normalize-space()='{text}']",
        "//li[contains(translate(normalize-space(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'), '{lower}')]",
    ]

    def locate_input(timeout=6.0):
        try:
            return _find_first_visible(driver, input_selectors, timeout)
        except Exception:
            return None

    def field_has_value() -> bool:
        current = locate_input(timeout=1.0)
        if current:
            try:
                val = (current.get_attribute('value') or '').strip().lower()
                if val and target_lower in val:
                    return True
            except Exception:
                pass
            try:
                container = current.find_element(
                    By.XPATH,
                    "./ancestor::*[contains(@class,'form-item') or contains(@class,'combobox') or contains(@class,'select')][1]",
                )
            except Exception:
                container = None
            if container:
                try:
                    chips = container.find_elements(
                        By.XPATH,
                        ".//*[not(self::input)][contains(@class,'tag') or contains(@class,'selected') or @data-selected='true']",
                    )
                except Exception:
                    chips = []
                for chip in chips:
                    try:
                        if target_lower in (chip.text or '').strip().lower():
                            return True
                    except Exception:
                        continue
        return False

    def focus_and_type(inp_el) -> bool:
        try:
            driver.execute_script(
                "arguments[0].scrollIntoView({block:'center'}); arguments[0].focus();",
                inp_el,
            )
        except Exception:
            pass
        for combo in ((Keys.CONTROL, 'a'), (Keys.COMMAND, 'a')):
            try:
                inp_el.send_keys(*combo)
                inp_el.send_keys(Keys.BACK_SPACE)
            except Exception:
                continue
        try:
            inp_el.clear(); time.sleep(0.05)
        except Exception:
            pass
        _set_input_value(driver, inp_el, '')
        typed = False
        try:
            inp_el.send_keys(product)
            typed = True
        except Exception:
            pass
        if _set_input_value(driver, inp_el, product):
            typed = True
        return typed

    def click_suggestion() -> bool:
        for patt in option_selectors:
            sel = patt.replace('{text}', product).replace('{lower}', target_lower)
            try:
                suggestion = _find_first_visible(driver, [sel], timeout=0.8)
                if suggestion and _safe_click(driver, suggestion, allow_actions=False):
                    time.sleep(0.1)
                    return True
            except Exception:
                continue
        return False

    for _ in range(3):
        inp = locate_input(timeout=6.0)
        if not inp:
            return False
        if not focus_and_type(inp):
            continue
        time.sleep(0.15)

        if not click_suggestion():
            try:
                inp.send_keys(Keys.ENTER)
                time.sleep(0.1)
            except Exception:
                try:
                    driver.execute_script(
                        "arguments[0].dispatchEvent(new KeyboardEvent('keydown', {key:'Enter', keyCode:13, which:13, bubbles:true}));"
                        "arguments[0].dispatchEvent(new KeyboardEvent('keyup', {key:'Enter', keyCode:13, which:13, bubbles:true}));",
                        inp,
                    )
                except Exception:
                    pass

        if not _wait_until(field_has_value, timeout=1.8):
            inp = locate_input(timeout=1.0) or inp
            _set_input_value(driver, inp, product)
            if not _wait_until(field_has_value, timeout=1.0):
                continue

        inp = locate_input(timeout=1.0) or inp
        try:
            ActionChains(driver).move_to_element(inp).pause(0.05).send_keys(Keys.TAB).perform()
        except Exception:
            try:
                driver.execute_script("arguments[0].blur && arguments[0].blur();", inp)
            except Exception:
                pass

        if _wait_until(field_has_value, timeout=1.2):
            return True

    return False


def wait_for_drawer_closed(driver, timeout=10) -> bool:
    end = time.time() + timeout
    while time.time() < end:
        # If drawer cannot be found, consider it closed
        try:
            _find_first_visible(driver, sel.DRAWER, timeout=1)
            time.sleep(0.2)
        except Exception:
            return True
    return False


def click_drawer_apply(driver) -> bool:
    """Click the drawer Apply button and wait for the drawer to dismiss."""
    try:
        btn = _find_first_visible(driver, sel.DRAWER_APPLY, timeout=10)
    except Exception:
        return False

    clicked = False
    attempts = (
        lambda b: _safe_click(driver, b, allow_actions=False),
        lambda b: driver.execute_script(
            "arguments[0].dispatchEvent(new MouseEvent('mousedown', {bubbles:true,cancelable:true}));"
            "arguments[0].dispatchEvent(new MouseEvent('mouseup', {bubbles:true,cancelable:true}));"
            "arguments[0].dispatchEvent(new MouseEvent('click', {bubbles:true,cancelable:true}));",
            b,
        ),
        lambda b: ActionChains(driver).move_to_element(b).pause(0.05).click().perform(),
        lambda b: driver.execute_script("arguments[0].click();", b),
    )

    for attempt in attempts:
        try:
            attempt(btn)
            clicked = True
            break
        except Exception:
            try:
                btn = _find_first_visible(driver, sel.DRAWER_APPLY, timeout=2)
            except Exception:
                return False
            continue

    if not clicked:
        try:
            btn.send_keys(Keys.ENTER)
            clicked = True
        except Exception:
            return False

    time.sleep(0.18)

    if not wait_for_drawer_closed(driver, timeout=12):
        for flick in (0, 1):
            try:
                driver.execute_script("arguments[0].dispatchEvent(new MouseEvent('click', {bubbles:true,cancelable:true}));", btn)
            except Exception:
                pass
            if wait_for_drawer_closed(driver, timeout=4):
                break
        else:
            return False

    wait_for_orders_populated(driver, timeout=15)
    return True


# --------------------- Orders table readiness ---------------------

def any_displayed(driver, selectors: List[str]) -> bool:
    for s in selectors:
        try:
            if s.startswith('//'):
                els = driver.find_elements(By.XPATH, s)
            else:
                els = driver.find_elements(By.CSS_SELECTOR, s)
            for el in els:
                try:
                    if el.is_displayed():
                        return True
                except Exception:
                    continue
        except Exception:
            continue
    return False


def count_elements(driver, selectors: List[str]) -> int:
    total = 0
    for s in selectors:
        try:
            if s.startswith('//'):
                total += len(driver.find_elements(By.XPATH, s))
            else:
                total += len(driver.find_elements(By.CSS_SELECTOR, s))
        except Exception:
            continue
    return total


def wait_for_orders_populated(driver, timeout: int = 15) -> bool:
    end = time.time() + timeout
    last_count = -1
    stable_ticks = 0
    while time.time() < end:
        if any_displayed(driver, sel.LOADING):
            time.sleep(0.1)
            continue

        count = count_elements(driver, sel.ROW_CHECKBOXES) or count_elements(driver, sel.TABLE_ROWS)
        if count > 0:
            if count == last_count:
                stable_ticks += 1
            else:
                stable_ticks = 0
                last_count = count
            if stable_ticks >= 4:
                return True
        time.sleep(0.1)
    return False


# --------------------- Bulk selection (orders) ---------------------

def _get_aria_checked(el) -> Optional[str]:
    try:
        return el.get_attribute("aria-checked")
    except Exception:
        return None


def ensure_header_select_all(driver) -> bool:
    try:
        el = _find_first_visible(driver, sel.SELECT_ALL_HEADER, timeout=10)
    except Exception:
        return False
    
    try:
        inp = el.find_element(By.CSS_SELECTOR, "input[type='checkbox']")
    except Exception:
        return False

    try:
        box = el
        if el.get_attribute("role") != "checkbox":
            try:
                box = el.find_element(By.XPATH, "./ancestor-or-self::*[@role='checkbox'][1]")
            except Exception:
                box = el
        state = _get_aria_checked(box)
        cls = (box.get_attribute("class") or "")
        checked = (state and state.lower() == "true") or ("checked" in cls)
        print("ensure_header_select_all:" +str(checked))
        if not checked:
            if _safe_click_checkbox(driver, el, inp, True):
                return True
            time.sleep(0.5)
        return True
    except Exception:
        if _safe_click_checkbox(driver, el, inp, True):
            time.sleep(0.5)
            return True
        return False
    
def ensure_order_header_select_all(driver) -> bool:
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC

    try:
        hdr = _find_first_visible(driver, sel.SELECT_ALL_HEADER, timeout=12)
    except Exception:
        return False

    def header_is_checked():
        cls = (hdr.get_attribute("class") or "").lower()
        return "checked" in cls

    attempts = [hdr]
    try:
        mask = hdr.find_element(By.CSS_SELECTOR, ".core-checkbox-mask-wrapper")
        attempts.append(mask)
    except Exception:
        pass
    try:
        inp = hdr.find_element(By.CSS_SELECTOR, "input[type='checkbox']")
        attempts.append(inp)
    except Exception:
        pass

    try:
        driver.execute_script("arguments[0].style.zIndex='2147483647';", hdr)
    except Exception:
        pass

    def verified():
        if header_is_checked():
            return True
        if count_ship_selected_rows(driver) > 0:
            return True
        try:
            _find_first_visible(driver, sel.SHIP_BULK_SELECT_ALL, timeout=1)
            return True
        except Exception:
            return False

    for el in attempts:
        try:
            WebDriverWait(driver, 6).until(EC.element_to_be_clickable((By.XPATH, "//label[@data-id='fulfillment.table.select_current_package']")))
        except Exception:
            pass

        if not _safe_click(driver, el):
            continue

        end = time.time() + 3
        while time.time() < end:
            if verified():
                return True
            time.sleep(0.15)

    try:
        driver.execute_script(
            "const el = arguments[0];"
            "const evt = new MouseEvent('click', {bubbles:true, cancelable:true, view:window});"
            "el.dispatchEvent(evt);",
            hdr
        )
        time.sleep(0.4)
        if verified():
            return True
    except Exception:
        pass

    return False



def _bulk_reset_visible(driver, timeout: float = 0.3) -> bool:
    """Return True if the bulk 'Reset' button is visible."""
    try:
        _find_first_visible(driver, sel.BULK_RESET_BUTTON, timeout=timeout)
        return True
    except Exception:
        return False


def _wait_for_bulk_reset(driver, timeout: float = 3.0) -> bool:
    """Wait until the bulk selection banner changes to the Reset state."""
    end = time.time() + timeout
    while time.time() < end:
        if _bulk_reset_visible(driver, timeout=0.2):
            return True
        time.sleep(0.1)
    return False


def _ship_bulk_reset_visible(driver, timeout: float = 0.3) -> bool:
    selectors = list(sel.BULK_RESET_BUTTON)
    extra = getattr(sel, "SHIP_BULK_RESET_BUTTON", None)
    if extra:
        selectors = list(dict.fromkeys(list(extra) + selectors))
    try:
        _find_first_visible(driver, selectors, timeout=timeout)
        return True
    except Exception:
        return False


def _wait_for_ship_bulk_reset(driver, timeout: float = 3.0) -> bool:
    end = time.time() + timeout
    while time.time() < end:
        if _ship_bulk_reset_visible(driver, timeout=0.2):
            return True
        time.sleep(0.1)
    return False


def maybe_click_bulk_select_all(driver) -> bool:
    """Click the orders bulk-select button."""
    selectors = sel.BULK_SELECT_ALL_BUTTON

    def locate(timeout=6):
        deadline = time.time() + timeout
        while time.time() < deadline:
            for selector in selectors:
                try:
                    return _find_first_visible(driver, [selector], timeout=0.5)
                except Exception:
                    continue
            if _bulk_reset_visible(driver, timeout=0.2):
                return None
            time.sleep(0.1)
        raise TimeoutException(f"Bulk select button not found via {selectors}")

    if _bulk_reset_visible(driver):
        return True

    click_strategies = [
        lambda element: _safe_click(driver, element, allow_actions=True),
        lambda element: driver.execute_script(
            "['mousedown','mouseup','click'].forEach(type => arguments[0].dispatchEvent(new MouseEvent(type, {bubbles:true,cancelable:true})));",
            element,
        ) or True,
        lambda element: driver.execute_script("arguments[0].click();", element) or True,
        lambda element: ActionChains(driver).move_to_element(element).pause(0.05).click().perform() or True,
        lambda element: element.send_keys(Keys.ENTER) or True,
        lambda element: element.send_keys(Keys.SPACE) or True,
    ]

    for attempt_index in range(3):
        try:
            btn = locate(timeout=6 if attempt_index == 0 else 3)
        except Exception:
            if _bulk_reset_visible(driver):
                return True
            time.sleep(0.2)
            continue

        if btn is None:
            return True

        try:
            driver.execute_script("arguments[0].scrollIntoView({block:'center'}); arguments[0].focus();", btn)
        except Exception:
            pass

        stale_reference = False
        for click_fn in click_strategies:
            try:
                if click_fn(btn):
                    time.sleep(0.2)
                    if _wait_for_bulk_reset(driver):
                        return True
            except StaleElementReferenceException:
                stale_reference = True
                break
            except Exception:
                continue

        if _bulk_reset_visible(driver):
            return True

        if stale_reference:
            time.sleep(0.2)
            continue

        time.sleep(0.2)

    return _wait_for_bulk_reset(driver)

def maybe_click_bulk_select_all_ship(driver) -> bool:
    """Click the orders bulk-select button."""
    selectors = sel.SHIP_BULK_SELECT_ALL

    def locate(timeout=6):
        deadline = time.time() + timeout
        while time.time() < deadline:
            for selector in selectors:
                try:
                    return _find_first_visible(driver, [selector], timeout=0.5)
                except Exception:
                    continue
            if _bulk_reset_visible(driver, timeout=0.2):
                return None
            time.sleep(0.1)
        raise TimeoutException(f"Bulk select button not found via {selectors}")

    if _bulk_reset_visible(driver):
        return True

    click_strategies = [
        lambda element: _safe_click(driver, element, allow_actions=True),
        lambda element: driver.execute_script(
            "['mousedown','mouseup','click'].forEach(type => arguments[0].dispatchEvent(new MouseEvent(type, {bubbles:true,cancelable:true})));",
            element,
        ) or True,
        lambda element: driver.execute_script("arguments[0].click();", element) or True,
        lambda element: ActionChains(driver).move_to_element(element).pause(0.05).click().perform() or True,
        lambda element: element.send_keys(Keys.ENTER) or True,
        lambda element: element.send_keys(Keys.SPACE) or True,
    ]

    for attempt_index in range(3):
        try:
            btn = locate(timeout=6 if attempt_index == 0 else 3)
        except Exception:
            if _bulk_reset_visible(driver):
                return True
            time.sleep(0.2)
            continue

        if btn is None:
            return True

        try:
            driver.execute_script("arguments[0].scrollIntoView({block:'center'}); arguments[0].focus();", btn)
        except Exception:
            pass

        stale_reference = False
        for click_fn in click_strategies:
            try:
                if click_fn(btn):
                    time.sleep(0.2)
                    if _wait_for_bulk_reset(driver):
                        return True
            except StaleElementReferenceException:
                stale_reference = True
                break
            except Exception:
                continue

        if _bulk_reset_visible(driver):
            return True

        if stale_reference:
            time.sleep(0.2)
            continue

        time.sleep(0.2)

    return _wait_for_bulk_reset(driver)
def click_arrange_shipment(driver) -> bool:
    """Click Arrange shipment and confirm we actually reach shipping/combine."""
    selectors = sel.ARRANGE_SHIPMENT_BUTTON
    overlay_selectors = [
        "div.flex.w-full.h-full.items-center.justify-center.fixed.top-0.left-0",
        ".theme-arco-modal-mask",
        ".arco-modal-mask",
        "[data-tid='m4b_modal_mask']",
    ]
    deadline = time.time() + 18
    initial_url = driver.current_url

    def masks():
        found = []
        for css in overlay_selectors:
            try:
                found.extend(driver.find_elements(By.CSS_SELECTOR, css))
            except Exception:
                continue
        print("0")
        return found

    def neutralize_masks(timeout: float = 3.0) -> None:
        end = time.time() + timeout
        while time.time() < end:
            active = False
            for overlay in masks():
                try:
                    if overlay.is_displayed():
                        active = True
                        driver.execute_script(
                            "arguments[0].style.pointerEvents='none'; arguments[0].style.opacity='0'; arguments[0].style.display='none'; arguments[0].removeAttribute('style');",
                            overlay,
                        )
                        try:
                            driver.execute_script("arguments[0].remove();", overlay)
                        except Exception:
                            pass
                except Exception:
                    continue
            if not active:
                return
            try:
                driver.find_element(By.TAG_NAME, "body").send_keys(Keys.ESCAPE)
            except Exception:
                pass
            try:
                driver.execute_script(
                    "document.dispatchEvent(new KeyboardEvent('keydown', {key:'Escape', bubbles:true}));"
                )
            except Exception:
                pass
            time.sleep(0.2)

    def manage_button_visible(timeout: float = 0.6) -> bool:
        try:
            _find_first_visible(driver, selectors, timeout=timeout)
            return True
        except Exception:
            return False

    def manage_button_gone(timeout: float = 2.0) -> bool:
        return _wait_until(lambda: not manage_button_visible(timeout=0.2), timeout=timeout, interval=0.2)

    def combine_modal_visible(timeout: float = 0.6) -> bool:
        try:
            _find_first_visible(driver, sel.COMBINE_CONFIRM_BUTTON, timeout=timeout)
            return True
        except Exception:
            return False

    def transitioned() -> bool:
        if combine_modal_visible(timeout=0.5):
            return True
        if manage_button_gone(timeout=2.0):
            try:
                _find_first_visible(driver, sel.BACK_TO_MANAGE_ORDERS, timeout=0.6)
                return True
            except Exception:
                pass
            try:
                current = driver.current_url
            except Exception:
                current = None
            if current and initial_url and current != initial_url:
                return True
        return False

    neutralize_masks()
    if transitioned():
        return True

    while time.time() < deadline:
        try:
            btn = _find_first_visible(driver, selectors, timeout=3)
        except Exception:
            if transitioned():
                return True
            neutralize_masks(timeout=1.0)
            time.sleep(0.4)
            continue

        try:
            driver.execute_script("arguments[0].scrollIntoView({block:'center'});", btn)
        except Exception:
            pass
        try:
            driver.execute_script("arguments[0].focus();", btn)
        except Exception:
            pass

        try:
            if hasattr(btn, 'is_enabled') and not btn.is_enabled():
                time.sleep(0.3)
                neutralize_masks(timeout=0.6)
                continue
        except Exception:
            pass
        try:
            aria_disabled = (btn.get_attribute('aria-disabled') or '').lower()
            if aria_disabled == 'true':
                time.sleep(0.3)
                neutralize_masks(timeout=0.6)
                continue
        except Exception:
            pass

        click_strategies = [
            lambda element: ActionChains(driver).move_to_element(element).pause(0.05).click().perform() or True,
            lambda element: ActionChains(driver).move_to_element_with_offset(element, element.size.get('width', 40) / 2, element.size.get('height', 20) / 2).click().perform() or True,
            lambda element: ActionChains(driver).move_to_element(element).click_and_hold().pause(0.05).release().perform() or True,
            lambda element: _safe_click(driver, element, allow_actions=True),
            lambda element: driver.execute_script("['pointerdown','mousedown','mouseup','click'].forEach(type => arguments[0].dispatchEvent(new MouseEvent(type, {bubbles:true,cancelable:true})));", element) or True,
            lambda element: driver.execute_script("(el => { el.click(); const span = el.querySelector('span'); if (span) span.click(); })(arguments[0]);", element) or True,
            lambda element: element.click() or True,
        ]

        masked = False
        for fn in click_strategies:
            try:
                if fn(btn):
                    if transitioned():
                        return True
                    time.sleep(0.4)
            except WebDriverException as e:
                if "Other element would receive the click" in str(e):
                    masked = True
                    break
            except StaleElementReferenceException:
                return True
            except Exception:
                continue

        if transitioned():
            return True

        if masked:
            neutralize_masks(timeout=2.0)
            time.sleep(0.3)
            continue

        neutralize_masks(timeout=1.0)
        time.sleep(0.4)

    return transitioned()


def click_arrange_shipment_all(driver) -> bool:
    """Click Arrange shipment and confirm we actually reach shipping/combine."""
    selectors = sel.ARRANGE_PRINT_BUTTON

    deadline = time.time() + 18

    def manage_button_visible(timeout: float = 0.6) -> bool:
        try:
            _find_first_visible(driver, selectors, timeout=timeout)
            return True
        except Exception:
            return False

    def manage_button_gone(timeout: float = 2.0) -> bool:
        return _wait_until(lambda: not manage_button_visible(timeout=0.2), timeout=timeout, interval=0.2)

    def combine_modal_visible(timeout: float = 0.6) -> bool:
        try:
            _find_first_visible(driver, sel.COMBINE_CONFIRM_BUTTON, timeout=timeout)
            return True
        except Exception:
            return False

    def transitioned() -> bool:
        if combine_modal_visible(timeout=0.5):
            return True
        if manage_button_gone(timeout=2.0):
            try:
                _find_first_visible(driver, sel.BACK_TO_MANAGE_ORDERS, timeout=0.6)
                return True
            except Exception:
                pass
            try:
                current = driver.current_url
            except Exception:
                current = None
        return False

    while time.time() < deadline:
        try:
            btn = _find_first_visible(driver, selectors, timeout=3)
        except Exception:
            if transitioned():
                return True
            time.sleep(0.4)
            continue

        try:
            driver.execute_script("arguments[0].scrollIntoView({block:'center'});", btn)
        except Exception:
            pass
        try:
            driver.execute_script("arguments[0].focus();", btn)
        except Exception:
            pass

        try:
            if hasattr(btn, 'is_enabled') and not btn.is_enabled():
                time.sleep(0.3)
                continue
        except Exception:
            pass
        try:
            aria_disabled = (btn.get_attribute('aria-disabled') or '').lower()
            if aria_disabled == 'true':
                time.sleep(0.3)
                continue
        except Exception:
            pass

        click_strategies = [
            lambda element: ActionChains(driver).move_to_element(element).pause(0.05).click().perform() or True,
            lambda element: ActionChains(driver).move_to_element_with_offset(element, element.size.get('width', 40) / 2, element.size.get('height', 20) / 2).click().perform() or True,
            lambda element: ActionChains(driver).move_to_element(element).click_and_hold().pause(0.05).release().perform() or True,
            lambda element: _safe_click(driver, element, allow_actions=True),
            lambda element: driver.execute_script("['pointerdown','mousedown','mouseup','click'].forEach(type => arguments[0].dispatchEvent(new MouseEvent(type, {bubbles:true,cancelable:true})));", element) or True,
            lambda element: driver.execute_script("(el => { el.click(); const span = el.querySelector('span'); if (span) span.click(); })(arguments[0]);", element) or True,
            lambda element: element.click() or True,
        ]

        masked = False
        for fn in click_strategies:
            try:
                if fn(btn):
                    if transitioned():
                        return True
                    time.sleep(0.4)
            except WebDriverException as e:
                if "Other element would receive the click" in str(e):
                    masked = True
                    break
            except StaleElementReferenceException:
                return True
            except Exception:
                continue

        if transitioned():
            return True

        if masked:
            time.sleep(0.3)
            continue

        time.sleep(0.4)
    return False
# --------------------- Shipping page readiness and actions ---------------------

def wait_for_shipping_page_ready(driver, timeout: int = 60) -> bool:
    end = time.time() + timeout
    last_rows = -1
    stable_ticks = 0
    while time.time() < end:
        if any_displayed(driver, sel.SHIP_LOADING):
            time.sleep(0.5)
            continue
        try:
            _find_first_visible(driver, sel.SHIP_SELECT_ALL_LABEL, timeout=1)
            return True
        except Exception:
            pass
        try:
            _find_first_visible(driver, sel.ARRANGE_PRINT_BUTTON, timeout=1)
            return True
        except Exception:
            pass
        rows = count_elements(driver, sel.SHIP_TABLE_ROWS)
        if rows > 0:
            if rows == last_rows:
                stable_ticks += 1
            else:
                stable_ticks = 0
                last_rows = rows
            if stable_ticks >= 4:
                return True
        time.sleep(0.5)
    return False

# --------------------- Orders pagination ---------------------
def set_orders_pagination(driver, page_size: int = 50, timeout_open: int = 8) -> bool:
    """Attempt to change the orders table page size to `page_size`.
    Uses broad selectors for Arco/pulse pagination size changer and falls back to text matching
    like '50 / page' or '50 per page'. Returns True if an option is selected or already set.
    """
    try:
        # Ensure table is present to anchor pagination
        wait_for_orders_populated(driver, timeout=10)
    except Exception:
        pass

    # 1) Find a pagination size changer and open it
    size_toggle = None
    try:
        size_toggle = _find_first_visible(driver, sel.PAGINATION_SIZE_CHANGER, timeout=timeout_open)
    except Exception:
        # Try finding pagination container and then a child select
        try:
            pg = _find_first_visible(driver, sel.PAGINATION_CONTAINER, timeout=timeout_open)
            cand = None
            for xp in [".//*[@role='combobox']",
                       ".//*[contains(@class,'select')]",
                       ".//*[contains(@class,'size-changer')]"]:
                els = pg.find_elements(By.XPATH, xp)
                if els:
                    cand = els[0]; break
            size_toggle = cand
        except Exception:
            size_toggle = None

    if not size_toggle:
        return False

    if not _safe_click(driver, size_toggle):
        return False
    time.sleep(0.3)

    # 2) Choose option by exact/loose patterns
    target = str(page_size)
    option_selectors = [
        f"//li[@role='option' and (normalize-space()='{target}' or contains(normalize-space(), '{target}'))]",
        f"//div[contains(@class,'option')][normalize-space()='{target}']",
        f"//div[contains(@class,'option')]//*[normalize-space()='{target}']",
        f"//*[contains(@class,'option') and contains(normalize-space(), '{target}') and (contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'per page') or contains(., '/') or contains(., 'page'))]",
        # Very broad fallback: any element in an options popup containing the number
        f"//*[contains(translate(@class,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'popup') or contains(translate(@class,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'select')]//*[contains(normalize-space(), '{target}')]",
    ]
    chosen = None
    for sel_xpath in option_selectors:
        try:
            chosen = _find_first_visible(driver, [sel_xpath], timeout=4)
            if chosen:
                break
        except Exception:
            continue
    if not chosen:
        return False

    if not _safe_click(driver, chosen):
        return False

    # 3) Wait for table to repopulate and stabilize
    wait_for_orders_populated(driver, timeout=10)
    return True

def count_ship_selected_rows(driver) -> int:
    return count_elements(driver, sel.SHIP_ROW_CHECKED)


def count_ship_total_rows(driver) -> int:
    c = count_elements(driver, sel.SHIP_ROW_CHECKBOXES)
    return c or count_elements(driver, sel.SHIP_TABLE_ROWS)


def ensure_ship_header_select_all(driver) -> bool:
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC

    try:
        hdr = _find_first_visible(driver, sel.SHIP_SELECT_ALL_LABEL, timeout=12)
    except Exception:
        return False

    def header_is_checked():
        cls = (hdr.get_attribute("class") or "").lower()
        return "checked" in cls

    attempts = [hdr]
    try:
        mask = hdr.find_element(By.CSS_SELECTOR, ".core-checkbox-mask-wrapper")
        attempts.append(mask)
    except Exception:
        pass
    try:
        inp = hdr.find_element(By.CSS_SELECTOR, "input[type='checkbox']")
        attempts.append(inp)
    except Exception:
        pass

    try:
        driver.execute_script("arguments[0].style.zIndex='2147483647';", hdr)
    except Exception:
        pass

    def verified():
        if header_is_checked():
            return True
        if count_ship_selected_rows(driver) > 0:
            return True
        try:
            _find_first_visible(driver, sel.SHIP_BULK_SELECT_ALL, timeout=1)
            return True
        except Exception:
            return False

    for el in attempts:
        try:
            WebDriverWait(driver, 6).until(EC.element_to_be_clickable((By.XPATH, "//label[@data-id='fulfillment.table.select_current_package']")))
        except Exception:
            pass
        
        if not _safe_click_checkbox(driver, el, inp, True):
            continue
        end = time.time() + 3
        while time.time() < end:
            if verified():
                return True
            time.sleep(0.15)

    try:
        driver.execute_script(
            "const el = arguments[0];"
            "const evt = new MouseEvent('click', {bubbles:true, cancelable:true, view:window});"
            "el.dispatchEvent(evt);",
            hdr
        )
        time.sleep(0.4)
        if verified():
            return True
    except Exception:
        pass

    return False


def maybe_click_ship_bulk_select_all(driver) -> bool:
    """Click the Arrange Shipment bulk-select button."""
    selectors = sel.SHIP_BULK_SELECT_ALL

    def selection_state():
        reset = _ship_bulk_reset_visible(driver, timeout=0.2)
        selected = count_ship_selected_rows(driver)
        total = count_ship_total_rows(driver)
        header_checked = False
        try:
            hdr = _find_first_visible(driver, sel.SHIP_SELECT_ALL_LABEL, timeout=0.8)
            header_checked = "checked" in ((hdr.get_attribute("class") or "").lower())
        except Exception:
            pass
        return reset, selected, total, header_checked

    def all_selected() -> bool:
        reset, selected, total, header_checked = selection_state()
        if reset:
            return True
        if total and selected >= total:
            return True
        if header_checked and total and selected == total:
            return True
        return False

    def locate(timeout=6):
        deadline = time.time() + timeout
        while time.time() < deadline:
            for selector in selectors:
                try:
                    return _find_first_visible(driver, [selector], timeout=0.5)
                except Exception:
                    continue
            if all_selected():
                return None
            time.sleep(0.1)
        raise TimeoutException(f"Ship bulk select button not found via {selectors}")

    def click_confirm_link(timeout: float = 0.6) -> bool:
        try:
            link = _find_first_visible(driver, sel.SHIP_BULK_SELECT_ALL_LINK, timeout=timeout)
        except Exception:
            return False
        return _safe_click(driver, link)

    if click_confirm_link(timeout=0.3) and all_selected():
        return True

    if all_selected():
        return True

    click_strategies = [
        lambda element: _safe_click(driver, element, allow_actions=True),
        lambda element: driver.execute_script(
            "['mousedown','mouseup','click'].forEach(type => arguments[0].dispatchEvent(new MouseEvent(type, {bubbles:true,cancelable:true})));",
            element,
        ) or True,
        lambda element: driver.execute_script("arguments[0].click();", element) or True,
        lambda element: ActionChains(driver).move_to_element(element).pause(0.05).click().perform() or True,
        lambda element: element.send_keys(Keys.ENTER) or True,
        lambda element: element.send_keys(Keys.SPACE) or True,
    ]

    for attempt_index in range(3):
        try:
            btn = locate(timeout=6 if attempt_index == 0 else 3)
        except Exception:
            if all_selected():
                return True
            time.sleep(0.2)
            continue

        if btn is None:
            return True

        try:
            driver.execute_script("arguments[0].scrollIntoView({block:'center'}); arguments[0].focus();", btn)
        except Exception:
            pass

        stale_reference = False
        for click_fn in click_strategies:
            try:
                if click_fn(btn):
                    time.sleep(0.2)
                    click_confirm_link(timeout=0.3)
                    if all_selected() or _wait_for_ship_bulk_reset(driver):
                        return True
            except StaleElementReferenceException:
                stale_reference = True
                break
            except Exception:
                continue

        if all_selected():
            return True

        if stale_reference:
            time.sleep(0.2)
            continue

        click_confirm_link(timeout=0.4)
        time.sleep(0.2)

    return all_selected() or _wait_for_ship_bulk_reset(driver)


def open_edit_weight_drawer(driver) -> bool:
    """Open the filter drawer using JS-friendly clicks (headless-safe) and wait for it to appear."""
    try:
        btn = _find_first_visible(driver, sel.EDIT_WEIGHT_BUTTON, timeout=6)
    except Exception:
        return False
    if not _safe_click_check(driver, btn, sel.DRAWER):
        return False
    time.sleep(0.2)
    return wait_for_drawer(driver, timeout=10)

    #return click_if_present(driver, sel.EDIT_WEIGHT_BUTTON, timeout=10)


def wait_for_edit_weight_drawer(driver, timeout: int = 10) -> bool:
    end = time.time() + timeout
    while time.time() < end:
        try:
            _find_first_visible(driver, sel.WEIGHT_INPUT, timeout=2)
            return True
        except Exception:
            time.sleep(0.25)
    return False


def set_weight_and_apply(driver, weight_value: float) -> bool:
    try:
        inp = _find_first_visible(driver, sel.WEIGHT_INPUT, timeout=8)

        try:
            driver.execute_script("arguments[0].scrollIntoView({block:'center'});", inp)
            driver.execute_script("arguments[0].focus();", inp)
        except Exception:
            pass
        time.sleep(0.1)

        # Thoroughly clear the input before typing
        try:
            inp.clear()
            time.sleep(0.05)
        except Exception:
            pass

        try:
            inp.send_keys(Keys.CONTROL, "a")
            inp.send_keys(Keys.BACK_SPACE)
        except Exception:
            pass
        try:
            inp.send_keys(Keys.COMMAND, "a")
            inp.send_keys(Keys.BACK_SPACE)
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
        time.sleep(0.2)

    except Exception:
        return False

    if not click_if_present(driver, sel.BATCH_EDIT_APPLY, timeout=8):
        return False

    end = time.time() + 15
    while time.time() < end:
        try:
            _find_first_visible(driver, sel.WEIGHT_INPUT, timeout=1)
            time.sleep(0.3)
        except Exception:
            break
    return True


def set_weight_in_drawer(driver, weight_value: float) -> bool:
    """Enter the product value, pick a suggestion if available, and ensure it persists."""
    if not weight_value:
        return False

    input_selectors = sel.SINGLE_WEIGHT_INPUT

    def locate_input(timeout=6.0):
        try:
            return _find_first_visible(driver, input_selectors, timeout)
        except Exception:
            return None

    def field_has_value() -> bool:
        current = locate_input(timeout=1.0)
        if current:
            try:
                val = (current.get_attribute('value') or '')
                if val == current:
                    return True
            except Exception:
                pass
        return False

    def focus_and_type(inp_el) -> bool:
        try:
            driver.execute_script(
                "arguments[0].scrollIntoView({block:'center'}); arguments[0].focus();",
                inp_el,
            )
        except Exception:
            pass
        for combo in ((Keys.CONTROL, 'a'), (Keys.COMMAND, 'a')):
            try:
                inp_el.send_keys(*combo)
                inp_el.send_keys(Keys.BACK_SPACE)
            except Exception:
                continue
        try:
            inp_el.clear(); time.sleep(0.05)
        except Exception:
            pass
        _set_input_value(driver, inp_el, '')
        typed = False
        try:
            inp_el.send_keys(weight_value)
            typed = True
        except Exception:
            pass
        if _set_input_value(driver, inp_el, weight_value):
            typed = True
        return typed

    for _ in range(3):
        inp = locate_input(timeout=6.0)
        if not inp:
            return False
        if not focus_and_type(inp):
            continue
        time.sleep(0.15)

        if not _wait_until(field_has_value, timeout=1.8):
            inp = locate_input(timeout=1.0) or inp
            _set_input_value(driver, inp, weight_value)
            if not _wait_until(field_has_value, timeout=1.0):
                continue

        inp = locate_input(timeout=1.0) or inp
        try:
            ActionChains(driver).move_to_element(inp).pause(0.05).send_keys(Keys.TAB).perform()
        except Exception:
            try:
                driver.execute_script("arguments[0].blur && arguments[0].blur();", inp)
            except Exception:
                pass

        if _wait_until(field_has_value, timeout=1.2):
            return True

    return False

# --------------------- Print document format ---------------------
def open_print_document_editor(driver, timeout: int = 8) -> bool:
    """Open the 'Print document' popover and click Edit to open the selection modal."""
    toggle_selectors = [
        "div[data-id='fulfillment.create_shipping_label.print_document']",
        "//div[@data-id='fulfillment.create_shipping_label.print_document']",
        "//div[.//text()[contains(.,'Print document')]]",
    ]
    edit_selectors = [
        "span[data-id='fulfillment.create_shipping_label.print_document_edit']",
        "//span[@data-id='fulfillment.create_shipping_label.print_document_edit']",
        "//span[.//span[normalize-space()='Edit'] and contains(@data-id,'print_document_edit')]",
        "//span[normalize-space()='Edit']",
    ]
    check_selectors = [
        "//span[@data-id='fulfillment.create_shipping_label.print_document_edit']",
    ]

    check_edit_document_selectors = [
    ".theme-arco-drawer.theme-m4b-drawer",
    ".theme-arco-drawer .theme-arco-drawer-inner",
    ".theme-arco-drawer .theme-arco-drawer-header",
    ".theme-arco-drawer .theme-m4b-drawer-header-title",
    ".theme-arco-drawer .theme-arco-drawer-close-icon",
    ".theme-arco-drawer .theme-arco-drawer-content-nofooter",
    "span.core-checkbox-group[data-tid='m4b_checkbox_group']",
    "label[data-tid='m4b_checkbox'][data-id='fulfillment.print_document.selection.shipping_label']",
    "label[data-tid='m4b_checkbox'][data-id='fulfillment.print_document.selection.packing_slip']",
    "label[data-tid='m4b_checkbox'][data-id='fulfillment.print_document.selection.picking_list']",
    "label[data-tid='m4b_checkbox'][data-id='fulfillment.print_document.selection.hazmat_label']",
    "button[data-tid='m4b_button'][data-id='fulfillment.print_document.edit_format_settings']",
    "button[data-tid='m4b_button'][data-log_click_for='select_print_document_drawer_confirm']",
    "//div[contains(@class,'theme-arco-drawer')]",
    "//div[contains(@class,'theme-arco-drawer')]//div[contains(@class,'theme-arco-drawer-content')]",
    "//button[@data-tid='m4b_button' and @data-log_click_for='select_print_document_drawer_confirm']",
    "//label[@data-tid='m4b_checkbox' and @data-id='fulfillment.print_document.selection.hazmat_label']",
    "//span[@data-tid='m4b_checkbox_group']"
]

    try:
        btn = _find_first_visible(driver, toggle_selectors, timeout=6)
    except Exception as e:
        return False
    if not _safe_click_check(driver, btn, check_selectors):
        print("_safe_click_check - document")
        return False
    save_screenshot(driver, "open_print_document_editor")
    
    try:
        btn = _find_first_visible(driver, edit_selectors, timeout=6)
    except Exception as e:
        return False
    if not _safe_click_check(driver, btn, check_edit_document_selectors):
        print("_safe_click_check - edit document")
        return False
    
    save_screenshot(driver, "open_print_document_editor")
    return False


def _set_checkbox_by_data_id(driver, data_id: str, should_check: bool) -> bool:
    """Ensure a checkbox label with given data-id is in desired state."""
    try:
        lbl = _find_first_visible(driver, [f"//label[@data-id='{data_id}']"], timeout=6)
    except Exception:
        #print("checkbox failed 1")
        return False
    try:
        # Determine current checked state from input or class
        try:
            inp = lbl.find_element(By.CSS_SELECTOR, "input[type='checkbox']")
            cur = False
            try:
                cur = inp.is_selected()
                #print("checkbox is 1: " + str(cur))
            except Exception:
                #print("checkbox is 2: " + str(cur))
                cur = (inp.get_attribute('checked') is not None)
        except Exception:
            cls = (lbl.get_attribute('class') or '').lower()
            cur = 'checked' in cls

        if cur != should_check:
            if not _safe_click_checkbox(driver, lbl, inp, should_check):
                #print("checkbox failed 3")
                return False
            else:
                save_screenshot(driver, "should_check")
            time.sleep(0.2)
        #print("checkbox good 1")
        return True
    except Exception:
        #print("checkbox failed 2")
        return False


def change_print_document_selection(
    driver,
    shipping_label: bool = True,
    packing_slip: bool = True,
    picking_list: bool = False,
    hazmat_label: bool = False,
    timeout: int = 10,
) -> bool:
    """Open Print document > Edit, set which documents to print, then Confirm.

    Returns True if the flow completes without errors.
    """
    ok = open_print_document_editor(driver, timeout=timeout)
    print("open_print_document_editor:" + str(ok))
    if not ok:
        save_screenshot(driver, "open_print_document_editor1")
        #return False

    ok = _set_checkbox_by_data_id(driver, 'fulfillment.print_document.selection.shipping_label', shipping_label) and ok
    if ok:
        save_screenshot(driver, "fulfillment.print_document.selection.shipping_label-1")
    
    ok = _set_checkbox_by_data_id(driver, 'fulfillment.print_document.selection.packing_slip', packing_slip) and ok
    ok = _set_checkbox_by_data_id(driver, 'fulfillment.print_document.selection.picking_list', picking_list) and ok
    ok = _set_checkbox_by_data_id(driver, 'fulfillment.print_document.selection.hazmat_label', hazmat_label) and ok
    
    save_screenshot(driver, "open_print_document_editor2")
        
    # Click Confirm (or Save/Apply) in the modal
    confirm_selectors = [
        "//button[.//span[normalize-space()='Confirm'] or normalize-space()='Confirm']",
        "//button[.//span[normalize-space()='Save'] or normalize-space()='Save']",
        "//button[.//span[normalize-space()='Apply'] or normalize-space()='Apply']",
    ]

    CONFIRM_BUTTON = [
    # Best: stable via data-* attrs
    "button[data-tid='m4b_button'][data-log_click_for='select_print_document_drawer_confirm']",

    # CSS fallback (still uses data-*)
    "button.theme-arco-btn-primary[data-log_click_for='select_print_document_drawer_confirm']",

    # XPath (exact attributes)
    "//button[@data-tid='m4b_button' and @data-log_click_for='select_print_document_drawer_confirm']",

    # XPath by visible text (fallback)
    "//button[@type='button' and .//span[normalize-space()='Confirm']]",
]

    SUCCESS_ALERT = [
    # CSS — container by role + success class
    "div.core-message.core-message-success[role='alert']",

    # CSS — target the text span (useful for assertions)
    "div.core-message.core-message-success[role='alert'] .core-message-content",

    # XPath — generic container
    "//div[contains(@class,'core-message') and contains(@class,'core-message-success') and @role='alert']",    

    # XPath — visible only (guards against opacity: 0 during fade)
    "//div[contains(@class,'core-message-success') and @role='alert' and not(contains(@style,'opacity: 0'))]",

    # XPath — match by exact text content
    "//span[contains(@class,'core-message-content') and normalize-space()='All changes are saved.']/ancestor::div[contains(@class,'core-message-success')]",
]
    try:
        btn = _find_first_visible(driver, CONFIRM_BUTTON, timeout=6)
    except Exception as e:
        print(e)
        return False
    
    if not _safe_click_check(driver, btn, SUCCESS_ALERT):
        print("_safe_click_check")
        return False
    
    #if not click_if_present(driver, confirm_selectors, timeout=timeout):
    #    return False
    save_screenshot(driver, "open_print_document_editor3")
    
    # Wait for modal to disappear
    end = time.time() + timeout
    while time.time() < end:
        try:
            _find_first_visible(driver, ["//div[contains(normalize-space(),'Select documents to print')]"] , timeout=1)
            time.sleep(0.2)
        except Exception:
            break
    return ok



def _download_url_with_cookies(driver, url: str, out_path: str):
    """Download a URL using Selenium session cookies into out_path."""
    import requests
    from pdf_replace import replace_text_in_pdf, os
    sess = requests.Session()
    for c in driver.get_cookies():
        try:
            sess.cookies.set(c.get("name"), c.get("value"), domain=c.get("domain"))
        except Exception:
            pass
    r = sess.get(url, stream=True, timeout=60)
    r.raise_for_status()
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "wb") as f:
        for chunk in r.iter_content(8192):
            if chunk: f.write(chunk)
    return out_path

def _sanitize_filename(name: str) -> str:
    import re
    return re.sub(r'[\\/:*?"<>|]+', "_", (name or "")).strip() or "file"

def _try_download_pdf_from_new_tab(driver, product_name: str = None, download_dir: str = "downloads", timeout: int = 25):
    """Wait for a new tab (opened by Arrange+Print), capture its URL, download PDF, append timestamp+product, then close tab."""
    base = driver.current_window_handle
    existing = set(driver.window_handles)
    end = time.time() + timeout
    new_handle = None
    while time.time() < end:
        wins = set(driver.window_handles)
        diff = wins - existing
        if diff:
            new_handle = list(diff)[0]
            break
        time.sleep(0.2)
    if not new_handle:
        print("[WARN] No new PDF tab detected."); return False

    driver.switch_to.window(new_handle)
    time.sleep(1.0)
    url = driver.current_url
    if not (url.startswith("http://") or url.startswith("https://")):
        try:
            emb = driver.find_element(By.CSS_SELECTOR, "embed[type='application/pdf'], iframe[src*='.pdf']")
            s = emb.get_attribute("src")
            if s: url = s
        except Exception:
            pass

    # Build filename with datetime + product
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    base_name = "label"
    if product_name:
        base_name += f"--{_sanitize_filename(product_name)}"
    fname = f"{base_name}--{timestamp}.pdf"


    out_path = os.path.join(download_dir, fname)
    if url.startswith("http"):
        try:
            _download_url_with_cookies(driver, url, out_path)
            print(f"[PDF] Saved to {out_path}")
        except Exception as e:
            print(f"[WARN] Direct PDF download failed: {e}")
    else:
        print("[INFO] Non-http PDF URL encountered; consider enabling Chrome 'always_open_pdf_externally'.")

    try: driver.close()
    except Exception: pass
    try: driver.switch_to.window(base)
    except Exception: pass
    return out_path


def _try_download_pdf_headless(driver, product_name: str = None, download_dir: str = "downloads", timeout: int = 30):
    """Wait for a new PDF to land in download_dir while running headless, rename it, and return its path."""
    download_path = Path(download_dir).expanduser()
    download_path.mkdir(parents=True, exist_ok=True)

    # Allow headless Chrome to write files to the target directory when possible
    abs_download = str(download_path.resolve())

    for cmd in ("Page.setDownloadBehavior", "Browser.setDownloadBehavior"):
        try:
            driver.execute_cdp_cmd(cmd, {"behavior": "allow", "downloadPath": abs_download})
            break
        except Exception:
            continue

    existing = {file.name for file in download_path.glob("*.pdf")}
    end = time.time() + timeout
    candidate = None

    while time.time() < end:
        pdfs = list(download_path.glob("*.pdf"))
        crdownloads = list(download_path.glob("*.crdownload"))

        # Ignore partially downloaded files (Chrome writes *.crdownload until finished)
        if crdownloads:
            time.sleep(0.3)
            continue

        new_pdfs = [p for p in pdfs if p.name not in existing]
        if new_pdfs:
            candidate = max(new_pdfs, key=lambda p: p.stat().st_mtime)
            break
        time.sleep(0.3)

    if not candidate:
        print("[WARN] No PDF detected in headless download directory.")
        return None

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    base_name = "label"
    if product_name:
        base_name += f"--{_sanitize_filename(product_name)}"
    target_name = f"{base_name}--{timestamp}.pdf"
    target_path = download_path / target_name

    try:
        candidate.rename(target_path)
    except Exception:
        target_path = candidate

    print(f"[PDF] Saved to {target_path}")
    return str(target_path)


from typing import Optional

def _upload_to_gdrive(file_path: str, folder_id: Optional[str] = None) -> Optional[str]:
    """Upload a file to Google Drive using either a Service Account or OAuth client.

    Env configuration (choose one auth method):
    - Service Account: set GD_SERVICE_ACCOUNT_FILE to the JSON path.
    - OAuth client: set GD_OAUTH_CLIENT_SECRETS to client_secret.json; token is cached to token.json.
    Optional: GD_FOLDER_ID for destination folder.
    Returns uploaded file id on success, else None.
    """
    import os
    try:
        from googleapiclient.discovery import build
        from googleapiclient.http import MediaFileUpload
    except Exception as e:
        print(f"[GDRIVE] google-api-python-client not installed: {e}")
        return None

    SCOPES = ["https://www.googleapis.com/auth/drive.file"]
    creds = None

    sa_path = os.getenv("GD_SERVICE_ACCOUNT_FILE") or os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
    oauth_client = os.getenv("GD_OAUTH_CLIENT_SECRETS") or os.getenv("GOOGLE_OAUTH_CLIENT_SECRETS")
    token_path = os.getenv("GD_TOKEN_PATH", "token.json")
    if sa_path:
        try:
            from google.oauth2 import service_account
            creds = service_account.Credentials.from_service_account_file(sa_path, scopes=SCOPES)
        except Exception as e:
            print(f"[GDRIVE] Failed to load service account: {e}")
            return None
    elif oauth_client:
        try:
            from google.auth.transport.requests import Request
            from google.oauth2.credentials import Credentials
            from google_auth_oauthlib.flow import InstalledAppFlow
            if os.path.exists(token_path):
                creds = Credentials.from_authorized_user_file(token_path, SCOPES)
            if not creds or not creds.valid:
                if creds and creds.expired and creds.refresh_token:
                    creds.refresh(Request())
                else:
                    flow = InstalledAppFlow.from_client_secrets_file(oauth_client, SCOPES)
                    creds = flow.run_local_server(port=0)
                with open(token_path, 'w') as token:
                    token.write(creds.to_json())
        except Exception as e:
            print(f"[GDRIVE] OAuth setup failed: {e}")
            return None
    else:
        print("[GDRIVE] No credentials provided. Set GD_SERVICE_ACCOUNT_FILE or GD_OAUTH_CLIENT_SECRETS.")
        return None

    try:
        service = build('drive', 'v3', credentials=creds)
        metadata = {'name': os.path.basename(file_path)}
        if folder_id:
            metadata['parents'] = [folder_id]
        media = MediaFileUpload(file_path, resumable=True)
        file = service.files().create(body=metadata, media_body=media, fields='id').execute()
        file_id = file.get('id')
        print(f"[GDRIVE] Uploaded {file_path} -> id {file_id}")
        return file_id
    except Exception as e:
        print(f"[GDRIVE] Upload failed: {e}")
        return None
def click_arrange_print(driver) -> bool:
    #ok = click_if_present(driver, sel.ARRANGE_PRINT_BUTTON, timeout=12)
    ok = click_arrange_shipment_all(driver)
    if ok:
        print("click_arrange_print_ship started")
        save_screenshot(driver, "click_arrange_print_ship1")
        time.sleep(60)
    else:
        save_screenshot(driver, "click_arrange_print_ship2")
        print("exiting save screenshots")
        time.sleep(300)
        return False
    try:
        if ok and ENABLE_PDF_DOWNLOAD and PDF_DOWNLOAD_DIR:
            #out_path = _try_download_pdf_from_new_tab(driver, PDF_PRODUCT_NAME if PDF_APPEND_PRODUCT else None, PDF_DOWNLOAD_DIR, timeout=25)
            out_path = _try_download_pdf_headless(driver, PDF_PRODUCT_NAME if PDF_APPEND_PRODUCT else None, PDF_DOWNLOAD_DIR, timeout=25)

            print(out_path)
            if out_path and PDF_REPLACE:
                try:
                    import json
                    with open(PDF_REPLACE_JSON, 'r', encoding='utf-8') as f:
                        replacements = json.load(f)
                except Exception:
                    replacements = {}
                print(replacements)
                # Write to a new file with "-translated" suffix
                import os as _os
                base, ext = _os.path.splitext(out_path)
                translated_path = f"{base}-translated{ext}"
                replace_text_in_pdf(out_path, translated_path, replacements, font_path=PDF_FONT_PATH)
                out_path = translated_path
                print(f"[PDF] Replaced text written to: {out_path}")
            # Optional: upload to Google Drive
            try:
                import os as _os
                gd_should = (_os.getenv('GD_UPLOAD', '0').lower() in {'1','true','yes'})
                gd_folder = _os.getenv('GD_FOLDER_ID') or _os.getenv('GOOGLE_DRIVE_FOLDER_ID')
                # Upload the final path (translated if replacement ran)
                if out_path and gd_should:
                    _upload_to_gdrive(out_path, gd_folder)
            except Exception as _e:
                print(f"[GDRIVE] Post-download upload hook failed: {_e}")
    except Exception as e:
        print(f"[WARN] PDF post-click handler failed: {e}")
    return ok

def handle_combine_orders_modal(driver, timeout: int = 8) -> bool:
    """Return True only if the Combine Orders modal was actually present and acted upon."""
    end = time.time() + timeout
    seen = False
    while time.time() < end:
        try:
            print("checking combine...")
            btn = _find_first_visible(driver, sel.COMBINE_CONFIRM_BUTTON, timeout=1.5)
            seen = True
        except TimeoutException:
            time.sleep(0.2)
            continue
        except Exception:
            time.sleep(0.2)
            continue

        try:
            driver.execute_script("arguments[0].scrollIntoView({block:'center'});", btn)
        except Exception:
            pass
        try:
            driver.execute_script("arguments[0].focus();", btn)
        except Exception:
            pass

        clicked = False
        for click_fn in (
            lambda: btn.click(),
            lambda: driver.execute_script("arguments[0].click();", btn),
        ):
            try:
                click_fn()
                clicked = True
                break
            except Exception:
                continue

        if not clicked:
            try:
                btn.send_keys(Keys.SPACE)
                clicked = True
            except Exception:
                try:
                    driver.execute_script(
                        "arguments[0].dispatchEvent(new MouseEvent('click', {bubbles:true,cancelable:true}));",
                        btn,
                    )
                    clicked = True
                except Exception:
                    pass

        time.sleep(0.5)
        try:
            _find_first_visible(driver, sel.COMBINE_CONFIRM_BUTTON, timeout=1.2)
        except TimeoutException:
            return True
        except Exception:
            pass
    return seen





def click_back_to_manage_orders(driver) -> bool:
    """Click the breadcrumb 'Manage orders' from Arrange Shipment and confirm navigation."""
    selectors = sel.BACK_TO_MANAGE_ORDERS
    overlay_selectors = [
        "div.flex.w-full.h-full.items-center.justify-center.fixed.top-0.left-0",
        ".theme-arco-modal-mask",
        ".arco-modal-mask",
        "[data-tid='m4b_modal_mask']",
    ]

    def overlays_present() -> bool:
        for css in overlay_selectors:
            try:
                overlays = driver.find_elements(By.CSS_SELECTOR, css)
            except Exception:
                overlays = []
            for overlay in overlays:
                try:
                    if overlay.is_displayed():
                        return True
                except Exception:
                    continue
        return False

    def dismiss_overlays(timeout: float = 3.0) -> None:
        end = time.time() + timeout
        while time.time() < end and overlays_present():
            try:
                driver.find_element(By.TAG_NAME, "body").send_keys(Keys.ESCAPE)
            except Exception:
                pass
            try:
                driver.execute_script(
                    "document.dispatchEvent(new KeyboardEvent('keydown', {key:'Escape', bubbles:true}));"
                )
            except Exception:
                pass
            try:
                driver.execute_script(
                    "document.querySelectorAll('div.flex.w-full.h-full.items-center.justify-center.fixed.top-0.left-0')"
                    ".forEach(el => { el.style.pointerEvents='none'; el.style.opacity='0'; el.style.display='none'; });"
                )
            except Exception:
                pass
            time.sleep(0.2)

    def remove_blocker(target) -> bool:
        try:
            blocker = driver.execute_script(
                "const el = arguments[0];"
                "const rect = el.getBoundingClientRect();"
                "if (!rect.width || !rect.height) return null;"
                "const cx = Math.min(window.innerWidth - 1, Math.max(rect.left + rect.width / 2, 0));"
                "const cy = Math.min(window.innerHeight - 1, Math.max(rect.top + rect.height / 2, 0));"
                "const topEl = document.elementFromPoint(cx, cy);"
                "return topEl && topEl !== el && !el.contains(topEl) ? topEl : null;",
                target,
            )
        except Exception:
            return False
        if not blocker:
            return False
        try:
            driver.execute_script("arguments[0].style.pointerEvents='none'; arguments[0].style.display='none';", blocker)
        except Exception:
            pass
        try:
            driver.execute_script("arguments[0].remove();", blocker)
        except Exception:
            pass
        return True

    def manage_orders_ready(timeout: float = 6.0) -> bool:
        end = time.time() + timeout
        target_text = "manage orders"
        while time.time() < end:
            header_el = None
            try:
                header_el = _find_first_visible(driver, sel.MANAGE_ORDERS_HEADER, timeout=0.4)
            except Exception:
                header_el = None

            if header_el:
                try:
                    raw = (header_el.text or "").strip()
                except Exception:
                    raw = ""
                if not raw:
                    try:
                        raw = (header_el.get_attribute("innerText") or "").strip()
                    except Exception:
                        raw = ""
                if not raw:
                    try:
                        parent = header_el.find_element(By.XPATH, "./ancestor-or-self::*[contains(@class,'page-header-title')][1]")
                        raw = ((parent.text or "") + " " + (parent.get_attribute("innerText") or "")).strip()
                    except Exception:
                        raw = ""
                if raw:
                    if target_text in raw.lower():
                        return True
                else:
                    return True
            time.sleep(0.2)
        return False

    dismiss_overlays()

    def find_crumb(timeout: float = 8.0):
        return _find_first_visible(driver, selectors, timeout=timeout)

    def candidate_elements(base):
        candidates = [base]
        try:
            link = base.find_element(By.XPATH, "./ancestor-or-self::a[1]")
            if link not in candidates:
                candidates.append(link)
        except Exception:
            pass
        try:
            button = base.find_element(By.XPATH, "./ancestor-or-self::button[1]")
            if button not in candidates:
                candidates.append(button)
        except Exception:
            pass
        try:
            role_button = base.find_element(By.XPATH, "./ancestor-or-self::*[@role='button'][1]")
            if role_button not in candidates:
                candidates.append(role_button)
        except Exception:
            pass
        try:
            span = base.find_element(By.CSS_SELECTOR, "span[data-log_click_for='back_to_order_list']")
            if span not in candidates:
                candidates.append(span)
        except Exception:
            pass
        try:
            text_span = base.find_element(By.CSS_SELECTOR, "[data-tid='m4b_overflow_text'] span")
            if text_span not in candidates:
                candidates.append(text_span)
        except Exception:
            pass
        try:
            icon = base.find_element(By.CSS_SELECTOR, "svg")
            if icon not in candidates:
                candidates.append(icon)
        except Exception:
            pass
        return candidates

    click_strategies = [
        lambda element: _safe_click(driver, element, allow_actions=True),
        lambda element: ActionChains(driver).move_to_element(element).pause(0.05).click().perform() or True,
        lambda element: ActionChains(driver).move_to_element_with_offset(element, 1, 1).click().perform() or True,
        lambda element: ActionChains(driver).move_to_element(element).click_and_hold().pause(0.05).release().perform() or True,
        lambda element: driver.execute_script(
            "['pointerdown','mousedown','mouseup','click'].forEach(type => arguments[0].dispatchEvent(new MouseEvent(type, {bubbles:true,cancelable:true})));",
            element,
        ) or True,
        lambda element: driver.execute_script("arguments[0].click();", element) or True,
        lambda element: element.send_keys(Keys.ENTER) or True,
        lambda element: element.send_keys(Keys.SPACE) or True,
    ]

    for attempt in range(5):
        try:
            crumb = find_crumb(timeout=4 if attempt else 8)
        except Exception:
            if manage_orders_ready(timeout=2):
                return True
            dismiss_overlays(timeout=1.0)
            continue

        try:
            driver.execute_script("arguments[0].scrollIntoView({block:'center'});", crumb)
        except Exception:
            pass
        try:
            driver.execute_script("arguments[0].focus();", crumb)
        except Exception:
            pass

        while remove_blocker(crumb):
            time.sleep(0.1)

        for target in candidate_elements(crumb):
            while remove_blocker(target):
                time.sleep(0.1)
            for click_fn in click_strategies:
                try:
                    if click_fn(target):
                        if manage_orders_ready(timeout=6):
                            print("manage_orders_ready TRUE 1")
                            return True
                        time.sleep(0.3)
                except StaleElementReferenceException:
                    break
                except WebDriverException:
                    continue
                except Exception:
                    continue

        dismiss_overlays(timeout=1.0)
        time.sleep(0.4)

    if manage_orders_ready(timeout=3):
        print("manage_orders_ready TRUE 2")
        return True

    # Final fallback: try loading Manage Orders directly if breadcrumb clicks failed
    origin = base_origin().rstrip('/')
    for path in ORDERS_PATHS:
        if not path:
            continue
        url = path if path.startswith("http") else f"{origin}{path}"
        try:
            driver.get(url)
            if manage_orders_ready(timeout=8):
                print("manage_orders_ready TRUE 3")
                return True
        except Exception:
            continue

    try:
        if navigate_to_orders(driver):
            return manage_orders_ready(timeout=8)
    except Exception:
        pass
    return False
# --------------------- Full flows ---------------------

def apply_orders_filters_and_bulk(driver, product: str, order_content: str, combine_split: str, page_size: int = 50) -> bool:
    save_screenshot(driver, "apply_orders_filters_and_bulk1")
    upload_screenshots()
    ok = navigate_to_orders(driver)
    # Wait for Orders page to render before touching filters
    wait_for_orders_populated(driver, timeout=10)
    # Adjust pagination if requested
    if page_size:
        try:
            set_orders_pagination(driver, page_size)
        except Exception:
            pass
    save_screenshot(driver, "apply_orders_filters_and_bulk2")
    upload_screenshots()
    ok = open_filter_drawer(driver) and ok
    if ok:
        if product:
            print(product)
            ok = set_product_in_drawer(driver, product) and ok
        if order_content:
            print(order_content)
            ok = pick_from_select_by_placeholder(driver, "Order contents", order_content) and ok
            save_screenshot(driver, "after_select_all_orders")
        if combine_split:
            print(combine_split)
            ok = pick_from_select_by_placeholder(driver, "Order combine/split", combine_split) and ok
            save_screenshot(driver, "after_select_all_orders")
    else:
        save_screenshot(driver, "open_filter_drawer")
        upload_screenshots()
    
    applied = click_drawer_apply(driver)
    #print(applied)
    ok = applied and ok
    save_screenshot(driver, "after_select_all_orders")
    upload_screenshots()
    wait_for_orders_populated(driver, timeout=10)
    if page_size:
        try:
            set_orders_pagination(driver, page_size)
        except Exception:
            pass

    ok = ensure_header_select_all(driver) and ok
    if not ok:
        save_screenshot(driver, "ensure_header_select_all1")
        return False
    else:
        save_screenshot(driver, "ensure_header_select_all2")
    print(ok)
    time.sleep(1)
    #save_screenshot(driver, "after_select_all_orders")
    # If only a subset is initially selected, confirm bulk selection for common cases
    if order_content in ('Single item', 'Original'):
        if _bulk_reset_visible(driver):
            print("bulk reset already visible; skip maybe_click_bulk_select_all")
        else:
            print("need maybe_click_bulk_select_all")
            click_ok = maybe_click_bulk_select_all(driver)
            #ok = click_ok and ok
            #save_screenshot(driver, "after_maybe_click_bulk_select_all")
            print(click_ok)
    return ok

def apply_mix_orders_and_bulk(driver, page_size: int = 50) -> bool:
    ok = navigate_to_orders(driver)
    # Wait for Orders page to render before touching filters
    wait_for_orders_populated(driver, timeout=15)
    if page_size:
        try:
            set_orders_pagination(driver, page_size)
        except Exception:
            pass
    #ok = ensure_header_select_all(driver) and ok
    #time.sleep(0.4)
    #save_screenshot(driver, "after_select_all_orders")
    return ok


def orders_to_shipping_and_edit_weight(driver, weight_value: float, do_print: bool = True) -> bool:
    """Open Arrange Shipment. If Combine Orders modal appears, go back via breadcrumb, reselect, and try again.
    Otherwise, continue with Arrange Shipment tasks. Returns True on success."""
    ok = True

    ok = click_arrange_shipment(driver) and ok
    print("click_arrange_shipment: " + str(ok))
    if not ok:
        save_screenshot(driver, "click_arrange_shipment")
        upload_screenshots()
        return False
    save_screenshot(driver, "orders_to_shipping_and_edit_weight1")
    modal_seen = handle_combine_orders_modal(driver, timeout=8)
    modal_seen = True
    if modal_seen:
        wait_for_shipping_page_ready(driver, timeout=15)
        if not click_back_to_manage_orders(driver):
            try:
                print("navigate_to_orders")
                navigate_to_orders(driver)
            except Exception:
                pass
        wait_for_orders_populated(driver, timeout=10)
        time.sleep(0.5)
        try:
            print("try find first")
            _find_first_visible(driver, sel.SELECT_ALL_HEADER, timeout=12)
        except Exception:
            print("no find first")
            time.sleep(0.5)
        time.sleep(0.5)
        try:
            print("try ensure_order_header_select_all")
            ok = ensure_order_header_select_all(driver)
            if ok:
                print("ok ensure_order_header_select_all")
            else:
                save_screenshot(driver, "ensure_order_header_select_all")
                print("copy screenshots now!!!!")
                time.sleep(60)
            save_screenshot(driver, "orders_to_shipping_and_edit_weight2")
        except Exception:
            print("no ensure_order_header_select_all")
            pass
        time.sleep(0.5)
        if _bulk_reset_visible(driver):
            print("bulk reset already visible after header select")
        else:
            try:
                print("try maybe_click_bulk_select_alls")
                maybe_click_bulk_select_all(driver)
                save_screenshot(driver, "orders_to_shipping_and_edit_weight3")
            except Exception:
                print("no maybe_click_bulk_select_all")
                pass
        print("click_arrange_shipment 1: " + str(ok))
        ok = click_arrange_shipment(driver) and ok
        if not ok:
            print("click_arrange_shipment 2: " + str(ok))
            return False
    save_screenshot(driver, "shipping_ready1")
    wait_for_shipping_page_ready(driver, timeout=15)
    save_screenshot(driver, "shipping_ready2")

    ok = ensure_ship_header_select_all(driver) and ok
    print("ensure_ship_header_select_all " +str(ok))
    save_screenshot(driver, "shipping_ready")
    if count_ship_selected_rows(driver) == 0 and count_ship_total_rows(driver) > 0:
        time.sleep(1)
        ok = ensure_ship_header_select_all(driver) and ok
    
    try:
        print("try maybe_click_ship_bulk_select_all ship")
        maybe_click_bulk_select_all_ship(driver)
    except Exception:
        print("no maybe_click_ship_bulk_select_all ship")
        pass

    save_screenshot(driver, "shipping_selected_all")

    ok = open_edit_weight_drawer(driver) and ok
    save_screenshot(driver, "shipping_weight_applied1")
    if wait_for_edit_weight_drawer(driver, timeout=12):
        #ok = set_weight_and_apply(driver, weight_value) and ok
        ok = set_weight_in_drawer(driver, weight_value) and ok
        if not click_if_present(driver, sel.BATCH_EDIT_APPLY, timeout=8):
            return False
    else:
        ok = False
        save_screenshot(driver, "shipping_weight_applied3")

    applied = click_drawer_apply(driver)
    print("applied weight:" + str(applied))
    if applied:
        ok = change_print_document_selection(driver)
        print("change_print_document_selection:" + str(ok))
        if ok:
            save_screenshot(driver, "change_print_document_selection1")
            pass
        else:
            save_screenshot(driver, "change_print_document_selection2")
    else:
        save_screenshot(driver, "shipping_weight_applied2")

    if do_print:
        ok = click_arrange_print(driver) and ok
        if ok:
            save_screenshot(driver, "shipping_clicked_print1")
            time.sleep(60)
    save_screenshot(driver, "shipping_clicked_print2")
    return ok

def mix_orders_to_shipping_and_edit_weight(driver) -> bool:
    """Open Arrange Shipment. If Combine Orders modal appears, go back via breadcrumb, reselect, and try again.
    Otherwise, continue with Arrange Shipment tasks. Returns True on success."""
    ok = True

    ok = click_arrange_shipment(driver) and ok
    if not ok:
        return False

    modal_seen = handle_combine_orders_modal(driver, timeout=8)

    wait_for_shipping_page_ready(driver, timeout=15)

    from row_processor import process_arrange_shipment_tbody_rows

    # after you navigate to Arrange Shipment and the page has populated
    print("start process")
    summary = process_arrange_shipment_tbody_rows(driver, max_rows=None, per_row_delay=2, weight_click_delay=2)
    print(summary)

    save_screenshot(driver, "shipping_ready")

    return ok

def _create_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "TikTok Shop Automation "
            + __VERSION__
            + ": login -> filter orders -> select all -> arrange -> (combine modal) -> shipping select all -> batch edit weight -> print"
        )
    )
    parser.add_argument("--product", default="G-BOX-FD-STRAWBERRY-SHORTCAKE-L", help="Product name/SKU to filter")
    parser.add_argument("--order-content", default="Single item", help="Order content option text")
    parser.add_argument("--combine-split", default="Original", help="Order combine/split option text")
    parser.add_argument("--weight", type=float, default=0.65, help="Package weight to set in the batch edit drawer (e.g., 0.65)")
    parser.add_argument("--no-print", action="store_true", help="Do not click 'Arrange shipment+print' at the end")
    parser.add_argument("--download-pdf-dir", default="downloads", help="Directory to save PDF label(s)")
    parser.add_argument("--no-pdf-download", action="store_true", help="Disable auto PDF download after Arrange+Print")
    parser.add_argument("--no-append-product", action="store_true", help="Do not append --<product> to PDF filename")
    parser.add_argument("--pdf-replace", action="store_true", default=True, help="Enable PDF text replace overlay")
    parser.add_argument("--pdf-replace-json", default="replacements.json", help="Path to JSON map for replacements")
    parser.add_argument("--pdf-font", default="simsun.ttf", help="TTF path for Chinese font (e.g., SimSun)")
    parser.add_argument("--pagination", type=int, default=50, help="Orders page size (e.g., 20, 50, 100)")
    return parser


def _run_flow(args) -> dict:
    logger.info("Start")
    driver = None
    result = {"success": True, "exit_code": 0}

    class FlowAbort(Exception):
        pass

    def fail(code: int, message: str = ""):
        if message:
            print(message)
            logger.info(message)
        result["success"] = False
        result["exit_code"] = code
        raise FlowAbort()

    global ENABLE_PDF_DOWNLOAD, PDF_DOWNLOAD_DIR, PDF_APPEND_PRODUCT, PDF_PRODUCT_NAME
    global PDF_REPLACE, PDF_REPLACE_JSON, PDF_FONT_PATH

    ENABLE_PDF_DOWNLOAD = not args.no_pdf_download
    pdf_dir = Path(args.download_pdf_dir).expanduser()
    if not pdf_dir.is_absolute():
        pdf_dir = ARTIFACTS / pdf_dir
    PDF_DOWNLOAD_DIR = str(pdf_dir)
    PDF_APPEND_PRODUCT = not args.no_append_product
    PDF_PRODUCT_NAME = args.product
    PDF_REPLACE = args.pdf_replace
    #PDF_REPLACE_JSON = args.pdf_replace_json
    PDF_FONT_PATH = args.pdf_font

    try:
        os.makedirs(PDF_DOWNLOAD_DIR, exist_ok=True)
    except Exception:
        pass

    try:
        driver = _driver()
        save_screenshot(driver, "start")
        upload_screenshots()
        if not login_flow(driver, USERNAME, PASSWORD):
            fail(2, "Login failed.")
            upload_screenshots()

        mix_order_flag = '1' if os.getenv('MIX_ORDER') == '1' else '0'
        save_screenshot(driver, "after_login")
        upload_screenshots()
        if mix_order_flag == '1':
            if not apply_mix_orders_and_bulk(driver, page_size=args.pagination):
                fail(3, "Failed during apply mix order and bulk.")
            if not apply_orders_filters_and_bulk(driver, args.product, args.order_content, args.combine_split, page_size=args.pagination):
                fail(3, "Failed during orders filtering/selection.")
            if not mix_orders_to_shipping_and_edit_weight(driver):
                fail(3, "Failed during mix order to shipping.")
            if not HEADLESS:
                print("Leaving the browser open for 60 seconds...")
                logger.info("Leaving the browser open for 60 seconds...")
                time.sleep(30060)
        else:
            if not apply_orders_filters_and_bulk(driver, args.product, args.order_content, args.combine_split, page_size=args.pagination):
                save_screenshot(driver, "after_select_all_orders")
                fail(3, "Failed during orders filtering/selection.")

            ok = orders_to_shipping_and_edit_weight(driver, weight_value=args.weight, do_print=not args.no_print)
            save_screenshot(driver, "orders_to_shipping_and_edit_weight")
            if ok:
                print("Completed: filtered orders, selected all, navigated to shipping, edited weight, and initiated print.")
                logger.info("Completed: filtered orders, selected all, navigated to shipping, edited weight, and initiated print.")
            else:
                print("Completed with issues; check screenshots/.")
                logger.info("Completed with issues; check screenshots/.")

            if not HEADLESS:
                print("Leaving the browser open for 60 seconds...")
                logger.info("Leaving the browser open for 60 seconds...")
                time.sleep(30060)
            save_screenshot(driver, "after_select_all_orders")
        result["success"] = True
        result["exit_code"] = 0
    except FlowAbort:
        pass
    except WebDriverException as e:
        print(f"WebDriver error: {e}")
        result["success"] = False
        result.setdefault("exit_code", 1)
    except Exception as e:
        print(f"Error: {e}")
        result["success"] = False
        result.setdefault("exit_code", 1)
    finally:
        if HEADLESS and driver:
            driver.quit()
        dump_cookies(driver)

    return result


def main(argv=None):
    parser = _create_arg_parser()
    args = parser.parse_args(argv)
    outcome = _run_flow(args)
    if not outcome.get("success", False):
        sys.exit(outcome.get("exit_code", 1))


def lambda_handler(event=None, context=None):
    event = event or {}
    parser = _create_arg_parser()
    args = parser.parse_args([])

    def _bool(val):
        if isinstance(val, bool):
            return val
        if isinstance(val, str):
            return val.strip().lower() in {"1", "true", "yes", "on"}
        if val is None:
            return False
        return bool(val)

    mappings = {
        "product": str,
        "order_content": str,
        "combine_split": str,
        "download_pdf_dir": str,
        "pdf_font": str,
    }
    for key, caster in mappings.items():
        if key in event and event[key] is not None:
            try:
                setattr(args, key, caster(event[key]))
            except Exception:
                setattr(args, key, event[key])

    if "weight" in event and event["weight"] is not None:
        try:
            args.weight = float(event["weight"])
        except Exception:
            pass

    if "pagination" in event and event["pagination"] is not None:
        try:
            args.pagination = int(event["pagination"])
        except Exception:
            pass

    for key in ("no_print", "no_pdf_download", "no_append_product", "pdf_replace"):
        if key in event and event[key] is not None:
            setattr(args, key, _bool(event[key]))

    outcome = _run_flow(args)
    status = 200 if outcome.get("success") else 500
    return {"statusCode": status, **outcome}


if __name__ == "__main__":
    main()


# [PATCHED v5.5.4] Mix Order flow helpers
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains
import time
import requests
from pdf_replace import replace_text_in_pdf
# --- PDF download config ---
ENABLE_PDF_DOWNLOAD = True
PDF_DOWNLOAD_DIR = 'downloads'
PDF_APPEND_PRODUCT = True
PDF_PRODUCT_NAME = None


def _try_click(driver, locators, timeout_each=8):
    for by, sel in locators:
        try:
            el = WebDriverWait(driver, timeout_each).until(EC.element_to_be_clickable((by, sel)))
            if _safe_click(driver, el):
                return True
        except Exception:
            continue
    return False

def _wait_arrange_page(driver, timeout=40):
    wait = WebDriverWait(driver, timeout)
    try:
        wait.until(lambda d: 'arrange' in (d.current_url or '').lower() and 'shipment' in (d.current_url or '').lower())
    except Exception:
        try:
            wait.until(EC.presence_of_element_located((By.XPATH, "//*[contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'arrange shipment')]")))
        except Exception:
            pass
    # Wait for tbody
    for by, sel in [(By.CSS_SELECTOR, "table tbody"),
                    (By.XPATH, "//table//tbody"),
                    (By.CSS_SELECTOR, ".arco-table-content table tbody, .pulse-table table tbody")]:
        try:
            wait.until(EC.presence_of_element_located((by, sel))); break
        except Exception:
            continue

def perform_mix_order_flow(driver, logger=None):
    # 1) Select all
    select_all = [
        (By.CSS_SELECTOR, "thead input[type='checkbox']"),
        (By.XPATH, "//th//input[@type='checkbox' or @role='checkbox']"),
        (By.CSS_SELECTOR, "label[data-id*='select_all'] input[type='checkbox']"),
        (By.XPATH, "//label[contains(@class,'checkbox')]//input[@type='checkbox']")
    ]
    _try_click(driver, select_all)
    time.sleep(0.4)
    # 2) Arrange shipment
    arrange_btn = [
        (By.XPATH, "//button[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'arrange shipment')]"),
        (By.XPATH, "//*[self::a or self::button][contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'arrange shipment')]"),
        (By.CSS_SELECTOR, "[data-id*='arrange'][data-id*='shipment'], [data-tid*='arrange'][data-tid*='shipment']"),
    ]
    _try_click(driver, arrange_btn)
    # 3) Wait for Arrange shipment
    _wait_arrange_page(driver, timeout=50)
    time.sleep(0.8)
    # 4) For each tbody row, click the product cell
    try:
        tbody = WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.XPATH, "//table//tbody")))
        rows = tbody.find_elements(By.XPATH, "./tr[not(contains(@style,'display: none'))]")
    except Exception as e:
        rows = []
        if logger:
            try: logger.warning(f"[PATCHED v5.5.4] Could not get rows: {e}")
            except Exception: pass
    for idx, row in enumerate(rows, start=1):
        try:
            cell = None
            for xp in [".//td[.//div[@data-log_click_for='cell_product']]",
                       ".//td[contains(@class,'theme-arco-popover-open')]",
                       ".//td[contains(@class,'sc-cVMLIT')]",
                       ".//td[1]"]:
                els = row.find_elements(By.XPATH, xp)
                if els:
                    cell = els[0]; break
            if not cell: 
                continue
            try:
                driver.execute_script("arguments[0].scrollIntoView({block:'center'});", cell)
            except Exception:
                pass
            target = None
            for tx in [".//div[@data-log_click_for='cell_product']",
                       ".//*"]:
                try:
                    target = cell.find_element(By.XPATH, tx)
                    if target: break
                except Exception:
                    continue
            if not target: target = cell
            ActionChains(driver).move_to_element(target).pause(0.05).click(target).perform()
            time.sleep(0.2)
        except Exception as e:
            if logger:
                try: logger.info(f"[PATCHED v5.5.4] Row {idx} click skipped: {e}")
                except Exception: pass
    return True
