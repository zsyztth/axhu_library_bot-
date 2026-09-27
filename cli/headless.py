"""
无头预约脚本 — 服务器定时任务专用
用法: python -m cli.headless [config.json]
Cron: 1 8 * * * cd /path/to/project && python -m cli.headless
"""

import json
import logging
import os
import sys
from datetime import date as dt_date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.api_client import LibSeatAPI
from core.captcha.solver import CaptchaSolver
from core.config import get_secrets
from core.constants import CONFIG_FILE, DEFAULT_MAX_END

# ====== 日志 ======
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.FileHandler("auto_book.log", encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("headless")


def _min_to_time(minutes):
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def load_config(path=None):
    if path is None:
        path = CONFIG_FILE
    if not os.path.exists(path):
        log.error(f"配置文件不存在: {path}")
        sys.exit(1)
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def send_notification(webhook_url, title, content):
    if not webhook_url:
        return
    try:
        import requests
        payload = {"msgtype": "text", "text": {"content": f"{title}\n{content}"}}
        requests.post(webhook_url, json=payload, timeout=10)
    except Exception as e:
        log.warning(f"通知发送失败: {e}")


def _list_bookable_seats(api, room_id, room_name, date_str, preferred_start):
    """列出符合条件的座位（无头模式，精简输出）"""
    seats = api.find_available_seats(room_id, date_str)
    if not seats:
        return []

    bookable = []
    for seat in seats:
        seat_id = seat["seat_id"]
        start_times = api.get_start_times(seat_id, date_str)
        if start_times.get("status") != "success":
            continue
        available_starts = start_times.get("data", {}).get("startTimes", [])
        if not available_starts:
            continue

        best_start = None
        if preferred_start is not None:
            for t in available_starts:
                tid = t.get("id", "0") if isinstance(t, dict) else str(t)
                if tid == "now":
                    continue
                if int(tid) >= preferred_start:
                    best_start = int(tid)
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

        end_times = api.get_end_times(seat_id, date_str, best_start)
        available_ends = (
            end_times.get("data", {}).get("endTimes", [])
            if end_times.get("status") == "success"
            else []
        )
        best_end = None
        for t in reversed(available_ends):
            tid = t.get("id", "0") if isinstance(t, dict) else str(t)
            if int(tid) <= DEFAULT_MAX_END:
                best_end = int(tid)
                break
        if best_end is None and available_ends:
            tid = available_ends[-1].get("id", "0") if isinstance(available_ends[-1], dict) else str(available_ends[-1])
            best_end = int(tid)
        if best_end is None:
            best_end = best_start + 60

        bookable.append({**seat, "start_time": best_start, "end_time": best_end})

    if preferred_start is not None:
        bookable.sort(key=lambda s: (
            0 if s["start_time"] == preferred_start else 1,
            s["start_time"],
            int(s["name"]) if s["name"].isdigit() else 9999,
        ))
    else:
        bookable.sort(key=lambda s: (
            s["start_time"],
            int(s["name"]) if s["name"].isdigit() else 9999,
        ))

    return bookable


def main():
    cfg_path = sys.argv[1] if len(sys.argv) > 1 else CONFIG_FILE
    cfg = load_config(cfg_path)
    secrets = get_secrets()

    username = secrets["username"] or cfg.get("username", "")
    password = secrets["password"] or cfg.get("password", "")
    room_name = cfg.get("room", "")
    start_time_str = cfg.get("start_time", "auto")
    webhook = secrets.get("webhook_url", "")
    preferred_seat = cfg.get("seat", "")

    if not username or not password:
        log.error("账号密码未设置（config.json 或环境变量）")
        sys.exit(1)

    # 日期
    date_str = cfg.get("date", "auto")
    if date_str == "auto":
        date_str = (dt_date.today() + timedelta(days=1)).strftime("%Y-%m-%d")

    # 解析时间
    preferred_start = None
    if start_time_str and start_time_str != "auto":
        try:
            h, m = start_time_str.split(":")
            preferred_start = int(h) * 60 + int(m)
        except ValueError:
            log.error(f"时间格式错误: {start_time_str}")
            sys.exit(1)

    log.info(f"{'='*50}")
    log.info(f"自动预约开始")
    log.info(f"  账号: {username}")
    log.info(f"  日期: {date_str}")
    log.info(f"  房间: {room_name}")
    log.info(f"  开始时间: {start_time_str}")
    log.info(f"{'='*50}")

    # 登录
    log.info("正在登录...")
    api = LibSeatAPI(username, password)
    if not api.login():
        msg = "登录失败！请检查账号密码"
        log.error(msg)
        send_notification(webhook, "图书馆预约失败", msg)
        sys.exit(1)
    log.info("登录成功！")
    api.get_user_info()

    # 查房间
    stats = api.get_building_stats(1, date_str)
    data = stats.get("data", [])
    rooms = {}
    if isinstance(data, list):
        for item in data:
            if isinstance(item, dict):
                rname = item.get("roomName") or item.get("room") or item.get("name") or ""
                rid = item.get("roomId") or item.get("id") or item.get("room_id")
                free = item.get("freeCount") or item.get("free") or 0
                if rid is not None and rname:
                    rooms[rname] = {"id": rid, "free": free}

    if room_name not in rooms:
        msg = f"未找到房间 '{room_name}'\n可选: {list(rooms.keys())}"
        log.error(msg)
        send_notification(webhook, "图书馆预约失败", msg)
        sys.exit(1)

    room_id = int(rooms[room_name]["id"])
    if rooms[room_name]["free"] == 0:
        msg = f"房间 '{room_name}' 已满！"
        log.warning(msg)
        send_notification(webhook, "图书馆预约失败", msg)
        sys.exit(1)

    log.info(f"房间: {room_name} (ID={room_id}, 空闲 {rooms[room_name]['free']})")

    # 查座位
    bookable = _list_bookable_seats(api, room_id, room_name, date_str, preferred_start)
    if not bookable:
        msg = f"房间 '{room_name}' 无符合时间条件的座位"
        log.warning(msg)
        send_notification(webhook, "图书馆预约失败", msg)
        sys.exit(1)

    # 默认座位优先
    if preferred_seat:
        for i, s in enumerate(bookable):
            if s["name"] == preferred_seat:
                bookable.insert(0, bookable.pop(i))
                log.info(f"默认座位 '{preferred_seat}' 可用，优先尝试")
                break
        else:
            log.warning(f"默认座位 '{preferred_seat}' 不在候选列表中")

    log.info(f"找到 {len(bookable)} 个候选座位，将尝试预约...")

    # 逐个尝试
    solver = CaptchaSolver(api)
    for i, seat in enumerate(bookable):
        seat_id = seat["seat_id"]
        best_start = seat["start_time"]
        best_end = seat["end_time"]
        slot = f"{_min_to_time(best_start)}-{_min_to_time(best_end)}"

        log.info(f"[{i+1}/{len(bookable)}] 尝试: {seat.get('area','')} {seat['name']} ({slot})")

        api._captcha_solved = False
        api._captcha_authid = None
        captcha_result = solver.solve(headless=True)

        if not captcha_result or not api._captcha_solved:
            log.warning("    验证码未解决，跳过此座位")
            continue

        result = api.free_book(seat_id, date_str, best_start, best_end)
        api._captcha_solved = False
        api._captcha_authid = None

        if result.get("status") == "success":
            msg = (
                f"预约成功！\n"
                f"房间: {room_name}\n"
                f"座位: {seat.get('area','')} {seat['name']}\n"
                f"时间: {slot}\n"
                f"日期: {date_str}"
            )
            log.info(msg)
            send_notification(webhook, "✅ 图书馆预约成功", msg)
            sys.exit(0)
        else:
            err = result.get("message", str(result))
            log.warning(f"    失败: {err}")
            if "已有" in err:
                log.info("已有有效预约，停止尝试")
                sys.exit(0)

    msg = f"所有 {len(bookable)} 个候选座位均预约失败，请手动预约"
    log.error(msg)
    send_notification(webhook, "❌ 图书馆预约失败", msg)
    sys.exit(1)


if __name__ == "__main__":
    main()
