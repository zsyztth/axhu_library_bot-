"""
核心 API 客户端 — SSO CAS 认证、HMAC 签名、REST API 封装
"""

import base64
import re
import time
import json
import uuid
import hmac
import hashlib
import requests
from datetime import date as dt_date
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad
from bs4 import BeautifulSoup

from .constants import SSO_BASE, SEAT_BASE, HMAC_SECRET


# ====== 加密工具 ======

def aes_ecb_encrypt(key_b64, plaintext):
    """AES-128-ECB PKCS7 → base64（SSO 登录密码加密）"""
    key = base64.b64decode(key_b64)
    cipher = AES.new(key, AES.MODE_ECB)
    padded = pad(plaintext.encode("utf-8"), 16)
    return base64.b64encode(cipher.encrypt(padded)).decode()


def aes_cbc_decrypt(ciphertext_b64):
    """AES-CBC PKCS7 解密（NUMCODE 解密）"""
    key = b"server_date_time"
    iv = b"client_date_time"
    ciphertext = base64.b64decode(ciphertext_b64)
    cipher = AES.new(key, AES.MODE_CBC, iv)
    return unpad(cipher.decrypt(ciphertext), 16).decode("utf-8")


def make_hmac_headers(method):
    """生成 HMAC SHA256 请求签名头"""
    if not HMAC_SECRET:
        raise RuntimeError(
            "HMAC_SECRET 未设置。请通过环境变量 HMAC_SECRET "
            "或 config.json 中的 hmac_secret 字段设置。"
        )
    req_id = str(uuid.uuid4())
    req_date = str(int(time.time() * 1000))
    message = f"seat::{req_id}::{req_date}::{method.upper()}"
    sig = hmac.new(
        HMAC_SECRET.encode(), message.encode(), hashlib.sha256
    ).hexdigest()
    return {
        "X-request-id": req_id,
        "X-request-date": req_date,
        "X-hmac-request-key": sig,
    }


# ====== 主 API 类 ======

