"""Core configuration management — reads from config.json and environment variables."""

import os
import json

from .constants import CONFIG_FILE, HMAC_SECRET


def load_config(path=None):
    """Load config.json from path, or CONFIG_FILE in cwd."""
    if path is None:
        path = CONFIG_FILE

    cfg = {}
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    return cfg


def get_secrets():
    """Get secrets from environment variables (preferred) or config file (fallback)."""
    cfg = load_config()

    return {
        "hmac_secret": os.environ.get("HMAC_SECRET") or cfg.get("hmac_secret", ""),
        "username": os.environ.get("LIBRARY_USERNAME") or cfg.get("username", ""),
        "password": os.environ.get("LIBRARY_PASSWORD") or cfg.get("password", ""),
        "vision_api_key": os.environ.get("VISION_API_KEY") or cfg.get("vision_api_key", ""),
        "vision_base_url": (
            os.environ.get("VISION_API_BASE_URL")
            or cfg.get("vision_base_url", "https://ark.cn-beijing.volces.com/api/v3/chat/completions")
        ),
        "vision_model": (
            os.environ.get("VISION_API_MODEL")
            or cfg.get("vision_model", "doubao-seed-2-0-code-preview-260215")
        ),
        "webhook_url": os.environ.get("WEBHOOK_URL") or cfg.get("webhook_url", ""),
    }


def get_user_preferences():
    """Get user booking preferences from config."""
    cfg = load_config()
    return {
        "room": cfg.get("room", ""),
        "start_time": cfg.get("start_time", ""),
        "seat": cfg.get("seat", ""),
        "date": cfg.get("date", "auto"),
    }
