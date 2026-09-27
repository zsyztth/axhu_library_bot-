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
    def __init__(self, username, password, headless=False):
        self.username = username
        self.password = password
        self.headless = headless  # True=服务器模式，跳过 cv2 弹窗
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
            code = result.get("code", "")
            msg = result.get("message", "")
            print(f"[!] API 失败 [{path}]: code={code}, msg={msg}")
            # token 过期 → 自动重登
            if code == "12" or "登录失败" in str(msg) or "用户名或密码" in str(msg):
                print("[*] Token 已过期，尝试自动重新登录...")
                if self.login():
                    print("[+] 重登成功，重试请求...")
                    params["token"] = self.token
                    headers["Authorization"] = self.token
                    headers.update(make_hmac_headers("GET"))
                    resp = self.session.get(url, params=params, headers=headers)
                    return resp.json()
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
        encoded = b64.b64encode(json.dumps(answer, separators=(',', ':')).encode()).decode()
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
        自动求解验证码（每个 token 只能提交一次，失败需换新验证码）：
        方案1: 文字验证码 OCR → 方案2: 点击验证码模板匹配（每次只提交最优候选）
        → 方案3: 弹出窗口让用户点击（新鲜 token）
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

        # === 方案2: 点击验证码（每次只提交最优候选，失败换新 token 重试）===
        import cv2, numpy as np, base64 as b64

        def _preprocess(img, method):
            """预处理：灰度 / 二值化 / 边缘"""
            if len(img.shape) == 3:
                gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            else:
                gray = img.copy()
            if method == "gray":
                return gray
            elif method == "binary":
                return cv2.adaptiveThreshold(gray, 255,
                    cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 15, 4)
            elif method == "edge":
                return cv2.Canny(gray, 40, 120)
            return gray

        def _match_one_captcha(big_img_bytes, small_img_bytes):
            """对一组图片运行多通道模板匹配，返回最优候选坐标或 None"""
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
                big_p = _preprocess(big, pp_name)
                small_p = _preprocess(small, pp_name)
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
                        candidates.append((cx, cy, max_val,
                            f"{pp_name}+{m_name}+x{scale:.1f}"))

            if not candidates:
                return None, 0

            candidates.sort(key=lambda c: -c[2])
            best_cx, best_cy, best_score, best_desc = candidates[0]
            print(f"    最优候选: ({best_cx}, {best_cy}) conf={best_score:.3f} [{best_desc}]")
            return (best_cx, best_cy), best_score

        # 模板匹配最多重试 3 个不同的验证码
        MAX_AUTO_RETRIES = 3
        auto_solved = False
        captcha_token = None

        for retry in range(MAX_AUTO_RETRIES):
            print(f"\n[*] 方案2: 获取点击验证码 (第{retry+1}次)...")
            challenge = self.get_click_captcha()
            if challenge.get("status") != "OK":
                print(f"[!] 点击验证码不可用: {json.dumps(challenge, ensure_ascii=False)[:200]}")
                break

            captcha_token = challenge.get("token")
            if not captcha_token:
                break

            print(f"[+] captcha token: {captcha_token[:20]}...")

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

            if not big_img_bytes or not small_img_bytes:
                print("[!] 图片解码失败")
                break

            try:
                best_pos, best_score = _match_one_captcha(big_img_bytes, small_img_bytes)
            except Exception as e:
                print(f"[!] 模板匹配异常: {e}")
                continue

            if best_pos is None:
                print("[!] 匹配失败，换验证码重试...")
                continue

            # 只提交一次！提交后 token 就消耗了
            cx, cy = best_pos
            check_res = self.check_captcha(captcha_token, [{"x": cx, "y": cy}])
            print(f"    验证结果: {check_res}")

            if check_res.get("status") == "OK":
                print(f"[+] 点击验证码自动通过！坐标=({cx},{cy})")
                auto_solved = True
                break
            elif check_res.get("code") == "12":
                print("[!] Token 过期")
                break
            else:
                msg = check_res.get("message", "")
                print(f"[!] 验证失败: {msg}，换新验证码重试...")
                # 继续下一轮，获取新验证码

        if auto_solved:
            self._captcha_solved = True
            self._captcha_authid = captcha_token
            return {"token": captcha_token, "authid": captcha_token}

        # === 方案2.5: AI 视觉求解（豆包/GPT-4V 等） ===
        try:
            from vision_solver import VisionCaptchaSolver
            ai_solver = VisionCaptchaSolver()
            # 检查 API Key 是否已配置
            if ai_solver.config.get("api_key") and ai_solver.config["api_key"] != "YOUR_API_KEY_HERE":
                print("\n[*] 方案2.5: AI 视觉求解...")
                challenge = self.get_click_captcha()
                if challenge.get("status") == "OK":
                    captcha_token = challenge.get("token")
                    wcc = challenge.get("wordCheckCount", 1)
                    if captcha_token:
                        # 解码图片
                        big_bytes, small_bytes = None, None
                        for key in ["image", "wordImage"]:
                            data_uri = challenge.get(key, "")
                            if data_uri and data_uri.startswith("data:image/"):
                                b64_data = data_uri.split(",", 1)[-1]
                                img_bytes = b64.b64decode(b64_data)
                                if key == "image":
                                    big_bytes = img_bytes
                                else:
                                    small_bytes = img_bytes

                        if big_bytes and small_bytes:
                            coords = ai_solver.solve(big_bytes, small_bytes, wcc)
                            if coords:
                                # 所有坐标合并为一次提交
                                answer = [{"x": cx, "y": cy} for cx, cy in coords]
                                check_res = self.check_captcha(captcha_token, answer)
                                print(f"    AI坐标: {coords} → {check_res}")
                                if check_res.get("status") == "OK":
                                    print("[+] AI 视觉验证通过！")
                                    self._captcha_solved = True
                                    self._captcha_authid = captcha_token
                                    return {"token": captcha_token, "authid": captcha_token}
                            else:
                                print("[!] AI 未能识别目标位置")
                        else:
                            print("[!] AI 方案图片解码失败")
            else:
                print("\n[*] 方案2.5: AI 视觉求解（跳过，未配置 API Key）")
        except ImportError:
            print("\n[*] 方案2.5: AI 视觉求解（跳过，vision_solver 模块未找到）")
        except Exception as e:
            print(f"\n[!] AI 视觉求解异常: {e}")

        # === 方案3: 弹出窗口让用户点击（无头模式下跳过） ===
        if self.headless:
            print("\n[*] 方案3: 手动点击（跳过，无头模式）")
            return None

        print("\n[*] 方案3: 获取新验证码，弹出窗口让您手动点击...")
        challenge = self.get_click_captcha()
        if challenge.get("status") != "OK":
            print(f"[!] 无法获取验证码: {json.dumps(challenge, ensure_ascii=False)[:200]}")
            return None

        captcha_token = challenge.get("token")
        if not captcha_token:
            return None

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

        if big_img_bytes and small_img_bytes:
            x, y = self._interactive_click(big_img_bytes, small_img_bytes, captcha_token)
            if x is not None and y is not None:
                check_res = self.check_captcha(captcha_token, [{"x": x, "y": y}])
                print(f"[*] 验证结果: {check_res}")
                if check_res.get("status") == "OK":
                    print("[+] 手动点击验证通过！")
                    self._captcha_solved = True
                    self._captcha_authid = captcha_token
                    return {"token": captcha_token, "authid": captcha_token}

        return None

    def cancel(self, reservation_id):
        """取消预约"""
        return self._api_get(
            f"/rest/v2/cancel/{reservation_id}",
            {"id": reservation_id},
        )


