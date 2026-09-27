"""
图书馆座位自动预约系统
支持：SSO 登录 + 验证码 OCR + HMAC 签名 + 座位查询 + 预约
"""
import requests
import base64
import re
import time
import json
import uuid
import hmac
import hashlib
from datetime import date as dt_date, timedelta
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad
from bs4 import BeautifulSoup
import ddddocr


HMAC_SECRET = "wowmom22bbaa"  # AES-CBC 解密 NUMCODE 得到

# ==================== 加密工具 ====================

def aes_ecb_encrypt(key_b64, plaintext):
    """AES-128-ECB PKCS7 → base64（SSO 登录用）"""
    key = base64.b64decode(key_b64)
    cipher = AES.new(key, AES.MODE_ECB)
    padded = pad(plaintext.encode("utf-8"), 16)
    return base64.b64encode(cipher.encrypt(padded)).decode()

def aes_cbc_decrypt(ciphertext_b64):
    """AES-CBC PKCS7 解密（解密 NUMCODE 等）key=server_date_time, iv=client_date_time"""
    key = b"server_date_time"
    iv = b"client_date_time"
    ciphertext = base64.b64decode(ciphertext_b64)
    cipher = AES.new(key, AES.MODE_CBC, iv)
    return unpad(cipher.decrypt(ciphertext), 16).decode("utf-8")

def make_hmac_headers(method):
    """生成 HMAC 签名请求头"""
    req_id = str(uuid.uuid4())
    req_date = str(int(time.time() * 1000))
    message = f"seat::{req_id}::{req_date}::{method.upper()}"
    sig = hmac.new(HMAC_SECRET.encode(), message.encode(), hashlib.sha256).hexdigest()
    return {
        "X-request-id": req_id,
        "X-request-date": req_date,
        "X-hmac-request-key": sig,
    }

# ==================== 主类 ====================

