from pathlib import Path
import errno
import os
from dotenv import load_dotenv

# Load .env in project root if present
load_dotenv()

# --- Credentials (from .env or environment variables) ---
USERNAME = os.getenv("TT_USERNAME", "").strip()
PASSWORD = os.getenv("TT_PASSWORD", "").strip()

# --- Headless (0/1, true/false) ---
HEADLESS = os.getenv("TT_HEADLESS", "0").lower() in {"1", "true", "yes"}

# --- Optional Chrome user profile ---
USER_DATA_DIR = os.getenv("TT_USER_DATA_DIR", "").strip() or None
PROFILE_DIR = os.getenv("TT_PROFILE_DIR", "").strip() or None

# --- Login URL (region-specific) ---
LOGIN_URL = os.getenv("TT_LOGIN_URL", "https://seller-us.tiktok.com/account/login")

# --- Output locations ---
PROJECT_ROOT = Path(__file__).resolve().parent


def _resolve_artifacts_dir() -> Path:
    candidates = []
    env_dir = os.getenv("TT_ARTIFACTS_DIR", "").strip()
    if env_dir:
        candidates.append(Path(env_dir).expanduser())
    candidates.append(PROJECT_ROOT / "artifacts")
    candidates.append(Path("/tmp/tiktok_artifacts"))

    art_dir = Path(os.getenv("TT_ARTIFACTS_DIR", "/tmp/tiktok_artifacts"))
    if "/var/task" in str(art_dir):
        art_dir.mkdir(parents=True, exist_ok=True)
    else:
        if not os.access(art_dir.parent, os.W_OK):
            art_dir = Path("/tmp/tiktok_artifacts")
            
    for directory in candidates:
        try:
            directory.mkdir(parents=True, exist_ok=True)
            if os.access(directory, os.W_OK):
                return directory
        except OSError as exc:
            if exc.errno not in {errno.EROFS, errno.EACCES}:
                raise
    # Fallback: last candidate even if mkdir failed (best effort)
    fallback = Path("/tmp/tiktok_artifacts")
    fallback.mkdir(parents=True, exist_ok=True)

    return fallback

TT_TMP_DIR = os.getenv("TT_TMP_DIR", "/tmp")
ARTIFACTS = _resolve_artifacts_dir()

SCREENSHOTS_DIR = ARTIFACTS / "screenshots"
SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)

COOKIES_JSON = ARTIFACTS / "cookies.json"
COOKIES_JSON = PROJECT_ROOT / "artifacts" / "cookies.json"
print(COOKIES_JSON)
print(PROJECT_ROOT)
# --- Orders navigation ---
def base_origin():
    return os.getenv("TT_SELLER_ORIGIN", "https://seller-us.tiktok.com")

ORDERS_PATHS = [
    "/order",  # Manage orders root
    "/fulfillment/orders/to-ship",
    "/order/list?tab=to_ship",
    "/orders/to_ship",
]


# --- Logging ---
_log_dir_setting = os.getenv("TT_LOG_DIR", "").strip()
if _log_dir_setting:
    LOG_DIR = Path(_log_dir_setting).expanduser()
    if not LOG_DIR.is_absolute():
        LOG_DIR = ARTIFACTS / LOG_DIR
else:
    LOG_DIR = ARTIFACTS / "logs"
LOG_LEVEL = os.getenv("TT_LOG_LEVEL", "INFO").upper()
LOG_MAX_BYTES = int(os.getenv("TT_LOG_MAX_BYTES", "1048576"))  # 1 MB
LOG_BACKUP_COUNT = int(os.getenv("TT_LOG_BACKUP_COUNT", "5"))
BROWSER_LOGS = os.getenv("TT_BROWSER_LOGS", "1").lower() in {"1","true","yes"}