# ==================== 主入口 ====================

# 预设房间名列表（按常用顺序）
PRESET_ROOMS = [
    "第二自习室",
    "308自习室",
    "第三自习室",
    "第一自习室",
    "第一自习室A",
]

def _pick_room(rooms):
    """让用户选择房间：按预设顺序展示，其余房间追加在后面"""
    # 建立 name → room 映射
    by_name = {}
    for r in rooms:
        name = r.get("name", "")
        by_name[name] = r

    # 先展示预设房间
    ordered = []
    seen = set()
    for pname in PRESET_ROOMS:
        if pname in by_name:
            ordered.append(by_name[pname])
            seen.add(pname)
    # 其余房间
    for r in rooms:
        if r["name"] not in seen:
            ordered.append(r)

    print("\n可选房间:")
    for i, r in enumerate(ordered):
        status = f"空闲 {r['free']}/{r['total']}" if r['free'] > 0 else "已满"
        print(f"  [{i+1}] {r['name']}   ({status})")

    while True:
        choice = input(f"\n选房间 [1-{len(ordered)}]: ").strip()
        if choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < len(ordered):
                r = ordered[idx]
                if r['free'] == 0:
                    print(f"该房间已满，请重新选择")
                    continue
                return r
        print("输入无效，请重试")


