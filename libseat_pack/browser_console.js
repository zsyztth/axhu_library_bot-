// ===== 1. 获取密钥 =====
const app = document.querySelector('#app').__vue__;
console.log('$NUMCODE:', app?.$NUMCODE);
console.log('$CODE:', app?.$CODE);

// ===== 2. 获取验证码图片并求解 =====
(async () => {
    const img = document.querySelector('img[src^="data:image"]');
    if (!img) { alert('没找到验证码'); return; }
    
    const c = document.createElement('canvas');
    c.width = img.naturalWidth; c.height = img.naturalHeight;
    c.getContext('2d').drawImage(img, 0, 0);
    const b64 = c.toDataURL('image/png').split(',')[1];
    
    console.log('图片 base64 (前100字):', b64.substring(0,100));
    
    // 用页面本身的 axios（带 HMAC 签名）提交
    const answer = prompt('验证码答案:');
    if (!answer) return;
    
    // 从页面找 token（captcha图片里的ID）
    const token = prompt('Token (captchaId):');
    
    const resp = await fetch(`/cap/checkCaptcha?a=${btoa(JSON.stringify([answer]))}&token=${token}&userId=32677&username=2442151726`);
    console.log('结果:', await resp.json());
})();

// ===== 3. 完整预约流程 =====
async function bookSeat(seatId, date, startTime, endTime) {
    // 获取验证码
    const capResp = await fetch('/auth/createCaptcha');
    const capData = await capResp.json();
    console.log('CaptchaID:', capData.captchaId);
    // ... 求解验证码 ... 提交 ...
    // ... 预约 ...
}
