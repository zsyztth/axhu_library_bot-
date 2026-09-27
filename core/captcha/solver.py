"""
验证码求解器 — 多策略渐进降级
策略: 文字OCR → 模板匹配 → AI视觉 → 手动点击(仅交互模式)
"""

import json
import base64 as b64
import cv2
import numpy as np

from ..constants import (
    SEAT_BASE,
    TEMPLATE_MATCH_MIN_CONFIDENCE,
    TEMPLATE_MATCH_MAX_RETRIES,
)


class CaptchaSolver:
    """多策略验证码求解器，挂载到 LibSeatAPI 实例上"""

    def __init__(self, bot):
        self.bot = bot

    # ===== 文字验证码 =====

    def get_text_captcha(self):
        """获取文字验证码"""
        from ..api_client import make_hmac_headers

        url = f"{SEAT_BASE}/auth/createCaptcha"
        headers = {
            "Authorization": self.bot.token,
            "Referer": f"{SEAT_BASE}/libseat/",
            "loginType": "PC",
            **make_hmac_headers("GET"),
        }
        resp = self.bot.session.get(url, headers=headers)
        return resp.json()

    def _ocr_text_captcha(self, data_uri):
        """ddddocr 识别文字验证码"""
        if not data_uri or not data_uri.startswith("data:image/"):
            return None
        img_bytes = b64.b64decode(data_uri.split(",", 1)[-1])
        return self.bot.ocr.classification(img_bytes).strip()

    # ===== 点击验证码 =====

    def get_click_captcha(self):
        """获取行为点击验证码。返回 {image, wordImage, token, ...}"""
        from ..api_client import make_hmac_headers

        url = f"{SEAT_BASE}/cap/captcha/{self.bot.token}"
        params = {"username": self.bot.username}
        headers = {
            "Authorization": self.bot.token,
            "Referer": f"{SEAT_BASE}/libseat/",
            "loginType": "PC",
            **make_hmac_headers("POST"),
        }
        resp = self.bot.session.post(url, params=params, headers=headers)
        return resp.json()

    @staticmethod
    def _decode_captcha_images(challenge):
        """解码验证码图片 (big, small)"""
        big_bytes, small_bytes = None, None
        for key, target in [("image", "big"), ("wordImage", "small")]:
            data_uri = challenge.get(key, "")
            if data_uri and data_uri.startswith("data:image/"):
                img_bytes = b64.b64decode(data_uri.split(",", 1)[-1])
                if target == "big":
                    big_bytes = img_bytes
                else:
                    small_bytes = img_bytes
        return big_bytes, small_bytes

    def check_captcha(self, captcha_token, answer):
        """
        提交验证码答案
        answer: 字符串（文字）或 [{"x":x,"y":y}] 列表（点击）
        """
        from ..api_client import make_hmac_headers

        if isinstance(answer, str):
            answer = [answer]
        encoded = b64.b64encode(
            json.dumps(answer, separators=(",", ":")).encode()
        ).decode()

        url = f"{SEAT_BASE}/cap/checkCaptcha"
        params = {
            "a": encoded,
            "token": captcha_token,
            "userId": str(self.bot.user_id),
            "username": self.bot.username,
        }
        headers = {
            "Authorization": self.bot.token,
            "Referer": f"{SEAT_BASE}/libseat/",
            "loginType": "PC",
            **make_hmac_headers("GET"),
        }
        resp = self.bot.session.get(url, params=params, headers=headers)
        return resp.json()

    # ===== 模板匹配 =====

    @staticmethod
    def _preprocess(img, method):
        """预处理：灰度 / 自适应二值 / Canny边缘"""
        if len(img.shape) == 3:
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        else:
            gray = img.copy()
        if method == "gray":
            return gray
        elif method == "binary":
            return cv2.adaptiveThreshold(
                gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 15, 4
            )
        elif method == "edge":
            return cv2.Canny(gray, 40, 120)
        return gray

    @classmethod
    def template_match(cls, big_img_bytes, small_img_bytes):
        """多通道模板匹配。返回 (x, y) 最优候选坐标，或 (None, 0)"""
        big = cv2.imdecode(np.frombuffer(big_img_bytes, np.uint8), 1)
        small = cv2.imdecode(np.frombuffer(small_img_bytes, np.uint8), 1)
        bh, bw = big.shape[:2]

        preprocess_methods = ["gray", "binary", "edge"]
        match_methods = {
            "ccoeff": cv2.TM_CCOEFF_NORMED,
            "ccorr": cv2.TM_CCORR_NORMED,
        }
        scales = [0.6, 0.7, 0.8, 0.9, 1.0, 1.1, 1.2, 1.3, 1.5, 1.8, 2.2]

        candidates = []
        for pp_name in preprocess_methods:
            big_p = cls._preprocess(big, pp_name)
            small_p = cls._preprocess(small, pp_name)
            sh, sw = small_p.shape[:2]

            for scale in scales:
                w, h = int(sw * scale), int(sh * scale)
                if w < 5 or h < 5 or w > bw or h > bh:
                    continue
                resized = cv2.resize(small_p, (w, h))
                for m_name, m_val in match_methods.items():
                    result = cv2.matchTemplate(big_p, resized, m_val)
                    _, max_val, _, max_loc = cv2.minMaxLoc(result)
                    cx = max_loc[0] + w // 2
                    cy = max_loc[1] + h // 2
                    candidates.append(
                        (cx, cy, max_val, f"{pp_name}+{m_name}+x{scale:.1f}")
                    )

        if not candidates:
            return None, 0

        candidates.sort(key=lambda c: -c[2])
        best_cx, best_cy, best_score, best_desc = candidates[0]
        print(
            f"    最优候选: ({best_cx}, {best_cy}) "
            f"conf={best_score:.3f} [{best_desc}]"
        )
        return (best_cx, best_cy), best_score

    # ===== 求解编排 =====

    def solve(self, headless=False):
        """多策略求解验证码，返回 dict 或 None"""
        print("\n[*] 尝试自动求解验证码...")

        # 方案1: 文字验证码 OCR
        result = self._try_text_captcha()
        if result:
            return result

        # 方案2: 点击验证码 模板匹配（最多3次不同验证码）
        result = self._try_template_match()
        if result:
            return result

        # 方案2.5: AI 视觉
        result = self._try_ai_vision()
        if result:
            return result

        # 方案3: 手动点击（无头模式跳过）
        if headless:
            print("\n[*] 方案3: 手动点击（跳过，无头模式）")
            return None

        result = self._try_manual_click()
        if result:
            return result

        return None

    def _try_text_captcha(self):
        """方案1: 文字验证码 + ddddocr"""
        print("[*] 方案1: 获取文字验证码...")
        text_cap = self.get_text_captcha()
        captcha_img = text_cap.get("captchaImage")
        captcha_id = text_cap.get("captchaId")

        if not captcha_id or not captcha_img:
            print("[*] 文字验证码不可用")
            return None

        answer = self._ocr_text_captcha(captcha_img)
        if not answer or len(answer) < 2:
            print(f"[!] OCR 识别失败: '{answer}'")
            return None

        print(f"[+] OCR 识别文字验证码: {answer}")
        check_res = self.check_captcha(captcha_id, answer)
        print(f"[*] 验证结果: {check_res}")

        if check_res.get("status") == "OK":
            print("[+] 文字验证码自动通过！")
            self.bot._captcha_solved = True
            self.bot._captcha_authid = captcha_id
            return {"token": captcha_id, "authid": captcha_id}

        print(f"[!] 文字验证码失败: {check_res.get('message', '')}")
        return None

    def _try_template_match(self):
        """方案2: 点击验证码 + 模板匹配，每次只提最优候选"""
        for retry in range(TEMPLATE_MATCH_MAX_RETRIES):
            print(f"\n[*] 方案2: 获取点击验证码 (第{retry+1}次)...")
            challenge = self.get_click_captcha()
            if challenge.get("status") != "OK":
                print(f"[!] 点击验证码不可用: {json.dumps(challenge, ensure_ascii=False)[:200]}")
                break

            captcha_token = challenge.get("token")
            if not captcha_token:
                break

            big_bytes, small_bytes = self._decode_captcha_images(challenge)
            if not big_bytes or not small_bytes:
                print("[!] 图片解码失败")
                break

            try:
                best_pos, best_score = self.template_match(big_bytes, small_bytes)
            except Exception as e:
                print(f"[!] 模板匹配异常: {e}")
                continue

            if best_pos is None:
                print("[!] 匹配失败，换验证码重试...")
                continue

            cx, cy = best_pos
            check_res = self.check_captcha(captcha_token, [{"x": cx, "y": cy}])
            print(f"    验证结果: {check_res}")

            if check_res.get("status") == "OK":
                print(f"[+] 点击验证码自动通过！坐标=({cx},{cy})")
                self.bot._captcha_solved = True
                self.bot._captcha_authid = captcha_token
                return {"token": captcha_token, "authid": captcha_token}
            elif check_res.get("code") == "12":
                print("[!] Token 过期")
                break
            else:
                msg = check_res.get("message", "")
                print(f"[!] 验证失败: {msg}，换新验证码重试...")

        return None

    def _try_ai_vision(self):
        """方案2.5: AI 视觉求解"""
        try:
            from ..vision_solver import VisionCaptchaSolver

            ai = VisionCaptchaSolver()
            if not ai.is_configured():
                print("\n[*] 方案2.5: AI 视觉求解（跳过，未配置 API Key）")
                return None

            print("\n[*] 方案2.5: AI 视觉求解...")
            challenge = self.get_click_captcha()
            if challenge.get("status") != "OK":
                return None

            captcha_token = challenge.get("token")
            if not captcha_token:
                return None

            big_bytes, small_bytes = self._decode_captcha_images(challenge)
            if not big_bytes or not small_bytes:
                return None

            wcc = challenge.get("wordCheckCount", 1)
            coords = ai.solve(big_bytes, small_bytes, wcc)
            if not coords:
                print("[!] AI 未能识别目标位置")
                return None

            # 所有坐标合并一次提交
            answer = [{"x": cx, "y": cy} for cx, cy in coords]
            check_res = self.check_captcha(captcha_token, answer)
            print(f"    AI坐标: {coords} → {check_res}")

            if check_res.get("status") == "OK":
                print("[+] AI 视觉验证通过！")
                self.bot._captcha_solved = True
                self.bot._captcha_authid = captcha_token
                return {"token": captcha_token, "authid": captcha_token}
        except ImportError:
            print("\n[*] 方案2.5: AI 视觉求解（vision_solver 模块未找到）")
        except Exception as e:
            print(f"\n[!] AI 视觉求解异常: {e}")

        return None

    def _try_manual_click(self):
        """方案3: 弹出窗口手动点击"""
        print("\n[*] 方案3: 获取新验证码，弹出窗口让您手动点击...")
        challenge = self.get_click_captcha()
        if challenge.get("status") != "OK":
            print(f"[!] 无法获取验证码: {json.dumps(challenge, ensure_ascii=False)[:200]}")
            return None

        captcha_token = challenge.get("token")
        if not captcha_token:
            return None

        big_bytes, small_bytes = self._decode_captcha_images(challenge)
        if not big_bytes or not small_bytes:
            return None

        x, y = self._interactive_click(big_bytes, small_bytes)
        if x is not None and y is not None:
            check_res = self.check_captcha(captcha_token, [{"x": x, "y": y}])
            print(f"[*] 验证结果: {check_res}")
            if check_res.get("status") == "OK":
                print("[+] 手动点击验证通过！")
                self.bot._captcha_solved = True
                self.bot._captcha_authid = captcha_token
                return {"token": captcha_token, "authid": captcha_token}

        return None

    @staticmethod
    def _interactive_click(big_img_bytes, small_img_bytes):
        """弹出 cv2 窗口，用户双击目标文字"""
        big = cv2.imdecode(np.frombuffer(big_img_bytes, np.uint8), 1)
        small = cv2.imdecode(np.frombuffer(small_img_bytes, np.uint8), 1)

        sw, sh = small.shape[1], small.shape[0]
        ref_h = max(sh + 20, 60)
        display = np.ones(
            (ref_h + big.shape[0], big.shape[1], 3), dtype=np.uint8
        ) * 240
        sx = (big.shape[1] - sw) // 2
        display[10 : 10 + sh, sx : sx + sw] = small
        cv2.putText(
            display,
            "TARGET - 看这里，然后在下面大图中双击目标字",
            (5, 5 if sh < 20 else sh + 19),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.4,
            (0, 0, 255),
            1,
        )
        display[ref_h:, :] = big

        result = {"x": None, "y": None}

        def on_mouse(event, x, y, flags, param):
            if event == cv2.EVENT_LBUTTONDBLCLK and y >= ref_h:
                result["x"] = x
                result["y"] = y - ref_h
                cv2.line(display, (x - 20, y), (x + 20, y), (0, 0, 255), 3)
                cv2.line(display, (x, y - 20), (x, y + 20), (0, 0, 255), 3)
                cv2.imshow("CAPTCHA", display)

        win_name = "CAPTCHA - 双击目标文字"
        cv2.imshow(win_name, display)
        cv2.setMouseCallback(win_name, on_mouse)

        print("    >>> 请在弹出的图片窗口中双击目标文字位置")
        print("    >>> 顶部小图 = 要点击的目标，下面大图 = 点击区域")

        while result["x"] is None:
            key = cv2.waitKey(100) & 0xFF
            if key == 27:  # ESC
                break
            try:
                if cv2.getWindowProperty(win_name, cv2.WND_PROP_VISIBLE) < 1:
                    break
            except:
                break

        cv2.destroyAllWindows()
        cv2.waitKey(1)

        if result["x"] is not None:
            print(f"    >>> 用户点击坐标: ({result['x']}, {result['y']})")
            return result["x"], result["y"]
        return None, None