def _pick_time():
    """让用户选择开始时间，返回 preferred_start（分钟），None=自动"""
    print("\n请选择开始时间（结束时间统一 22:00）:")
    print("  [1] 10:00")
    print("  [2] 13:00")
    print("  [3] 14:00")
    print("  [4] 15:00")
    print("  [5] 自定义")
    print("  [6] 自动（最早可用）")

    while True:
        choice = input("选择 [1-6]: ").strip()
        if choice == "1":
            return 600   # 10:00
        elif choice == "2":
            return 780   # 13:00
        elif choice == "3":
            return 840   # 14:00
        elif choice == "4":
            return 900   # 15:00
        elif choice == "5":
            time_str = input("输入开始时间 (如 8:00, 10:30): ").strip()
            try:
                h, m = time_str.split(":")
                return int(h) * 60 + int(m)
            except:
                print("格式错误，请用 HH:MM 格式，如 8:00")
        elif choice == "6":
            return None  # 自动
        else:
            print("输入无效，请重试")


def _list_bookable_seats(bot, room_id, room_name, date_str, preferred_start):
    """查询房间内符合时间条件的座位，返回 [{seat_id, name, area, start_time, end_time, ...}]"""
    print(f"\n[*] 查询 {room_name} 空闲座位...")
    seats = bot.find_available_seats(room_id, date_str)
    if not seats:
        print("[!] 该房间无空闲座位")
        return []

    total = len(seats)
    print(f"[+] 找到 {total} 个空闲座位，正在检查时间可用性...")
    last_pct = -1

    bookable = []
    for i, seat in enumerate(seats):
        # 进度显示（每 10% 输出一次）
        pct = (i + 1) * 100 // total
        if pct >= last_pct + 10:
            print(f"    进度: {i+1}/{total} ({pct}%)")
            last_pct = pct

        seat_id = seat["seat_id"]
        start_times = bot.get_start_times(seat_id, date_str)
        if start_times.get("status") != "success":
            continue

        available_starts = start_times.get("data", {}).get("startTimes", [])
        if not available_starts:
            continue

        # 找匹配的开始时间
        best_start = None
        if preferred_start is not None:
            for t in available_starts:
                tid = t.get("id", "0") if isinstance(t, dict) else str(t)
                if tid == "now":
                    continue
                t_min = int(tid)
                if t_min >= preferred_start:
                    best_start = t_min
                    break
        else:
            for t in available_starts:
                tid = t.get("id", "0") if isinstance(t, dict) else str(t)
                if tid == "now":
                    continue
                best_start = int(tid)
                break

        if best_start is None:
            continue

        # 获取结束时间（尽量到 22:00）
        end_times = bot.get_end_times(seat_id, date_str, best_start)
        available_ends = []
        if end_times.get("status") == "success":
            available_ends = end_times.get("data", {}).get("endTimes", [])

        best_end = None
        for t in reversed(available_ends):
            tid = t.get("id", "0") if isinstance(t, dict) else str(t)
            t_min = int(tid)
            if t_min <= 1320:
                best_end = t_min
                break

        if best_end is None and available_ends:
            tid = available_ends[-1].get("id", "0") if isinstance(available_ends[-1], dict) else str(available_ends[-1])
            best_end = int(tid)

        if best_end is None:
            best_end = best_start + 60

        bookable.append({
            **seat,
            "start_time": best_start,
            "end_time": best_end,
        })

    # 排序：精确匹配优先 → 座位号升序（按实际位置）
    if preferred_start is not None:
        bookable.sort(key=lambda s: (
            0 if s["start_time"] == preferred_start else 1,  # 精确匹配排前面
            s["start_time"],    # 开始时间早的优先
            int(s["name"]) if s["name"].isdigit() else 9999,  # 座位号升序
        ))
    else:
        bookable.sort(key=lambda s: (
            s["start_time"],
            int(s["name"]) if s["name"].isdigit() else 9999,
        ))

    print(f"    完成: {len(bookable)}/{total} 个座位符合条件")
    return bookable


