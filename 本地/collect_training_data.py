"""
验证码训练数据收集器
流程: 登录 → 触发预约验证码 → 框选文字 → 输入文字名 → 保存到对应文件夹
用法: python collect_training_data.py
"""
import os, sys, json, base64, time
import cv2, numpy as np

# 直接复用已验证的 libseat_bot 登录逻辑
from libseat_bot import LibSeatBot, make_hmac_headers, HMAC_SECRET

SEAT_BASE = "https://seat.axhu.edu.cn"
TRAINING_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "素材")

class CaptchaDataCollector(LibSeatBot):
    """继承 LibSeatBot，复用其登录+验证码 API，只覆写交互式收集部分"""
    def __init__(self, username, password):
        super().__init__(username, password)
        # 连接池优化：减少 TIME_WAIT 端口占用
        from requests.adapters import HTTPAdapter
        adapter = HTTPAdapter(pool_connections=10, pool_maxsize=10, max_retries=2)
        self.session.mount('https://', adapter)

    # ============ 获取点击验证码 ============
    def get_click_captcha(self):
        """获取行为验证码挑战"""
        url = f"{SEAT_BASE}/cap/captcha/{self.token}"
        params = {"username": self.username}
        headers = {
            "Authorization": self.token,
            "Referer": f"{SEAT_BASE}/libseat/",
            "loginType": "PC",
            **make_hmac_headers("POST"),
        }
        resp = self.session.post(url, params=params, headers=headers)
        return resp.json()

    # ============ 交互式框选 + 保存 ============
    def collect_sample(self):
        """
        获取验证码 → 显示大图+小图 → 用户输入文字名+框选区域 → 保存截图
        返回: True 继续, False 退出
        """
        print("\n" + "=" * 50)
        print("[*] 获取新的验证码...")

        # 端口耗尽或网络波动时自动重试
        for net_retry in range(3):
            try:
                challenge = self.get_click_captcha()
                break
            except Exception as e:
                wait = (net_retry + 1) * 5
                print(f"   [!] 网络错误: {e}")
                print(f"   [*] 等待 {wait}s 后重试 ({net_retry+1}/3)...")
                time.sleep(wait)
        else:
            print("[!] 网络重试耗尽，退出")
            return False

        if challenge.get("status") != "OK":
            msg = challenge.get("message", json.dumps(challenge, ensure_ascii=False)[:200])
            print(f"[!] 获取失败: {msg}")
            # token 过期或风控，不要假装成功
            if challenge.get("code") == "12" or "token" in str(msg).lower():
                print("[!] Token 可能已过期，需重新登录")
            return "retry"  # 特殊标记：失败但可重试

        # 解码图片
        big_img = None
        small_img = None
        for key in ["image", "wordImage"]:
            data_uri = challenge.get(key, "")
            if data_uri and data_uri.startswith("data:image/"):
                b64_data = data_uri.split(",", 1)[-1]
                img_bytes = base64.b64decode(b64_data)
                img = cv2.imdecode(np.frombuffer(img_bytes, np.uint8), 1)
                if key == "image":
                    big_img = img
                else:
                    small_img = img

        if big_img is None or small_img is None:
            print("[!] 图片解码失败")
            return True

        # 构造显示：顶部放小图(参考) + 下方放大图
        sw, sh = small_img.shape[1], small_img.shape[0]
        ref_h = sh + 30
        display = np.ones((ref_h + big_img.shape[0],
                           max(big_img.shape[1], sw + 60), 3), dtype=np.uint8) * 240
        # 小图居中
        sx = (display.shape[1] - sw) // 2
        display[10:10+sh, sx:sx+sw] = small_img
        cv2.putText(display, "TARGET CHAR (look here, then find it below)",
                    (5, sh + 22), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 255), 1)
        # 大图
        display[ref_h:ref_h+big_img.shape[0], :big_img.shape[1]] = big_img
        # 分隔线
        cv2.line(display, (0, ref_h), (display.shape[1], ref_h), (0, 0, 0), 2)

        # 交互状态
        state = {"drawing": False, "start": None, "end": None, "done": False, "confirmed": False}

        def on_mouse(event, x, y, flags, param):
            if y < ref_h:  # 顶部参考区不响应
                return
            if event == cv2.EVENT_LBUTTONDOWN:
                state["drawing"] = True
                state["start"] = (x, y - ref_h)
                state["end"] = (x, y - ref_h)
            elif event == cv2.EVENT_MOUSEMOVE and state["drawing"]:
                state["end"] = (x, y - ref_h)
                d = display.copy()
                cv2.rectangle(d,
                    (state["start"][0], state["start"][1] + ref_h),
                    (x, y), (0, 255, 0), 2)
                cv2.imshow(win_name, d)
            elif event == cv2.EVENT_LBUTTONUP:
                state["drawing"] = False
                state["end"] = (x, y - ref_h)
                state["done"] = True
                state["confirmed"] = True  # 松开鼠标即确认
                cv2.rectangle(display,
                    (state["start"][0], state["start"][1] + ref_h),
                    (x, y), (0, 255, 0), 2)
                cv2.imshow(win_name, display)

        win_name = "CAPTCHA - drag to select char, ESC=skip, q=quit"
        cv2.imshow(win_name, display)
        cv2.setMouseCallback(win_name, on_mouse)

        print("   操作: 鼠标拖拽框选目标文字，松开即确认")
        print("   ESC=跳过   q=退出   关窗=跳过")

        while True:
            key = cv2.waitKey(100) & 0xFF
            # 检测窗口是否关闭
            try:
                if cv2.getWindowProperty(win_name, cv2.WND_PROP_VISIBLE) < 1:
                    break
            except:
                break
            # 松开鼠标确认或按 ENTER
            if state["confirmed"]:
                cv2.waitKey(200)  # 短暂显示矩形再关闭
                break
            if key == 13 or key == 32:  # ENTER/SPACE
                state["confirmed"] = True
                break
            elif key == 27:  # ESC
                cv2.destroyAllWindows()
                cv2.waitKey(1)
                return True
            elif key == ord('q') or key == ord('Q'):
                cv2.destroyAllWindows()
                cv2.waitKey(1)
                return False

        confirmed = state["confirmed"]
        cv2.destroyAllWindows()
        cv2.waitKey(1)

        if not confirmed or not state["done"] or state["start"] is None or state["end"] is None:
            print("   未框选或已跳过")
            return True

        x1, y1 = state["start"]
        x2, y2 = state["end"]
        if x1 > x2: x1, x2 = x2, x1
        if y1 > y2: y1, y2 = y2, y1

        # 裁剪区域
        bx, by = big_img.shape[1], big_img.shape[0]
        x1, x2 = max(0, min(x1, bx)), max(0, min(x2, bx))
        y1, y2 = max(0, min(y1, by)), max(0, min(y2, by))

        if x2 - x1 < 5 or y2 - y1 < 5:
            print("   选择区域太小，跳过")
            return True

        crop = big_img[y1:y2, x1:x2]
        crop_h, crop_w = crop.shape[:2]
        print(f"   框选区域: ({x1},{y1})-({x2},{y2}), 裁剪尺寸: {crop_w}x{crop_h}")

        # 输入文字名（输入 q 退出）
        char_name = input("   该字是 (输入 q 退出): ").strip()
        if char_name.lower() == 'q':
            print("   退出程序")
            return False
        if not char_name:
            print("   未输入文字名，跳过")
            return True

        # 保存
        char_dir = os.path.join(TRAINING_DIR, char_name)
        os.makedirs(char_dir, exist_ok=True)
        ts = int(time.time() * 1000)

        # 保存裁剪图和小图参考
        crop_path = os.path.join(char_dir, f"{ts}_{crop_w}x{crop_h}.png")
        ref_path = os.path.join(char_dir, f"{ts}_ref.png")
        cv2.imencode('.png', crop)[1].tofile(crop_path)
        cv2.imencode('.png', small_img)[1].tofile(ref_path)

        count = len([f for f in os.listdir(char_dir) if not f.endswith("_ref.png")])
        print(f"   [+] 已保存: {crop_path}")
        print(f"   [+] 该字已收集: {count} 个样本")
        return True

    def run(self):
        TOKEN_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".token_cache.json")

        # 尝试从缓存恢复 token（避免反复登录被风控）
        if os.path.exists(TOKEN_FILE):
            try:
                with open(TOKEN_FILE, "r") as f:
                    cache = json.load(f)
                self.token = cache.get("token")
                self.user_id = cache.get("user_id")
                # 验证 token 是否还有效
                test = self.session.get(
                    f"{SEAT_BASE}/rest/v2/user",
                    params={"token": self.token},
                    headers={"Authorization": self.token, "loginType": "PC",
                             "Referer": f"{SEAT_BASE}/libseat/",
                             **make_hmac_headers("GET")}
                )
                if test.json().get("status") == "success":
                    self.user_id = test.json()["data"]["id"]
                    print(f"[+] 从缓存恢复 token: {self.token[:20]}...")
                else:
                    print("[*] 缓存 token 已过期，重新登录...")
                    self.token = None
            except:
                self.token = None

        if not self.token:
            if not self.login():
                print("[!] 登录失败")
                return
            # 保存 token 缓存
            with open(TOKEN_FILE, "w") as f:
                json.dump({"token": self.token, "user_id": self.user_id}, f)
            print(f"[+] token 已缓存到 {TOKEN_FILE}")

        print("\n" + "=" * 60)
        print("  验证码训练数据收集器")
        print("=" * 60)
        print(f"  保存目录: {TRAINING_DIR}")
        print("  操作: 鼠标拖拽框选大图中的目标文字 → 按 ENTER → 输入字名")
        print("  ESC = 跳过    q = 退出")
        print("=" * 60)

        count = 0
        fail_count = 0
        try:
            while True:
                result = self.collect_sample()
                if result is True:  # 成功收集一个样本
                    count += 1
                    fail_count = 0
                    print(f"\n--- 已收集 {count} 个样本 ---")
                elif result == "retry":  # API 失败，不计入样本
                    fail_count += 1
                    if fail_count >= 5:
                        print("\n[!] 连续 5 次失败，token 可能过期，尝试重新登录...")
                        # 清楚缓存 token
                        if os.path.exists(TOKEN_FILE):
                            os.remove(TOKEN_FILE)
                        self.token = None
                        if self.login():
                            fail_count = 0
                            continue
                        else:
                            print("[!] 重新登录失败，退出")
                            break
                    print(f"   连续失败 {fail_count}/5 次，将重试...")
                elif result is False:  # 用户主动退出
                    break
        except KeyboardInterrupt:
            pass

        # 统计
        print("\n" + "=" * 60)
        print("  收集完成！统计:")
        if os.path.exists(TRAINING_DIR):
            for char_dir in sorted(os.listdir(TRAINING_DIR)):
                path = os.path.join(TRAINING_DIR, char_dir)
                if os.path.isdir(path):
                    imgs = [f for f in os.listdir(path) if not f.endswith("_ref.png")]
                    print(f"    {char_dir}: {len(imgs)} 个样本")
        print(f"\n  数据保存在: {TRAINING_DIR}")


if __name__ == "__main__":
    username = input("学号: ").strip()
    password = input("密码: ").strip()
    collector = CaptchaDataCollector(username, password)
    collector.run()