class LibSeatBot:
    def __init__(self, username, password):
        self.username = username
        self.password = password
        self.session = requests.Session()
        self.session.headers["User-Agent"] = (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36 Edg/148.0.0.0"
        )
        self.ocr = ddddocr.DdddOcr()
        self.sso_base = "https://sso.axhu.edu.cn"
        self.seat_base = "https://seat.axhu.edu.cn"
        self.token = None
        self.user_id = None

    # ==================== SSO 登录 ====================

    def login(self):
        """完整登录流程：图书馆 SSO 入口 → SSO → CAS ticket → 图书馆 token"""
        print("\n[*] 第一步：通过图书馆 SSO 入口跳转到 SSO...")

        # 访问图书馆 SSO 入口，跟随重定向到 SSO 登录页（关键：设置 redirect 目标 cookie）
        lib_sso_entry = (
            f"{self.seat_base}/remote/static/sso/login"
            f"?redirectUrl=https://seat.axhu.edu.cn/libseat/#/login"
        )
        resp = self.session.get(lib_sso_entry, allow_redirects=True)
        login_page_url = resp.url
        print(f"[*] 当前 URL: {login_page_url[:120]}...")

        # 获取登录页，提取参数
        resp = self.session.get(login_page_url)
        resp.encoding = "utf-8"
        soup = BeautifulSoup(resp.text, "html.parser")

        croypto_el = soup.find("p", id="login-croypto")
        flowkey_el = soup.find("p", id="login-page-flowkey")

        if not croypto_el or not flowkey_el:
            print("[!] 无法提取登录参数")
            return False

        croypto_key = croypto_el.text.strip()
        execution = flowkey_el.text.strip()
        print(f"[+] 加密密钥: {croypto_key[:30]}...")
        print(f"[+] execution: {execution[:60]}...")

        # 获取验证码
        captcha_url = f"{self.sso_base}/api/captcha/generate/DEFAULT"
        captcha_resp = self.session.get(captcha_url)
        captcha_code = self.ocr.classification(captcha_resp.content).strip()
        print(f"[+] 验证码 OCR: {captcha_code}")

        if len(captcha_code) < 3:
            captcha_resp = self.session.get(captcha_url)
            captcha_code = self.ocr.classification(captcha_resp.content).strip()
            print(f"[+] 重试 OCR: {captcha_code}")

        # 加密
        encrypted_pw = aes_ecb_encrypt(croypto_key, self.password)
        encrypted_captcha = aes_ecb_encrypt(croypto_key, "{}")

        # 提交登录
        login_resp = self.session.post(
            f"{self.sso_base}/login",
            data={
                "username": self.username,
                "type": "UsernamePassword",
                "_eventId": "submit",
                "geolocation": "",
                "execution": execution,
                "captcha_code": captcha_code,
                "croypto": croypto_key,
                "password": encrypted_pw,
                "captcha_payload": encrypted_captcha,
            },
            headers={
                "Origin": self.sso_base,
                "Referer": login_page_url,
                "Content-Type": "application/x-www-form-urlencoded",
            },
            allow_redirects=False,
        )

        print(f"[*] SSO 响应: {login_resp.status_code}")

        # 重试验证码（状态码 200 表示验证码错误返回了页面，非 302 重定向）
        location = login_resp.headers.get("Location", "")
        is_redirect = login_resp.status_code in (301, 302, 303, 307, 308)
        needs_retry = not is_redirect or "error" in location or ("login" in location and "ticket" not in location)

        retry_count = 0
        while needs_retry and retry_count < 5:
            retry_count += 1
            print(f"[!] 验证码错误，重试 ({retry_count}/5)...")
            captcha_resp2 = self.session.get(captcha_url)
            captcha_code2 = self.ocr.classification(captcha_resp2.content).strip()
            print(f"[+] OCR ({retry_count}): {captcha_code2}")

            login_resp = self.session.post(
                f"{self.sso_base}/login",
                data={
                    "username": self.username,
                    "type": "UsernamePassword",
                    "_eventId": "submit",
                    "geolocation": "",
                    "execution": execution,
                    "captcha_code": captcha_code2,
                    "croypto": croypto_key,
                    "password": encrypted_pw,
                    "captcha_payload": aes_ecb_encrypt(croypto_key, "{}"),
                },
                headers={
                    "Origin": self.sso_base,
                    "Referer": login_page_url,
                    "Content-Type": "application/x-www-form-urlencoded",
                },
                allow_redirects=False,
            )
            print(f"[*] SSO 响应 ({retry_count}): {login_resp.status_code}")
            location = login_resp.headers.get("Location", "")
            is_redirect = login_resp.status_code in (301, 302, 303, 307, 308)
            needs_retry = not is_redirect or "error" in location or ("login" in location and "ticket" not in location)

        # 跟随 CAS 重定向
        if login_resp.status_code in (301, 302, 303, 307, 308):
            print(f"[*] CAS 重定向: {location[:120]}...")

            # 只跟随一步，拿到 CAS 验证后的重定向
            # 第一步：SSO → CAS 验证端点，拿到 ticket 或 ticketCode
            cas_resp = self.session.get(location, allow_redirects=False)
            cas_location = cas_resp.headers.get("Location", "")

            print(f"[*] CAS 验证响应: {cas_resp.status_code}")
            if cas_location:
                print(f"[*] CAS 重定向: {cas_location[:120]}...")

            # 如果有二次重定向（CAS 验证页 302 → 图书馆首页）
            if cas_resp.status_code in (301, 302, 303, 307, 308) and cas_location:
                final_resp = self.session.get(cas_location, allow_redirects=True)
            else:
                final_resp = cas_resp

            print(f"[*] 最终 URL: {final_resp.url[:150]}...")

            # 尝试提取 token
            auth_token = None
            final_url = final_resp.url

            # 方式1: URL 参数 token=xxx (最高优先级，JWT 格式)
            token_match = re.search(r"[?&#]token=([^&\s#]+)", final_url)
            if token_match:
                val = token_match.group(1)
                # JWT — 走 ssoAuth 验证
                if val.startswith("eyJ") or len(val) > 80:
                    auth_token = val
                    print(f"[+] 从 URL 提取到 JWT: {auth_token[:50]}...")

            # 方式2: ticketCode
            if not auth_token:
                tc_match = re.search(r"ticketCode=([^&\s]+)", final_url)
                if tc_match:
                    auth_token = tc_match.group(1)

            # 方式3: CAS ticket（fallback）
            if not auth_token:
                ticket_match = re.search(r"[?&]ticket=(ST-[^&\s]+)", location)
                if ticket_match:
                    auth_token = ticket_match.group(1)

            if auth_token:
                return self._sso_auth(auth_token)

        print("[!] SSO 登录失败")
        return False

    def _sso_auth(self, cas_ticket):
        """用 CAS ticket 换取图书馆 session token"""
        print("\n[*] 第二步：ssoAuth 换取 token...")
        resp = self.session.post(
            f"{self.seat_base}/rest/ssoAuth?token={cas_ticket}",
            json={},
            headers={
                "Referer": f"{self.seat_base}/libseat/",
                "Content-Type": "application/json",
                "loginType": "PC",
                **make_hmac_headers("POST"),
            },
        )
        data = resp.json()
        print(f"[*] ssoAuth 响应: {json.dumps(data, ensure_ascii=False)}")

        if data.get("status") == "success" and data.get("data", {}).get("token"):
            self.token = data["data"]["token"]
            print(f"[+] session token: {self.token[:40]}...")
            return True
        else:
            print(f"[!] ssoAuth 失败")
            return False

    # ==================== API 请求 ====================

    def _api_get(self, path, params=None):
        """带 HMAC 签名的 GET 请求"""
        url = f"{self.seat_base}{path}"
        if params is None:
            params = {}
        params["token"] = self.token
        headers = {
            "Authorization": self.token,
            "Referer": f"{self.seat_base}/libseat/",
            "loginType": "PC",
            **make_hmac_headers("GET"),
        }
        resp = self.session.get(url, params=params, headers=headers)
        result = resp.json()
        if result.get("status") != "success":
            print(f"[!] API 失败 [{path}]: code={result.get('code')}, msg={result.get('message')}")
            print(f"    sent headers: X-request-id={headers.get('X-request-id')}")
        return result

    def _api_post(self, path, body=None, params=None):
        """带 HMAC 签名的 POST 请求"""
        url = f"{self.seat_base}{path}"
        if params is None:
            params = {}
        params["token"] = self.token
        headers = {
            "Authorization": self.token,
            "Referer": f"{self.seat_base}/libseat/",
            "loginType": "PC",
            "Content-Type": "application/json",
            **make_hmac_headers("POST"),
        }
        resp = self.session.post(url, json=body or {}, params=params, headers=headers)
        return resp.json()

    # ==================== 座位查询 ====================

    def get_building_stats(self, building_id=1, date_str=None):
        """获取建筑/楼层统计，返回可用的房间列表"""
        if date_str is None:
            date_str = dt_date.today().strftime("%Y-%m-%d")
        result = self._api_get(
            f"/rest/v2/room/stats2/{building_id}/{date_str}",
            {"buildingId": building_id, "date": date_str},
        )
        return result

    def get_floors(self, building_id=1):
        """获取楼层信息"""
        return self._api_post(
            f"/rest/v2/room/floors/{building_id}",
            body={},
        )

    def get_room_layout(self, room_id, date_str=None):
        """获取房间座位布局"""
        if date_str is None:
            date_str = dt_date.today().strftime("%Y-%m-%d")
        return self._api_get(
            f"/rest/v2/room/layoutByDate/{room_id}/{date_str}",
            {"id": room_id, "date": date_str},
        )

    def get_user_info(self):
        """获取用户信息（得到 userId 用于 freeBook）"""
        result = self._api_get("/rest/v2/user")
        if result.get("status") == "success":
            self.user_id = result["data"]["id"]
            print(f"[+] userId: {self.user_id}")
        return result

    def get_start_times(self, seat_id, date_str=None):
        """获取座位可用开始时间列表（返回 data.startTimes 列表）"""
        if date_str is None:
            date_str = dt_date.today().strftime("%Y-%m-%d")
        return self._api_get(
            f"/rest/v2/startTimesForSeat/{seat_id}/{date_str}",
            {"seatId": seat_id, "date": date_str},
        )

    def get_end_times(self, seat_id, date_str, start_minutes):
        """获取指定开始时间后的可用结束时间（start 可以是 'now' 或分钟数）"""
        start_str = str(start_minutes) if start_minutes != "now" else "now"
        return self._api_get(
            f"/rest/v2/endTimesForSeat/{seat_id}/{date_str}/{start_str}",
            {"id": seat_id, "date": date_str, "start": start_str},
        )

    def find_available_seats(self, room_id, date_str=None):
        """查找房间内所有空闲座位（修复：解析 data.layout 字典）"""
        if date_str is None:
            date_str = dt_date.today().strftime("%Y-%m-%d")

        layout = self.get_room_layout(room_id, date_str)
        seats = []
        stats = {}

        if layout.get("status") == "success":
            data = layout.get("data", {})
            room_name = data.get("name", "")
            layout_map = data.get("layout", {}) if isinstance(data, dict) else {}
            print(f"[*] 房间: {room_name}, layout 条目数: {len(layout_map)}")

            for pos_key, item in layout_map.items():
                if isinstance(item, dict) and item.get("type") == "seat":
                    s = item.get("status", "?")
                    stats[s] = stats.get(s, 0) + 1
                    if s == "FREE" and item.get("enabled", True):
                        seats.append({
                            "seat_id": item.get("id"),
                            "name": item.get("name"),
                            "area": room_name,
                        })
            print(f"[*] 座位状态统计: {stats}")
        else:
            print(f"[!] layout 查询失败: {json.dumps(layout, ensure_ascii=False)[:500]}")

        return seats

    def get_current_reservation(self):
        """获取当前预约"""
        return self._api_get("/rest/v2/user/reservations")

    # ==================== 预约 ====================

    def free_book(self, seat_id, date_str, start_minutes, end_minutes):
        """预约座位（freeBook）— 使用 multipart/form-data 格式"""
        url = f"{self.seat_base}/rest/v2/freeBook"
        data = {
            "startTime": str(start_minutes),
            "endTime": str(end_minutes),
            "seat": str(seat_id),
            "date": date_str,
            "userId": str(self.user_id) if self.user_id else "",
            "username": self.username,
        }
        # 如果有验证码 authid，加入请求
        if getattr(self, '_captcha_authid', None):
            data["authid"] = self._captcha_authid

        headers = {
            "Authorization": self.token,
            "Referer": f"{self.seat_base}/libseat/",
            "loginType": "PC",
            **make_hmac_headers("POST"),
        }
        params = {"token": self.token}
        resp = self.session.post(url, data=data, params=params, headers=headers)
        return resp.json()

    # ==================== 行为验证码 ====================

    def get_text_captcha(self):
        """获取文字验证码（GET /auth/createCaptcha）— 简单 OCR 类型
        注意：不能走 _api_get，因为返回格式不是 {status:success}"""
        url = f"{self.seat_base}/auth/createCaptcha"
        headers = {
            "Authorization": self.token,
            "Referer": f"{self.seat_base}/libseat/",
            "loginType": "PC",
            **make_hmac_headers("GET"),
        }
        resp = self.session.get(url, headers=headers)
        return resp.json()

    def get_click_captcha(self):
        """获取点击行为验证码（POST /cap/captcha/{token}?username=xxx）
        返回: {image, wordImage, wordCheckCount, token, status}"""
        url = f"{self.seat_base}/cap/captcha/{self.token}"
        params = {"username": self.username}
        headers = {
            "Authorization": self.token,
            "Referer": f"{self.seat_base}/libseat/",
            "loginType": "PC",
            **make_hmac_headers("POST"),
        }
        resp = self.session.post(url, params=params, headers=headers)
        return resp.json()

    def check_captcha(self, captcha_token, answer):
        """
        提交验证码答案（不能用 _api_get，因为 token 参数会被覆写）
        answer: 字符串（文字验证码）或 [{x, y}] 列表（点击验证码）
               如果是字符串，自动包装为 [answer]
        """
        import base64 as b64
        # 字符串自动包装为数组
        if isinstance(answer, str):
            answer = [answer]
        encoded = b64.b64encode(json.dumps(answer).encode()).decode()
        url = f"{self.seat_base}/cap/checkCaptcha"
        params = {
            "a": encoded,
            "token": captcha_token,  # captcha token，不是 session token！
            "userId": str(self.user_id),
            "username": self.username,
        }
        headers = {
            "Authorization": self.token,
            "Referer": f"{self.seat_base}/libseat/",
            "loginType": "PC",
            **make_hmac_headers("GET"),
        }
        resp = self.session.get(url, params=params, headers=headers)
        return resp.json()

    def _ocr_image_from_data_uri(self, data_uri):
        """从 data URI 中用 ddddocr 识别文字"""
        import base64 as b64
        if not data_uri or not data_uri.startswith("data:image/"):
            return None
        b64_data = data_uri.split(",", 1)[-1]
        img_bytes = b64.b64decode(b64_data)
        return self.ocr.classification(img_bytes).strip()

    def _interactive_click(self, big_img_bytes, small_img_bytes, captcha_token):
        """
        弹出图片窗口让用户点击目标位置，自动返回坐标
        显示目标小图作为参考，用户在大图上双击目标位置
        """
        import cv2, numpy as np
        big = cv2.imdecode(np.frombuffer(big_img_bytes, np.uint8), 1)
        small = cv2.imdecode(np.frombuffer(small_img_bytes, np.uint8), 1)

        # 在 big 图上方拼接 small 图作为参考
        sw, sh = small.shape[1], small.shape[0]
        ref_h = max(sh + 20, 60)
        display = np.ones((ref_h + big.shape[0], big.shape[1], 3), dtype=np.uint8) * 240
        # 把 small 参考图放在顶部居中
        sx = (big.shape[1] - sw) // 2
        display[10:10+sh, sx:sx+sw] = small
        # 参考文字
        cv2.putText(display, "TARGET - look at this, then double-click it in the image below",
                    (5, 5 if sh < 20 else sh + 19), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 0, 255), 1)
        # 下面放 big 图
        display[ref_h:, :] = big

        result = {"x": None, "y": None}

        def on_mouse(event, x, y, flags, param):
            if event == cv2.EVENT_LBUTTONDBLCLK and y >= ref_h:
                # 转换为 big 图坐标
                result["x"] = x
                result["y"] = y - ref_h
                # 画十字标记
                cv2.line(display, (x-20, y), (x+20, y), (0, 0, 255), 3)
                cv2.line(display, (x, y-20), (x, y+20), (0, 0, 255), 3)
                cv2.imshow("CAPTCHA - double-click to submit", display)

        cv2.imshow("CAPTCHA - double-click to submit", display)
        cv2.setMouseCallback("CAPTCHA - double-click to submit", on_mouse)

        print("    >>> 请在弹出的图片窗口中双击目标文字位置")
        print("    >>> 顶部小图 = 要点击的目标，下面大图 = 点击区域")

        while result["x"] is None:
            key = cv2.waitKey(100) & 0xFF
            if key == 27:  # ESC
                break

        cv2.destroyAllWindows()
        cv2.waitKey(1)  # 确保窗口关闭

        if result["x"] is not None:
            print(f"    >>> 用户点击坐标: ({result['x']}, {result['y']})")
            return result["x"], result["y"]
        return None, None

    def solve_behavioral_captcha(self):
        """
        自动求解验证码：
        方案1: 文字验证码 OCR → 方案2: 点击验证码模板匹配 → 方案3: 弹出窗口让用户点击
        返回: {"token": captcha_token} 或 None
        """
        print("\n[*] 尝试自动求解验证码...")

        # === 方案1: 文字验证码 (GET /auth/createCaptcha) ===
        print("[*] 方案1: 获取文字验证码...")
        text_cap = self.get_text_captcha()
        captcha_img = text_cap.get("captchaImage")
        captcha_id = text_cap.get("captchaId")
        if captcha_id and captcha_img:
            print(f"[+] captchaId: {captcha_id}")
            answer = self._ocr_image_from_data_uri(captcha_img)
            if answer and len(answer) >= 2:
                print(f"[+] OCR 识别文字验证码: {answer}")
                check_res = self.check_captcha(captcha_id, answer)
                print(f"[*] 验证结果: {check_res}")
                if check_res.get("status") == "OK":
                    print("[+] 文字验证码自动通过！")
                    self._captcha_solved = True
                    self._captcha_authid = captcha_id
                    return {"token": captcha_id, "authid": captcha_id}
                else:
                    print(f"[!] 文字验证码失败: {check_res.get('message', '')}")
            else:
                print(f"[!] OCR 识别失败: '{answer}'")
        else:
            print(f"[*] 文字验证码不可用: {json.dumps(text_cap, ensure_ascii=False)[:200]}")

        # === 方案2: 点击验证码 + cv2 模板匹配 ===
        print("[*] 方案2: 获取点击验证码...")
        challenge = self.get_click_captcha()
        if challenge.get("status") != "OK":
            print(f"[!] 点击验证码不可用: {json.dumps(challenge, ensure_ascii=False)[:200]}")
            return None

        captcha_token = challenge.get("token")
        if not captcha_token:
            return None

        print(f"[+] captcha token: {captcha_token[:20]}...")
        print(f"[*] wordCheckCount: {challenge.get('wordCheckCount')}")

        # 解码图片
        import base64 as b64
        big_img_bytes = None
        small_img_bytes = None
        for key in ["image", "wordImage"]:
            data_uri = challenge.get(key, "")
            if data_uri and data_uri.startswith("data:image/"):
                b64_data = data_uri.split(",", 1)[-1]
                img_bytes = b64.b64decode(b64_data)
                if key == "image":
                    big_img_bytes = img_bytes
                else:
                    small_img_bytes = img_bytes

        # 尝试 cv2 模板匹配
        auto_solved = False
        if big_img_bytes and small_img_bytes:
            try:
                import cv2, numpy as np
                big = cv2.imdecode(np.frombuffer(big_img_bytes, np.uint8), 1)
                small = cv2.imdecode(np.frombuffer(small_img_bytes, np.uint8), 1)
                best_score, best_pos = 0, None
                for scale in [0.5, 0.6, 0.7, 0.8, 0.9, 1.0, 1.1, 1.2, 1.3, 1.5, 2.0]:
                    w = int(small.shape[1] * scale)
                    h = int(small.shape[0] * scale)
                    if w > big.shape[1] or h > big.shape[0]:
                        continue
                    resized = cv2.resize(small, (w, h))
                    result = cv2.matchTemplate(big, resized, cv2.TM_CCOEFF_NORMED)
                    _, max_val, _, max_loc = cv2.minMaxLoc(result)
                    if max_val > best_score:
                        best_score = max_val
                        best_pos = (max_loc[0] + w // 2, max_loc[1] + h // 2)

                if best_pos and best_score > 0.3:
                    print(f"[+] 模板匹配成功: ({best_pos[0]}, {best_pos[1]}), 置信度={best_score:.3f}")
                    check_res = self.check_captcha(captcha_token, [{"x": best_pos[0], "y": best_pos[1]}])
                    print(f"[*] 验证结果: {check_res}")
                    if check_res.get("status") == "OK":
                        print("[+] 点击验证码自动通过！")
                        auto_solved = True
                    else:
                        print(f"[!] 自动验证失败: {check_res.get('message', '')}")
                else:
                    print(f"[!] 模板匹配置信度过低 ({best_score:.3f})")
            except Exception as e:
                print(f"[!] 模板匹配异常: {e}")

        # === 方案3: 弹出窗口让用户点击 ===
        if not auto_solved and big_img_bytes and small_img_bytes:
            print("\n[*] 方案3: 弹出图片窗口，请手动点击...")
            x, y = self._interactive_click(big_img_bytes, small_img_bytes, captcha_token)
            if x is not None and y is not None:
                check_res = self.check_captcha(captcha_token, [{"x": x, "y": y}])
                print(f"[*] 验证结果: {check_res}")
                if check_res.get("status") == "OK":
                    print("[+] 手动点击验证通过！")
                    auto_solved = True

        if auto_solved:
            self._captcha_solved = True
            self._captcha_authid = captcha_token
            return {"token": captcha_token, "authid": captcha_token}

        return {"token": captcha_token}

    def cancel(self, reservation_id):
        """取消预约"""
        return self._api_get(
            f"/rest/v2/cancel/{reservation_id}",
            {"id": reservation_id},
        )

    # ==================== 高级方法 ====================

    def smart_book(self, room_id, date_str=None, min_start=480, max_end=1260):
        """
        智能预约：在指定房间找第一个可用座位并预约最长时段
        min_start=480 (8:00), max_end=1260 (21:00)
        """
        if date_str is None:
            date_str = dt_date.today().strftime("%Y-%m-%d")

        print(f"\n[*] 查找 {date_str} 房间 {room_id} 的可用座位...")
        seats = self.find_available_seats(room_id, date_str)
        print(f"[+] 找到 {len(seats)} 个空闲座位")

        for seat in seats:
            seat_id = seat["seat_id"]
            print(f"\n[*] 尝试: {seat['area']} {seat['name']} (ID:{seat_id})")

            start_times = self.get_start_times(seat_id, date_str)
            if start_times.get("status") != "success":
                print(f"   获取开始时间失败: {start_times}")
                continue

            available_starts = start_times.get("data", {}).get("startTimes", [])
            if not available_starts:
                print("   无可用开始时间")
                continue

            # 选最早的开始时间（不早于 min_start，跳过 "now"）
            best_start = None
            for t in available_starts:
                tid = t.get("id", "0") if isinstance(t, dict) else str(t)
                if tid == "now":
                    continue
                t_min = int(tid)
                if t_min >= min_start:
                    best_start = t_min
                    break

            if best_start is None:
                print("   没有符合开始时间的选项")
                continue

            end_times = self.get_end_times(seat_id, date_str, best_start)
            if end_times.get("status") != "success":
                print(f"   获取结束时间失败: {end_times}")
                continue

            available_ends = end_times.get("data", {}).get("endTimes", [])
            if not available_ends:
                print("   无可用结束时间")
                continue

            # 选最晚的结束时间（不晚于 max_end）
            best_end = None
            for t in reversed(available_ends):
                tid = t.get("id", "0") if isinstance(t, dict) else str(t)
                t_min = int(tid)
                if t_min <= max_end:
                    best_end = t_min
                    break

            if best_end is None:
                print("   没有符合结束时间的选项")
                continue

            print(f"   预约: {self._min_to_time(best_start)} - {self._min_to_time(best_end)}")

            # 解验证码（只需解一次）
            if not getattr(self, '_captcha_solved', False):
                captcha_result = self.solve_behavioral_captcha()
                if not captcha_result or not getattr(self, '_captcha_solved', False):
                    print("   [!] 验证码未解决，跳过此座位")
                    continue

            result = self.free_book(seat_id, date_str, best_start, best_end)
            if result.get("status") == "success":
                print(f"[+] 预约成功！座位 {seat['name']}")
                return True, seat, best_start, best_end
            elif result.get("code") == "12":
                print(f"   [!] Token 已失效，无法继续")
                return False, None, None, None
            else:
                msg = result.get('message', str(result))
                print(f"   失败: {msg}")

        print("\n[!] 所有座位均无法预约")
        return False, None, None, None

    @staticmethod
    def _min_to_time(minutes):
        return f"{minutes // 60:02d}:{minutes % 60:02d}"


# ==================== 主入口 ====================

def main():
    print("=" * 50)
    print("  图书馆座位自动预约系统 v1.0")
    print("=" * 50)

    username = input("学号: ").strip()
    password = input("密码: ").strip()
    room_id = input("房间 ID [默认 1]: ").strip() or "1"
    date_str = input(f"日期 [默认明天 {(dt_date.today() + timedelta(days=1)).strftime('%Y-%m-%d')}]: ").strip()
    if not date_str:
        date_str = (dt_date.today() + timedelta(days=1)).strftime("%Y-%m-%d")

    bot = LibSeatBot(username, password)

    if not bot.login():
        print("\n[!] 登录失败，请检查账号密码")
        return

    print("\n[+] 登录成功！")

    # 获取用户信息（userId 在 freeBook 时需要）
    print("\n[*] 获取用户信息...")
    bot.get_user_info()

    # 先列出可用楼层/房间
    print("\n[*] 查询建筑信息...")
    stats = bot.get_building_stats(1, date_str)
    print(f"[*] stats 原始响应: {json.dumps(stats, ensure_ascii=False)[:800]}")

    data = stats.get("data", [])
    rooms = []  # list of {id, name, free, total}

    if isinstance(data, list):
        for item in data:
            if isinstance(item, dict):
                rid = item.get("roomId") or item.get("id") or item.get("room_id")
                rname = item.get("roomName") or item.get("room") or item.get("name") or item.get("room_name")
                free_count = item.get("freeCount") or item.get("free") or item.get("free_count", 0)
                total = item.get("totalSeats") or item.get("total") or item.get("total_seats", 0)
                if rid is not None:
                    rooms.append({"id": rid, "name": rname, "free": free_count, "total": total})
                    print(f"    房间 [{rid}] {rname}: 空闲 {free_count}/{total}")
    elif isinstance(data, dict):
        room_list = data.get("rooms") or data.get("roomList") or data.get("list") or []
        for room in room_list:
            rid = room.get("roomId") or room.get("id") or room.get("room_id")
            rname = room.get("roomName") or room.get("room") or room.get("name") or room.get("room_name")
            free_count = room.get("freeCount") or room.get("free") or room.get("free_count", 0)
            total = room.get("totalSeats") or room.get("total") or room.get("total_seats", 0)
            if rid is not None:
                rooms.append({"id": rid, "name": rname, "free": free_count, "total": total})
                print(f"    房间 [{rid}] {rname}: 空闲 {free_count}/{total}")

    if not rooms:
        print("[!] 无法解析房间数据，使用用户输入的房间 ID")
    elif room_id == "1":
        # If user just hit enter (using default), auto-pick the first room from stats
        first_room = rooms[0]
        room_id = str(first_room["id"])
        print(f"[*] 自动选择第一个房间: [{room_id}] {first_room['name']}")

    print(f"\n[*] 开始查找座位 (房间ID={room_id}, 日期={date_str})...")
    bot.smart_book(int(room_id), date_str)


if __name__ == "__main__":
    main()
