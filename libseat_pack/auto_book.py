"""全自动图书馆预约 - 需要先获取$NUMCODE"""
import requests, json, base64, time, uuid, hmac, hashlib, re, cv2, numpy as np
import ddddocr
from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad

BASE = "https://seat.axhu.edu.cn"
USER_ID = "32677"
USERNAME = "2442151726"

class LibraryBooker:
    def __init__(self, encrypted_numcode):
        """encrypted_numcode: 从浏览器Console获取的加密$NUMCODE"""
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0",
            "loginType": "PC",
        })
        
        # 解密密钥
        key = b"server_date_time"
        iv = b"client_date_time"
        cipher = AES.new(key, AES.MODE_CBC, iv)
        self.secret = unpad(cipher.decrypt(bytes.fromhex(encrypted_numcode)), 16).decode()
        print(f"密钥已解密: {self.secret[:4]}...")
        
        self.text_ocr = ddddocr.DdddOcr(beta=True, show_ad=False)
    
    def sign(self, method="get"):
        req_id = str(uuid.uuid4())
        req_date = int(time.time() * 1000)
        msg = f"seat::{req_id}::{req_date}::{method.upper()}"
        sig = hmac.new(self.secret.encode(), msg.encode(), hashlib.sha256).hexdigest()
        return {
            "X-request-id": req_id,
            "X-request-date": str(req_date),
            "X-hmac-request-key": sig
        }
    
    def get_captcha(self):
        r = self.session.get(f"{BASE}/auth/createCaptcha",
            headers={"Authorization": "58ae6b5016f8350f27c0b7c751576cab8499cc5406193037"})
        d = r.json()
        b64 = re.sub(r'^data:image/\w+;base64,', '', d['captchaImage'])
        img = cv2.imdecode(np.frombuffer(base64.b64decode(b64), np.uint8), 1)
        _, buf = cv2.imencode('.png', img)
        answer = self.text_ocr.classification(buf.tobytes())
        return d['captchaId'], answer
    
    def check_captcha(self, cap_id, answer):
        a_b64 = base64.b64encode(json.dumps([answer]).encode()).decode()
        r = self.session.get(f"{BASE}/cap/checkCaptcha",
            params={"a": a_b64, "token": cap_id, "userId": USER_ID, "username": USERNAME},
            headers={
                "Authorization": "58ae6b5016f8350f27c0b7c751576cab8499cc5406193037",
                **self.sign("get")
            })
        return r.json()
    
    def book(self, seat_id, date, start_time, end_time, auth_id, login_token):
        r = self.session.post(f"{BASE}/rest/v2/freeBook?token={login_token}",
            data={
                "startTime": str(start_time),
                "endTime": str(end_time),
                "seat": str(seat_id),
                "date": date,
                "userId": USER_ID,
                "username": USERNAME,
                "authid": auth_id
            },
            headers={
                "Authorization": login_token,
                **self.sign("post")
            })
        return r.json()

# 用法:
# booker = LibraryBooker("加密的$NUMCODE")
# cap_id, answer = booker.get_captcha()
# print(f"验证码: {answer}")
# result = booker.check_captcha(cap_id, answer)
# print(result)
