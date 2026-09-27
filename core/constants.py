"""
Constants and magic numbers for the library seat booking system.
"""
import os

# ====== API Endpoints ======
SSO_BASE = "https://sso.axhu.edu.cn"
SEAT_BASE = "https://seat.axhu.edu.cn"

# ====== HMAC Secret ======
# IMPORTANT: This should be set via environment variable, not hardcoded.
# The value here is a placeholder and will NOT work.
HMAC_SECRET = os.environ.get("HMAC_SECRET", "")

# ====== Time defaults (in minutes from midnight) ======
DEFAULT_MAX_END = 1320    # 22:00
DEFAULT_MIN_START = 480   # 08:00

# ====== Captcha solver thresholds ======
TEMPLATE_MATCH_MIN_CONFIDENCE = 0.15
TEMPLATE_MATCH_MAX_RETRIES = 3
VISION_API_TIMEOUT = 30    # seconds

# ====== Booking retry ======
MAX_BOOK_RETRIES = 3

# ====== File paths ======
TOKEN_CACHE_FILE = ".token_cache.json"
CONFIG_FILE = "config.json"

# ====== Preset rooms ======
PRESET_ROOMS = [
    "Second Study Room",
    "308 Study Room",
    "Third Study Room",
    "First Study Room",
    "First Study Room A",
]

# Mapping of preset room names (English -> Chinese, configurable)
ROOM_NAME_MAP = {
    "Second Study Room": "第二自习室",
    "308 Study Room": "308自习室",
    "Third Study Room": "第三自习室",
    "First Study Room": "第一自习室",
    "First Study Room A": "第一自习室A",
}

# ====== Default time presets ======
TIME_PRESETS = {
    "1": (600, "10:00"),
    "2": (780, "13:00"),
    "3": (840, "14:00"),
    "4": (900, "15:00"),
}
