"""
AI Vision captcha solver — uses multimodal LLM (Doubao/GPT-4V/Qwen-VL) to find
click targets in behavioral captcha images.
"""

import base64
import json
import os
import re

import cv2
import numpy as np
import requests

# Configurable via environment variables or config.json
API_CONFIG = {
    "base_url": os.environ.get(
        "VISION_API_BASE_URL",
        "https://ark.cn-beijing.volces.com/api/v3/chat/completions",
    ),
    "api_key": os.environ.get("VISION_API_KEY", ""),
    "model": os.environ.get("VISION_API_MODEL", "doubao-seed-2-0-code-preview-260215"),
    "max_tokens": 300,
    "temperature": 0.1,
}

PROMPT = """You are a captcha solving assistant. I will provide two images:
- Image 1 (small): a reference Chinese character (the target to find)
- Image 2 (large): a larger image containing many Chinese characters

Your task: find the Chinese character in the large image that matches the reference character in the small image (ignore minor font/style differences).

Assume the large image's top-left is (0, 0) and bottom-right is (1000, 1000).
Return the click coordinates proportionally, rounded to integers.

If you find the target, return JSON:
{"found": true, "coords": [[x, y]]}
For multiple targets that need sequential clicking:
{"found": true, "coords": [[x1, y1], [x2, y2]]}
If not found:
{"found": false}

Reply with JSON only, no other text."""


class VisionCaptchaSolver:
    """Multi-modal AI captcha solver."""

    def __init__(self, config=None):
        self.config = {**API_CONFIG, **(config or {})}

    def is_configured(self):
        """Check if API key is set."""
        key = self.config.get("api_key", "")
        return bool(key) and key != "YOUR_API_KEY_HERE"

    def update_config_from_dict(self, cfg):
        """Update API config from a dict (e.g., from config.json)."""
        for k in ("api_key", "base_url", "model"):
            if k in cfg and cfg[k]:
                self.config[k] = cfg[k]

    def _encode_image(self, img_bytes):
        """Encode image bytes as base64 data URI."""
        return f"data:image/png;base64,{base64.b64encode(img_bytes).decode()}"

    def solve(self, big_img_bytes, small_img_bytes, word_check_count=1):
        """
        Send captcha images to AI, return click coordinates.
        Returns list of (x, y) tuples, or None on failure.
        """
        big_b64 = self._encode_image(big_img_bytes)
        small_b64 = self._encode_image(small_img_bytes)

        messages = [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {"url": small_b64, "detail": "high"},
                    },
                    {"type": "text", "text": "Image 1 (reference): target character"},
                    {
                        "type": "image_url",
                        "image_url": {"url": big_b64, "detail": "high"},
                    },
                    {
                        "type": "text",
                        "text": "Image 2 (search area): find the matching character here",
                    },
                    {"type": "text", "text": PROMPT},
                ],
            }
        ]

        payload = {
            "model": self.config["model"],
            "messages": messages,
            "max_tokens": self.config["max_tokens"],
            "temperature": self.config["temperature"],
        }
        headers = {
            "Authorization": f"Bearer {self.config['api_key']}",
            "Content-Type": "application/json",
        }

        try:
            resp = requests.post(
                self.config["base_url"],
                json=payload,
                headers=headers,
                timeout=30,
            )
            resp.raise_for_status()
            result = resp.json()
        except requests.exceptions.RequestException as e:
            print(f"[!] AI API request failed: {e}")
            return None

        try:
            text = result["choices"][0]["message"]["content"].strip()
        except (KeyError, IndexError, TypeError) as e:
            print(f"[!] AI response format error: {e}")
            return None

        print(f"[*] AI raw response: {text}")
        return self._parse_response(text, big_img_bytes)

    def _parse_response(self, text, big_img_bytes):
        """Parse AI response and convert proportional coords to pixel coords."""
        # Strip markdown code fences
        m = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
        if m:
            text = m.group(1).strip()

        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            m = re.search(r"\{[^}]+\}", text)
            if m:
                try:
                    data = json.loads(m.group())
                except json.JSONDecodeError:
                    print("[!] Cannot parse AI response as JSON")
                    return None
            else:
                print("[!] Cannot parse AI response as JSON")
                return None

        if not data.get("found"):
            print("[!] AI did not find target")
            return None

        coords = data.get("coords", [])
        if not coords:
            print("[!] AI returned empty coords")
            return None

        # Convert proportional (0-1000) to actual pixel coords
        big = cv2.imdecode(np.frombuffer(big_img_bytes, np.uint8), 1)
        bh, bw = big.shape[:2]

        real_coords = []
        for cx, cy in coords:
            real_x = int(cx / 1000.0 * bw)
            real_y = int(cy / 1000.0 * bh)
            real_coords.append((real_x, real_y))
            print(
                f"    Prop ({cx}, {cy}) -> Pixel ({real_x}, {real_y}) "
                f"(image {bw}x{bh})"
            )

        return real_coords
