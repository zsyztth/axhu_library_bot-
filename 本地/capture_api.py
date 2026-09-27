"""
图书馆预约系统 API 嗅探器 v3
使用 async API — 异步事件循环，不会阻塞网络拦截
用法: pip install playwright && playwright install chromium
      python capture_api.py
"""
import json, os, re, asyncio
from datetime import datetime
from playwright.async_api import async_playwright

OUTPUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "library_api.json")

API_KEYWORDS = ['api', 'ajax', 'json', 'search', 'login', 'book', 'seat',
                'order', 'reserve', 'cancel', 'token', 'auth', 'list',
                'captcha', 'cap/', 'stats', 'layout', 'free', 'timesFor',
                'ssoAuth', 'rest/v2', 'reserv', 'room/']

def is_api(url):
    url_lower = url.lower()
    return any(k in url_lower for k in API_KEYWORDS) or url.endswith('.json')

def clean_headers(headers):
    skip = {'content-length', 'accept-encoding', 'sec-ch-ua', 'sec-ch-ua-mobile',
            'sec-ch-ua-platform', 'user-agent', 'sec-fetch-dest', 'sec-fetch-mode',
            'sec-fetch-site', 'accept-language', 'upgrade-insecure-requests'}
    return {k: v for k, v in headers.items() if k.lower() not in skip and len(v) < 2000}

def _save_result(captured):
    """去重并保存捕获的 API 数据"""
    seen = set()
    unique = []
    for r in captured:
        key = (r["method"], r["url"])
        if key not in seen:
            seen.add(key)
            unique.append(r)

    with open(OUTPUT, "w", encoding="utf-8") as f:
        json.dump(unique, f, ensure_ascii=False, indent=2)

    print(f"\n[OK] 已保存 {len(unique)} 条 API 到: {OUTPUT}")
    key_count = sum(1 for r in unique if any(
        k in r["url"] for k in ["freeBook", "stats", "layout", "captcha", "timesFor", "ssoAuth"]
    ))
    print(f"   核心 API: {key_count} 条")
    return unique

async def capture():
    captured = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context(
            viewport={"width": 1400, "height": 900},
            locale="zh-CN"
        )
        page = await context.new_page()

        # 用 page.route 拦截所有请求（浏览器层面，最可靠）
        async def on_route(route):
            request = route.request
            if is_api(request.url):
                record = {
                    "id": len(captured) + 1,
                    "timestamp": datetime.now().isoformat(),
                    "url": request.url,
                    "method": request.method,
                    "headers": clean_headers(request.headers),
                    "post_data": request.post_data,
                    "status": None,
                }
                captured.append(record)
                key_apis = ["auth", "token", "book", "seat", "layout", "stats",
                            "captcha", "cap/", "timesFor", "free", "ssoAuth", "reserv",
                            "freeBook", "checkCaptcha", "createCaptcha"]
                is_key = any(k in request.url for k in key_apis)
                marker = "[CORE]" if is_key else "  "
                print(f"{marker} [{request.method}] {request.url[:130]}")
            await route.continue_()

        # 拦截响应获取 body
        async def on_response(response):
            for r in reversed(captured):
                if r["url"] == response.url and r["method"] == response.request.method and r["status"] is None:
                    try:
                        body = await response.text()
                        r["status"] = response.status
                        r["response_headers"] = clean_headers(response.headers)
                        r["response_body"] = body[:5000]
                        try:
                            r["response_json"] = json.loads(body)
                        except:
                            pass
                    except:
                        r["status"] = response.status
                    return

        await page.route("**/*", on_route)
        page.on("response", on_response)

        print("=" * 60)
        print("[REC] 图书馆预约 API 嗅探器 v3 (async)")
        print("=" * 60)
        print()
        print("[*] 浏览器将打开图书馆页面，请开始操作...")
        print()
        print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        print("   1. 点「用户名密码」→ 登录")
        print("   2. 选日期 → 自习室 → 空座位")
        print("   3. 选时间 → 点「预约」")
        print("   4. 完成行为验证码（如有）")
        print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        print()
        print("全部完成后，回到终端按 Ctrl+C 保存")
        print()

        await page.goto("https://seat.axhu.edu.cn/libseat/#/home")
        print("[*] 页面已加载，开始监听 API...\n")

        # Windows 兼容：用 asyncio.sleep 轮询保持事件循环活跃
        # KeyboardInterrupt 在 sleep 时可以被捕获
        import signal
        running = True
        def _handle_sigint(signum, frame):
            nonlocal running
            running = False
            print("\n[!] 收到停止信号，保存中...")
        signal.signal(signal.SIGINT, _handle_sigint)
        signal.signal(signal.SIGTERM, _handle_sigint)

        try:
            while running:
                await asyncio.sleep(0.5)
        except KeyboardInterrupt:
            pass

        # 给一点时间让最后的响应回调执行完
        await asyncio.sleep(1)

        # 先保存数据（不管浏览器是否还活着）
        _save_result(captured)

        # 再尝试关闭浏览器（可能已经关了，忽略错误）
        try:
            await browser.close()
        except Exception:
            pass

if __name__ == "__main__":
    asyncio.run(capture())
