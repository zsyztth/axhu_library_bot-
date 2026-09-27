"""
无头预约脚本 — 服务器定时任务专用
用法: python auto_book_headless.py [config.json]
适合 crontab: 0 7 * * * cd /path/to/tushuguan && python auto_book_headless.py
"""
import os
import sys
import json
import logging
from datetime import date as dt_date, timedelta

from libseat_bot import LibSeatBot, _min_to_time, _list_bookable_seats

# ====== 日志配置 ======
LOG_FILE = "auto_book.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("auto_book")


def load_config(path="config.json"):
    """加载配置文件"""
    if not os.path.exists(path):
        log.error(f"配置文件不存在: {path}")
        sys.exit(1)

    with open(path, "r", encoding="utf-8") as f:
        cfg = json.load(f)

    # 必填项检查
    for key in ["username", "password", "room"]:
        if not cfg.get(key):
            log.error(f"配置项 '{key}' 未填写")
            sys.exit(1)

    return cfg


def parse_start_time(time_str):
    """解析 HH:MM 格式开始时间，返回分钟数；'auto' 返回 None"""
    if not time_str or time_str == "auto":
        return None
    try:
        h, m = time_str.split(":")
        return int(h) * 60 + int(m)
    except:
        log.error(f"时间格式错误: {time_str}，应为 HH:MM")
        sys.exit(1)


def send_notification(webhook_url, title, content):
    """发送通知（支持飞书/企业微信/Discord webhook）"""
    if not webhook_url:
        return
    try:
        import requests
        payload = {
            "msgtype": "text",
            "text": {"content": f"{title}\n{content}"},
        }
        requests.post(webhook_url, json=payload, timeout=10)
    except Exception as e:
        log.warning(f"通知发送失败: {e}")


def main():
    cfg = load_config(sys.argv[1] if len(sys.argv) > 1 else "config.json")

    username = cfg["username"]
    password = cfg["password"]
    room_name = cfg["room"]
    start_time_str = cfg.get("start_time", "auto")
    webhook = cfg.get("webhook_url", "")

    # 日期："auto" = 明天（8 点开放后抢明天的座）
    date_str = cfg.get("date", "auto")
    if date_str == "auto":
        date_str = (dt_date.today() + timedelta(days=1)).strftime("%Y-%m-%d")

    preferred_start = parse_start_time(start_time_str)

    log.info(f"{'='*50}")
    log.info(f"自动预约开始")
    log.info(f"  账号: {username}")
    log.info(f"  日期: {date_str}")
    log.info(f"  房间: {room_name}")
    log.info(f"  开始时间: {start_time_str if start_time_str != 'auto' else '自动'}")
    log.info(f"{'='*50}")

    # ====== 登录 ======
    log.info("正在登录...")
    bot = LibSeatBot(username, password, headless=True)
    if not bot.login():
        msg = "登录失败！请检查账号密码"
        log.error(msg)
        send_notification(webhook, "图书馆预约失败", msg)
        sys.exit(1)

    log.info("登录成功！")
    bot.get_user_info()

    # ====== 查询房间 ======
    log.info("查询房间信息...")
    stats = bot.get_building_stats(1, date_str)
    data = stats.get("data", [])
    rooms = {}

    if isinstance(data, list):
        for item in data:
            if isinstance(item, dict):
                rid = item.get("roomId") or item.get("id") or item.get("room_id")
                rname = item.get("roomName") or item.get("room") or item.get("name") or item.get("room_name")
                free = item.get("freeCount") or item.get("free") or item.get("free_count", 0)
                if rid is not None:
                    rooms[rname] = {"id": rid, "free": free}

    if room_name not in rooms:
        msg = f"未找到房间 '{room_name}'\n可选: {list(rooms.keys())}"
        log.error(msg)
        send_notification(webhook, "图书馆预约失败", msg)
        sys.exit(1)

    room_id = int(rooms[room_name]["id"])
    log.info(f"房间: {room_name} (ID={room_id}, 空闲 {rooms[room_name]['free']})")

    if rooms[room_name]["free"] == 0:
        msg = f"房间 '{room_name}' 已满！"
        log.warning(msg)
        send_notification(webhook, "图书馆预约失败", msg)
        sys.exit(1)

    # ====== 查询可选座位 ======
    bookable = _list_bookable_seats(bot, room_id, room_name, date_str, preferred_start)
    if not bookable:
        msg = f"房间 '{room_name}' 无符合时间条件的座位"
        log.warning(msg)
        send_notification(webhook, "图书馆预约失败", msg)
        sys.exit(1)

    log.info(f"找到 {len(bookable)} 个候选座位")

    # ====== 默认座位优先 ======
    preferred_seat = cfg.get("seat", "").strip()
    if preferred_seat:
        # 把首选座位排到最前面
        for i, s in enumerate(bookable):
            if s["name"] == preferred_seat:
                bookable.insert(0, bookable.pop(i))
                log.info(f"默认座位 '{preferred_seat}' 可用，优先尝试")
                break
        else:
            log.warning(f"默认座位 '{preferred_seat}' 不在候选列表中（已被占用或时间不匹配）")

    log.info(f"将尝试预约...")

    # ====== 逐个尝试预约 ======
    for i, seat in enumerate(bookable):
        seat_id = seat["seat_id"]
        best_start = seat["start_time"]
        best_end = seat["end_time"]
        time_range = f"{_min_to_time(best_start)}-{_min_to_time(best_end)}"

        log.info(f"[{i+1}/{len(bookable)}] 尝试: {seat.get('area','')} {seat['name']} ({time_range})")

        # 解验证码（自动：OCR → 模板匹配 → AI → 放弃）
        bot._captcha_solved = False
        bot._captcha_authid = None
        captcha_result = bot.solve_behavioral_captcha()

        if not captcha_result or not getattr(bot, '_captcha_solved', False):
            log.warning(f"    验证码未解决，跳过此座位")
            continue

        # 预约
        result = bot.free_book(seat_id, date_str, best_start, best_end)
        bot._captcha_solved = False
        bot._captcha_authid = None

        if result.get("status") == "success":
            msg = (
                f"预约成功！\n"
                f"房间: {room_name}\n"
                f"座位: {seat.get('area','')} {seat['name']}\n"
                f"时间: {time_range}\n"
                f"日期: {date_str}"
            )
            log.info(msg)
            send_notification(webhook, "✅ 图书馆预约成功", msg)
            sys.exit(0)
        else:
            err_msg = result.get("message", str(result))
            log.warning(f"    失败: {err_msg}")
            if "已有" in err_msg:
                log.info("已有有效预约，停止尝试")
                sys.exit(0)
            if result.get("code") == "12":
                log.warning("Token 过期，尝试重登...")
                if bot.login():
                    log.info("重登成功")
                    continue
                else:
                    break

    # 全部失败
    msg = f"所有 {len(bookable)} 个候选座位均预约失败，请手动预约"
    log.error(msg)
    send_notification(webhook, "❌ 图书馆预约失败", msg)
    sys.exit(1)