class LibSeatAPI:
    """图书馆座位预约系统 API 客户端"""

    def __init__(self, username, password):
        self.username = username
        self.password = password
        self.session = requests.Session()
        self.session.headers["User-Agent"] = (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 "
            "Safari/537.36 Edg/148.0.0.0"
        )
        self.token = None
        self.user_id = None
        self._captcha_solved = False
        self._captcha_authid = None

    # ====== 登录 ======

    def login(self):
        """
        完整 SSO CAS 登录流程:
        图书馆 SSO 入口 → SSO 登录页 → CAS ticket → 图书馆 token
        """
        print("\n[*] 第一步：通过图书馆 SSO 入口跳转到 SSO...")

        lib_entry = (
            f"{SEAT_BASE}/remote/static/sso/login"
            f"?redirectUrl=https://seat.axhu.edu.cn/libseat/#/login"
        )
        resp = self.session.get(lib_entry, allow_redirects=True)
        login_page_url = resp.url
        print(f"[*] 当前 URL: {login_page_url[:120]}...")

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

        # 获取验证码并 OCR
        import ddddocr

        ocr = ddddocr.DdddOcr()
        captcha_url = f"{SSO_BASE}/api/captcha/generate/DEFAULT"
        captcha_resp = self.session.get(captcha_url)
        captcha_code = ocr.classification(captcha_resp.content).strip()
        print(f"[+] 验证码 OCR: {captcha_code}")

        if len(captcha_code) < 3:
            captcha_resp = self.session.get(captcha_url)
            captcha_code = ocr.classification(captcha_resp.content).strip()
            print(f"[+] 重试 OCR: {captcha_code}")

        # 加密
        encrypted_pw = aes_ecb_encrypt(croypto_key, self.password)
        encrypted_captcha = aes_ecb_encrypt(croypto_key, "{}")

        login_resp = self._do_login_post(
            croypto_key, execution, captcha_code, encrypted_pw, encrypted_captcha,
            login_page_url
        )
        print(f"[*] SSO 响应: {login_resp.status_code}")

        # 重试验证码（最多5次）
        retry_count = 0
        while self._needs_retry(login_resp) and retry_count < 5:
            retry_count += 1
            print(f"[!] 验证码错误，重试 ({retry_count}/5)...")
            captcha_resp2 = self.session.get(captcha_url)
            captcha_code2 = ocr.classification(captcha_resp2.content).strip()
            print(f"[+] OCR ({retry_count}): {captcha_code2}")
            login_resp = self._do_login_post(
                croypto_key, execution, captcha_code2,
                encrypted_pw,
                aes_ecb_encrypt(croypto_key, "{}"),
                login_page_url,
            )
            print(f"[*] SSO 响应 ({retry_count}): {login_resp.status_code}")

        return self._handle_cas_redirect(login_resp)

    def _do_login_post(self, croypto_key, execution, captcha_code, enc_pw, enc_captcha, referer):
        """发送 SSO 登录 POST"""
        return self.session.post(
            f"{SSO_BASE}/login",
            data={
                "username": self.username,
                "type": "UsernamePassword",
                "_eventId": "submit",
                "geolocation": "",
                "execution": execution,
                "captcha_code": captcha_code,
                "croypto": croypto_key,
                "password": enc_pw,
                "captcha_payload": enc_captcha,
            },
            headers={
                "Origin": SSO_BASE,
                "Referer": referer,
                "Content-Type": "application/x-www-form-urlencoded",
            },
            allow_redirects=False,
        )

    @staticmethod
    def _needs_retry(resp):
        """判断是否需要重试（验证码错误）"""
        location = resp.headers.get("Location", "")
        is_redirect = resp.status_code in (301, 302, 303, 307, 308)
        return not is_redirect or (
            "error" in location
            or ("login" in location and "ticket" not in location)
        )

    def _handle_cas_redirect(self, login_resp):
        """跟踪 CAS 重定向，获取 session token"""
        if login_resp.status_code not in (301, 302, 303, 307, 308):
            print("[!] SSO 登录失败")
            return False

        location = login_resp.headers.get("Location", "")
        print(f"[*] CAS 重定向: {location[:120]}...")

        cas_resp = self.session.get(location, allow_redirects=False)
        cas_location = cas_resp.headers.get("Location", "")

        print(f"[*] CAS 验证响应: {cas_resp.status_code}")
        if cas_location:
            print(f"[*] CAS 重定向: {cas_location[:120]}...")

        if cas_resp.status_code in (301, 302, 303, 307, 308) and cas_location:
            final_resp = self.session.get(cas_location, allow_redirects=True)
        else:
            final_resp = cas_resp

        print(f"[*] 最终 URL: {final_resp.url[:150]}...")

        auth_token = self._extract_token(final_resp.url, location)
        if auth_token:
            return self._sso_auth(auth_token)

        print("[!] SSO 登录失败")
        return False

    @staticmethod
    def _extract_token(final_url, location):
        """从重定向 URL 提取 JWT 或 CAS ticket"""
        # JWT
        token_match = re.search(r"[?&#]token=([^&\s#]+)", final_url)
        if token_match:
            val = token_match.group(1)
            if val.startswith("eyJ") or len(val) > 80:
                return val

        # ticketCode
        tc_match = re.search(r"ticketCode=([^&\s]+)", final_url)
        if tc_match:
            return tc_match.group(1)

        # CAS ticket
        ticket_match = re.search(r"[?&]ticket=(ST-[^&\s]+)", location)
        if ticket_match:
            return ticket_match.group(1)

        return None

    def _sso_auth(self, cas_ticket):
        """用 CAS ticket 换取图书馆 session token"""
        print("\n[*] 第二步：ssoAuth 换取 token...")
        resp = self.session.post(
            f"{SEAT_BASE}/rest/ssoAuth?token={cas_ticket}",
            json={},
            headers={
                "Referer": f"{SEAT_BASE}/libseat/",
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

        print("[!] ssoAuth 失败")
        return False

    # ====== 通用 API 方法 ======

    def _api_get(self, path, params=None):
        """带 HMAC 签名的 GET 请求，token 过期自动重登"""
        url = f"{SEAT_BASE}{path}"
        if params is None:
            params = {}
        params["token"] = self.token
        headers = {
            "Authorization": self.token,
            "Referer": f"{SEAT_BASE}/libseat/",
            "loginType": "PC",
            **make_hmac_headers("GET"),
        }
        resp = self.session.get(url, params=params, headers=headers)
        result = resp.json()

        if result.get("status") != "success":
            code = result.get("code", "")
            msg = result.get("message", "")
            print(f"[!] API 失败 [{path}]: code={code}, msg={msg}")
            if code == "12" or "登录" in str(msg):
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
        url = f"{SEAT_BASE}{path}"
        if params is None:
            params = {}
        params["token"] = self.token
        headers = {
            "Authorization": self.token,
            "Referer": f"{SEAT_BASE}/libseat/",
            "loginType": "PC",
            "Content-Type": "application/json",
            **make_hmac_headers("POST"),
        }
        resp = self.session.post(url, json=body or {}, params=params, headers=headers)
        return resp.json()

    # ====== 用户 & 建筑 ======

    def get_user_info(self):
        """获取用户信息（设置 self.user_id）"""
        result = self._api_get("/rest/v2/user")
        if result.get("status") == "success":
            self.user_id = result["data"]["id"]
            print(f"[+] userId: {self.user_id}")
        return result

    def get_building_stats(self, building_id=1, date_str=None):
        """获取建筑房间统计"""
        if date_str is None:
            date_str = dt_date.today().strftime("%Y-%m-%d")
        return self._api_get(
            f"/rest/v2/room/stats2/{building_id}/{date_str}",
            {"buildingId": building_id, "date": date_str},
        )

    def get_room_layout(self, room_id, date_str=None):
        """获取房间座位布局"""
        if date_str is None:
            date_str = dt_date.today().strftime("%Y-%m-%d")
        return self._api_get(
            f"/rest/v2/room/layoutByDate/{room_id}/{date_str}",
            {"id": room_id, "date": date_str},
        )

    # ====== 座位 & 时间 ======

    def find_available_seats(self, room_id, date_str=None):
        """查找房间内所有空闲座位"""
        if date_str is None:
            date_str = dt_date.today().strftime("%Y-%m-%d")

        layout = self.get_room_layout(room_id, date_str)
        seats = []

        if layout.get("status") == "success":
            data = layout.get("data", {})
            room_name = data.get("name", "")
            layout_map = data.get("layout", {}) if isinstance(data, dict) else {}
            print(f"[*] 房间: {room_name}, layout 条目数: {len(layout_map)}")

            stats = {}
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

        return seats

    def get_start_times(self, seat_id, date_str=None):
        """获取座位可用开始时间列表"""
        if date_str is None:
            date_str = dt_date.today().strftime("%Y-%m-%d")
        return self._api_get(
            f"/rest/v2/startTimesForSeat/{seat_id}/{date_str}",
            {"seatId": seat_id, "date": date_str},
        )

    def get_end_times(self, seat_id, date_str, start_minutes):
        """获取指定开始时间后的可用结束时间"""
        start_str = str(start_minutes) if start_minutes != "now" else "now"
        return self._api_get(
            f"/rest/v2/endTimesForSeat/{seat_id}/{date_str}/{start_str}",
            {"id": seat_id, "date": date_str, "start": start_str},
        )

    def get_current_reservation(self):
        """获取当前有效预约"""
        return self._api_get("/rest/v2/user/reservations")

    # ====== 预约 ======

    def free_book(self, seat_id, date_str, start_minutes, end_minutes):
        """预约座位（multipart/form-data POST）"""
        url = f"{SEAT_BASE}/rest/v2/freeBook"
        data = {
            "startTime": str(start_minutes),
            "endTime": str(end_minutes),
            "seat": str(seat_id),
            "date": date_str,
            "userId": str(self.user_id) if self.user_id else "",
            "username": self.username,
        }
        if self._captcha_authid:
            data["authid"] = self._captcha_authid

        headers = {
            "Authorization": self.token,
            "Referer": f"{SEAT_BASE}/libseat/",
            "loginType": "PC",
            **make_hmac_headers("POST"),
        }
        params = {"token": self.token}
        resp = self.session.post(url, data=data, params=params, headers=headers)
        return resp.json()

    def cancel(self, reservation_id):
        """取消预约"""
        return self._api_get(
            f"/rest/v2/cancel/{reservation_id}",
            {"id": reservation_id},
        )