def _min_to_time(minutes):
    """分钟 → HH:MM 格式（独立函数）"""
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def _pick_seat(bookable):
    """让用户从可选座位中挑选"""
    if not bookable:
        return None

    first_start = _min_to_time(bookable[0]['start_time'])
    print(f"\n符合条件（{first_start} 起）的座位:")
    print(f"  {'#':<4} {'座位':<10} {'区域':<16} {'时段'}")
    print(f"  {'-'*4} {'-'*10} {'-'*16} {'-'*18}")
    for i, s in enumerate(bookable):
        time_range = f"{_min_to_time(s['start_time'])}-{_min_to_time(s['end_time'])}"
        print(f"  [{i+1}] {'':<2} {s['name']:<8} {s.get('area',''):<16} {time_range}")

    while True:
        choice = input(f"\n选座位 [1-{len(bookable)}, q=退出]: ").strip()
        if choice.lower() == 'q':
            return None
        if choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < len(bookable):
                return bookable[idx]
        print("输入无效，请重试")


def _load_user_config():
    """加载当前目录下的 config.json，不存在返回空字典"""
    import os
    cfg_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")
    if os.path.exists(cfg_path):
        try:
            with open(cfg_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            pass
    return {}


def main():
    print("=" * 50)
    print("  图书馆座位自动预约系统 v2.0")
    print("=" * 50)

    # 检测配置文件
    cfg = _load_user_config()
    use_cfg = False
    if cfg:
        print(f"\n[!] 检测到配置文件 config.json")
        print(f"    学号: {cfg.get('username', '(未设)')}")
        print(f"    房间: {cfg.get('room', '(未设)')}")
        print(f"    时间: {cfg.get('start_time', '(未设)')}")
        print(f"    座位: {cfg.get('seat', '(未设)')}")
        choice = input("\n是否读取配置？[回车=是 / 0=否]: ").strip()
        if choice != "0":
            use_cfg = True
            print("[+] 已读取配置")

    # 账号
    cfg_user = cfg.get("username", "") if use_cfg else ""
    if cfg_user:
        username = cfg_user
        print(f"学号: {username}")
    else:
        username = input("学号: ").strip()

    # 密码（明文输入）
    cfg_pw = cfg.get("password", "") if use_cfg else ""
    if cfg_pw:
        password = cfg_pw
        print("密码: *** (来自配置)")
    else:
        password = input("密码: ").strip()

    # 日期
    default_date = (dt_date.today() + timedelta(days=1)).strftime("%Y-%m-%d")
    date_str = input(f"日期 [默认明天 {default_date}]: ").strip()
    if not date_str:
        date_str = default_date

    # 登录
    bot = LibSeatBot(username, password)
    if not bot.login():
        print("\n[!] 登录失败，请检查账号密码")
        return
    print("\n[+] 登录成功！")
    bot.get_user_info()

    # 查询可用房间
    print("\n[*] 查询房间信息...")
    stats = bot.get_building_stats(1, date_str)
    data = stats.get("data", [])
    rooms = []

    if isinstance(data, list):
        for item in data:
            if isinstance(item, dict):
                rid = item.get("roomId") or item.get("id") or item.get("room_id")
                rname = item.get("roomName") or item.get("room") or item.get("name") or item.get("room_name")
                free_count = item.get("freeCount") or item.get("free") or item.get("free_count", 0)
                total = item.get("totalSeats") or item.get("total") or item.get("total_seats", 0)
                if rid is not None:
                    rooms.append({"id": rid, "name": rname, "free": free_count, "total": total})

    if not rooms:
        print("[!] 无法获取房间数据")
        return

    # 选房间
    cfg_room = cfg.get("room", "") if use_cfg else ""
    if cfg_room:
        matched = [r for r in rooms if r["name"] == cfg_room]
        if matched:
            selected_room = matched[0]
            if selected_room["free"] == 0:
                print(f"\n[!] 配置的房间 '{cfg_room}' 已满，请手动选择")
                selected_room = _pick_room(rooms)
            else:
                print(f"\n[+] 使用配置房间: {cfg_room}")
        else:
            print(f"\n[!] 配置的房间 '{cfg_room}' 未找到，请手动选择")
            selected_room = _pick_room(rooms)
    else:
        selected_room = _pick_room(rooms)

    room_id = int(selected_room["id"])
    room_name = selected_room["name"]

    # 选时间
    cfg_time = cfg.get("start_time", "") if use_cfg else ""
    if cfg_time:
        try:
            h, m = cfg_time.split(":")
            preferred_start = int(h) * 60 + int(m)
            print(f"[+] 使用配置时间: {cfg_time}, 结束时间: 22:00")
        except:
            preferred_start = _pick_time()
    else:
        preferred_start = _pick_time()

    if preferred_start is not None:
        print(f"[+] 开始时间: {_min_to_time(preferred_start)}, 结束时间: 22:00")
    else:
        print("[+] 开始时间: 自动（最早可用）, 结束时间: 22:00")

    # 列出符合条件的座位
    bookable = _list_bookable_seats(bot, room_id, room_name, date_str, preferred_start)
    if not bookable:
        print("\n[!] 没有符合条件的座位")
        return

    # 默认座位优先
    cfg_seat = cfg.get("seat", "") if use_cfg else ""
    if cfg_seat:
        for i, s in enumerate(bookable):
            if s["name"] == cfg_seat:
                bookable.insert(0, bookable.pop(i))
                print(f"\n[+] 默认座位 '{cfg_seat}' 可用，已置顶")
                break
        else:
            print(f"\n[!] 默认座位 '{cfg_seat}' 不在候选列表中")

    # 选座位
    selected_seat = _pick_seat(bookable)
    if selected_seat is None:
        print("\n[*] 已取消")
        return

    seat_id = selected_seat["seat_id"]
    best_start = selected_seat["start_time"]
    best_end = selected_seat["end_time"]
    print(f"\n[+] 已选择: {selected_seat.get('area','')} {selected_seat['name']}")
    print(f"[+] 时段: {_min_to_time(best_start)} - {_min_to_time(best_end)}")

    # 解验证码 + 预约（验证码失败可重试）
    MAX_BOOK_RETRIES = 3
    for book_try in range(MAX_BOOK_RETRIES):
        if book_try > 0:
            print(f"\n[*] 重试预约 ({book_try+1}/{MAX_BOOK_RETRIES})...")

        print("\n[*] 获取验证码...")
        captcha_result = bot.solve_behavioral_captcha()
        if not captcha_result or not getattr(bot, '_captcha_solved', False):
            if book_try < MAX_BOOK_RETRIES - 1:
                retry = input("[!] 验证码未解决，重试？[Y/n]: ").strip().lower()
                if retry == 'n':
                    return
                continue
            else:
                print("[!] 验证码未解决，预约取消")
                return

        result = bot.free_book(seat_id, date_str, best_start, best_end)
        bot._captcha_solved = False
        bot._captcha_authid = None

        if result.get("status") == "success":
            print(f"\n{'='*50}")
            print(f"  预约成功！")
            print(f"  房间: {room_name}")
            print(f"  座位: {selected_seat['area']} {selected_seat['name']}")
            print(f"  时间: {_min_to_time(best_start)} - {_min_to_time(best_end)}")
            print(f"  日期: {date_str}")
            print(f"{'='*50}")
            return
        else:
            msg = result.get('message', str(result))
            print(f"\n[!] 预约失败: {msg}")
            if "已有" in msg:
                return
            if book_try < MAX_BOOK_RETRIES - 1:
                retry = input("重试？[Y/n]: ").strip().lower()
                if retry == 'n':
                    return
            else:
                print("[!] 已达最大重试次数")


if __name__ == "__main__":
    main()