def setup():
    """交互式设置默认座位：登录 → 列出座位 → 用户选 → 写入 config"""
    cfg_path = sys.argv[2] if len(sys.argv) > 2 else "config.json"
    cfg = load_config(cfg_path)

    print("=" * 50)
    print("  默认座位设置")
    print("=" * 50)

    username = cfg["username"]
    password = cfg["password"]
    room_name = cfg["room"]
    date_str = (dt_date.today() + timedelta(days=1)).strftime("%Y-%m-%d")

    print(f"房间: {room_name}")
    print(f"日期: {date_str} (明天)")
    print()

    # 登录
    print("正在登录...")
    bot = LibSeatBot(username, password, headless=True)
    if not bot.login():
        print("[!] 登录失败")
        sys.exit(1)
    print("登录成功！")
    bot.get_user_info()

    # 查房间
    stats = bot.get_building_stats(1, date_str)
    data = stats.get("data", [])
    room_id = None
    if isinstance(data, list):
        for item in data:
            if isinstance(item, dict):
                rname = item.get("roomName") or item.get("room") or item.get("name") or ""
                if rname == room_name:
                    room_id = int(item.get("roomId") or item.get("id") or item.get("room_id") or 0)
                    break

    if not room_id:
        print(f"[!] 未找到房间 '{room_name}'")
        sys.exit(1)

    # 列出所有空闲座位
    print(f"\n查询 {room_name} 明天空闲座位...")
    seats = bot.find_available_seats(room_id, date_str)
    if not seats:
        print("[!] 该房间明天暂无空闲座位")
        sys.exit(1)

    print(f"\n明天空闲座位 ({len(seats)} 个):")
    print(f"  {'#':<4} {'座位':<8} {'区域'}")
    print(f"  {'-'*4} {'-'*8} {'-'*20}")
    for i, s in enumerate(seats):
        print(f"  [{i+1}] {'':<2} {s['name']:<6} {s.get('area','')}")

    # 选默认座位
    print(f"\n请选择默认座位（部署后每天优先抢这个位置）")
    while True:
        choice = input(f"选座位 [1-{len(seats)}, 回车=不设默认座]: ").strip()
        if choice == "":
            cfg["seat"] = ""
            break
        if choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < len(seats):
                cfg["seat"] = seats[idx]["name"]
                print(f"[+] 默认座位设为: {cfg['seat']}")
                break
        print("输入无效，请重试")

    # 写入配置
    with open(cfg_path, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=4)
    print(f"[+] 配置已保存到 {cfg_path}")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--setup":
        setup()
    else:
        main()
