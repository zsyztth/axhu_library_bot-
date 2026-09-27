# 图书馆预约 API 文档

## 基础信息
- BaseURL: https://seat.axhu.edu.cn
- Auth header: `Authorization: 58ae6b5016f8350f27c0b7c751576cab8499cc5406193037`
- loginType: PC

## 接口列表

### 获取验证码
GET /auth/createCaptcha
返回: {captchaId, captchaImage (data URI)}

### 校验验证码
GET /cap/checkCaptcha?a={base64}&token={captchaId}&userId={userId}&username={username}
需要 HMAC 签名头: X-request-id, X-request-date, X-hmac-request-key

### 提交验证(备选)
POST /cap/captcha/{token}?username={username}

### 预约座位
POST /rest/v2/freeBook?token={loginToken}
Form: startTime, endTime, seat, date, userId, username, authid

### 用户预约列表
GET /rest/v2/user/reservations?token={loginToken}

### 用户信息
GET /rest/v2/user?token={loginToken}
