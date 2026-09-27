"""HMAC签名 - 需要$NUMCODE才能工作"""
import hmac, hashlib, uuid, time
from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad

def decrypt_numcode(encrypted_hex):
    """AES解密 $NUMCODE"""
    key = b"server_date_time"
    iv = b"client_date_time"
    cipher = AES.new(key, AES.MODE_CBC, iv)
    encrypted = bytes.fromhex(encrypted_hex)
    return unpad(cipher.decrypt(encrypted), 16).decode()

def sign_request(secret, method="get"):
    """生成HMAC签名头"""
    req_id = str(uuid.uuid4())
    req_date = int(time.time() * 1000)
    msg = f"seat::{req_id}::{req_date}::{method.upper()}"
    sig = hmac.new(secret.encode(), msg.encode(), hashlib.sha256).hexdigest()
    return {
        "X-request-id": req_id,
        "X-request-date": str(req_date),
        "X-hmac-request-key": sig
    }

# 用法:
# 1. 从浏览器 Console 获取 $NUMCODE (加密的十六进制)
# 2. secret = decrypt_numcode($NUMCODE)
# 3. headers = sign_request(secret, "get")
