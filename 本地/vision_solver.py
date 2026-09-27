"""
验证码视觉求解器 — 调用多模态 AI（豆包/GPT-4V/Qwen-VL 等）识别点击位置
通用 OpenAI-compatible API 格式，支持任何兼容的视觉模型
"""
import base64
import json
import requests


# ====== 配置：改成你自己的 API 信息 ======
# 豆包（火山方舟 Ark）: https://console.volcengine.com/ark
API_CONFIG = {
    "base_url": "https://ark.cn-beijing.volces.com/api/v3/chat/completions",
    "api_key": "YOUR_API_KEY_HERE",
    "model": "doubao-seed-2-0-code-preview-260215",
    "max_tokens": 300,
    "temperature": 0.1,
}

PROMPT = """你是一个验证码识别助手。我会给你两张图片：
- 图1（小图）：一个参考汉字字符，这是你需要找的目标
- 图2（大图）：一张包含多个汉字的大图

你的任务：在大图中找到与小图中相同的汉字（忽略字形大小和字体的细微差异），然后告诉我应该点击哪个位置。

假设大图的左上角坐标是 (0, 0)，右下角坐标是 (1000, 1000)。
请依照这个比例，给出点击坐标（精确到个位）。

如果你找到了目标字，返回 JSON 格式：
{"found": true, "coords": [[x, y]]}
如果有多个相同的字需要依次点击，返回多个坐标：
{"found": true, "coords": [[x1, y1], [x2, y2]]}
如果找不到，返回：
{"found": false}

只返回 JSON，不要其他内容。"""


class VisionCaptchaSolver:
    """多模态 AI 验证码求解器"""

    def __init__(self, config=None):
        self.config = {**API_CONFIG, **(config or {})}

    def _encode_image(self, img_bytes):
        """将图片字节编码为 base64 data URI"""
        return f"data:image/png;base64,{base64.b64encode(img_bytes).decode()}"

    def solve(self, big_img_bytes, small_img_bytes, word_check_count=1):
        """
        发送验证码图片到 AI，返回点击坐标列表
        参数:
            big_img_bytes: 大图（验证码背景图）的 PNG 字节
            small_img_bytes: 小图（目标汉字）的 PNG 字节
            word_check_count: 需要点击的次数
        返回:
            [(x, y), ...] 坐标列表，或 None（求解失败）
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
                    {
                        "type": "text",
                        "text": "图1（小图）：参考目标汉字",
                    },
                    {
                        "type": "image_url",
                        "image_url": {"url": big_b64, "detail": "high"},
                    },
                    {
                        "type": "text",
                        "text": "图2（大图）：请在这张图中找到与图1相同的汉字",
                    },
                    {
                        "type": "text",
                        "text": PROMPT,
                    },
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
            print(f"[!] AI API 请求失败: {e}")
            return None

        # 提取回复文本
        try:
            text = result["choices"][0]["message"]["content"].strip()
        except (KeyError, IndexError, TypeError) as e:
            print(f"[!] AI 回复格式异常: {e}")
            print(f"    原始响应: {json.dumps(result, ensure_ascii=False)[:500]}")
            return None

        print(f"[*] AI 原始回复: {text}")

        # 解析 JSON
        return self._parse_response(text, big_img_bytes)

    def _parse_response(self, text, big_img_bytes):
        """从 AI 回复中提取坐标"""
        # 去除可能的 markdown 代码块标记
        import re
        # 尝试匹配 ```json ... ``` 或 ``` ... ```
        m = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', text, re.DOTALL)
        if m:
            text = m.group(1).strip()

        # 尝试直接解析 JSON
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            # 尝试从文本中提取 JSON 对象
            m = re.search(r'\{[^}]+\}', text)
            if m:
                try:
                    data = json.loads(m.group())
                except json.JSONDecodeError:
                    print(f"[!] 无法从 AI 回复中解析坐标")
                    return None
            else:
                print(f"[!] 无法从 AI 回复中解析坐标")
                return None

        if not data.get("found"):
            print("[!] AI 未找到目标字")
            return None

        coords = data.get("coords", [])
        if not coords:
            print("[!] AI 返回空坐标")
            return None

        # 将比例坐标 (0-1000) 转换为实际像素坐标
        import numpy as np
        import cv2
        big = cv2.imdecode(np.frombuffer(big_img_bytes, np.uint8), 1)
        bh, bw = big.shape[:2]

        real_coords = []
        for cx, cy in coords:
            # 比例 0-1000 → 实际像素
            real_x = int(cx / 1000.0 * bw)
            real_y = int(cy / 1000.0 * bh)
            real_coords.append((real_x, real_y))
            print(f"    比例坐标 ({cx}, {cy}) → 实际像素 ({real_x}, {real_y}) "
                  f"(图片尺寸 {bw}x{bh})")

        return real_coords


# ====== 自测 ======
if __name__ == "__main__":
    import sys
    if len(sys.argv) < 3:
        print("用法: python vision_solver.py <big_image.png> <small_image.png>")
        sys.exit(1)

    with open(sys.argv[1], "rb") as f:
        big_bytes = f.read()
    with open(sys.argv[2], "rb") as f:
        small_bytes = f.read()

    solver = VisionCaptchaSolver()
    coords = solver.solve(big_bytes, small_bytes)
    print(f"\n结果: {coords}")
