"""
交互式命令行 — 图书馆座位预约
用法: python -m cli.interactive
"""

import json
import os
import sys
from datetime import date as dt_date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.api_client import LibSeatAPI
from core.captcha.solver import CaptchaSolver
from core.constants import (
    CONFIG_FILE,
    MAX_BOOK_RETRIES,
    PRESET_ROOMS,
    TIME_PRESETS,
    DEFAULT_MAX_END,
)


# ====== 工具函数 ======

def _min_to_time(minutes):
    """分钟 → HH:MM"""
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def _load_user_config():
    """加载当前目录下的 config.json"""
    cfg_path = os.path.join(os.getcwd(), CONFIG_FILE)
    if os.path.exists(cfg_path):
        try:
            with open(cfg_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    return {}


def _pick_room(rooms):
    """选房间：预设房间优先展示"""
    by_name = {r["name"]: r for r in rooms}
    ordered = []
    seen = set()
    for pname in PRESET_ROOMS:
        if pname in by_name:
            ordered.append(by_name[pname])
            seen.add(pname)
    for r in rooms:
        if r["name"] not in seen:
            ordered.append(r)

    print("\n可选房间:")
    for i, r in enumerate(ordered):
        status = f"空闲 {r['free']}/{r['total']}" if r["free"] > 0 else "已满"
        print(f"  [{i+1}] {r['name']}   ({status})")

    while True:
        choice = input(f"\n选房间 [1-{len(ordered)}]: ").strip()
        if choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < len(ordered):
                r = ordered[idx]
                if r["free"] == 0:
                    print("该房间已满，请重新选择")
                    continue
                return r
        print("输入无效，请重试")


def _pick_time():
    """选开始时间"""
    print("\n请选择开始时间（结束时间统一 22:00）:")
    for key, (mins, label) in TIME_PRESETS.items():
        print(f"  [{key}] {label}")
    print("  [5] 自定义")
    print("  [6] 自动（最早可用）")

    while True:
        choice = input("选择 [1-6]: ").strip()
        if choice in TIME_PRESETS:
            return TIME_PRESETS[choice][0]
        elif choice == "5":
            t = input("输入开始时间 (如 8:00, 16:00): ").strip()
            try:
                h, m = t.split(":")
                return int(h) * 60 + int(m)
            except ValueError:
                print("格式错误，请用 HH:MM 格式")
        elif choice == "6":
            return None
        else:
            print("输入无效，请重试")


def _list_bookable_seats(api, room_id, room_name, date_str, preferred_start):
    """列出符合条件的座位"""
    print(f"\n[*] 查询 {room_name} 空闲座位...")
    seats = api.find_available_seats(room_id, date_str)
    if not seats:
        print("[!] 该房间无空闲座位")
        return []

    total = len(seats)
    print(f"[+] 找到 {total} 个空闲座位，正在检查时间可用性...")
    last_pct = -1

    bookable = []
    for i, seat in enumerate(seats):
        pct = (i + 1) * 100 // total
        if pct >= last_pct + 10:
            print(f"    进度: {i+1}/{total} ({pct}%)")
            last_pct = pct

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
        available_ends = []
        if end_times.get("status") == "success":
            available_ends = end_times.get("data", {}).get("endTimes", [])

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

        bookable.append({
            **seat,
            "start_time": best_start,
            "end_time": best_end,
        })

    # 排序：精确匹配优先 → 开始时间升序 → 座位号升序
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

    print(f"    完成: {len(bookable)}/{total} 个座位符合条件")
    return bookable


def _pick_seat(bookable):
    """选座位"""
    if not bookable:
        return None

    first_start = _min_to_time(bookable[0]["start_time"])
    print(f"\n符合条件（{first_start} 起）的座位:")
    print(f"  {'#':<4} {'座位':<10} {'区域':<16} {'时段'}")
    print(f"  {'-'*4} {'-'*10} {'-'*16} {'-'*18}")
    for i, s in enumerate(bookable):
        slot = f"{_min_to_time(s['start_time'])}-{_min_to_time(s['end_time'])}"
        print(f"  [{i+1}] {'':<2} {s['name']:<8} {s.get('area',''):<16} {slot}")

    while True:
        choice = input(f"\n选座位 [1-{len(bookable)}, q=退出]: ").strip()
        if choice.lower() == "q":
            return None
        if choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < len(bookable):
                return bookable[idx]
        print("输入无效，请重试")


# ====== 主函数 ======

def main():
    print("=" * 50)
    print("  图书馆座位自动预约系统 v2.0")
    print("=" * 50)

    # 检测配置文件
    cfg = _load_user_config()
    use_cfg = False
    cfg_user = ""
    cfg_pw = ""
    cfg_room = ""
    cfg_time = ""
    cfg_seat = ""

    if cfg:
        print(f"\n[!] 检测到配置文件 config.json")
        print(f"    学号: {cfg.get('username', '(未设)')}")
        print(f"    房间: {cfg.get('room', '(未设)')}")
        print(f"    时间: {cfg.get('start_time', '(未设)')}")
        print(f"    座位: {cfg.get('seat', '(未设)')}")
        choice = input("\n是否读取配置？[回车=是 / 0=否]: ").strip()
        if choice != "0":
            use_cfg = True
            cfg_user = cfg.get("username", "")
            cfg_pw = cfg.get("password", "")
            cfg_room = cfg.get("room", "")
            cfg_time = cfg.get("start_time", "")
            cfg_seat = cfg.get("seat", "")
            print("[+] 已读取配置")

    # 学号
    if cfg_user:
        username = cfg_user
        print(f"学号: {username}")
    else:
        username = input("学号: ").strip()

    # 密码
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
    api = LibSeatAPI(username, password)
    if not api.login():
        print("\n[!] 登录失败，请检查账号密码")
        return
    print("\n[+] 登录成功！")
    api.get_user_info()

    # 查询房间
    print("\n[*] 查询房间信息...")
    stats = api.get_building_stats(1, date_str)
    data = stats.get("data", [])
    rooms = []

    if isinstance(data, list):
        for item in data:
            if isinstance(item, dict):
                rid = item.get("roomId") or item.get("id") or item.get("room_id")
                rname = item.get("roomName") or item.get("room") or item.get("name") or ""
                free = item.get("freeCount") or item.get("free") or 0
                total = item.get("totalSeats") or item.get("total") or 0
                if rid is not None:
                    rooms.append({"id": rid, "name": rname, "free": free, "total": total})

    if not rooms:
        print("[!] 无法获取房间数据")
        return

    # 选房间
    if cfg_room:
        matched = [r for r in rooms if r["name"] == cfg_room]
        if matched and matched[0]["free"] > 0:
            selected = matched[0]
            print(f"\n[+] 使用配置房间: {cfg_room}")
        else:
            selected = _pick_room(rooms)
    else:
        selected = _pick_room(rooms)

    room_id = int(selected["id"])
    room_name = selected["name"]

    # 选时间
    if cfg_time:
        try:
            h, m = cfg_time.split(":")
            preferred_start = int(h) * 60 + int(m)
            print(f"[+] 使用配置时间: {cfg_time}, 结束时间: 22:00")
        except ValueError:
            preferred_start = _pick_time()
    else:
        preferred_start = _pick_time()

    if preferred_start is not None:
        print(f"[+] 开始时间: {_min_to_time(preferred_start)}, 结束时间: 22:00")
    else:
        print("[+] 开始时间: 自动（最早可用）, 结束时间: 22:00")

    # 列出座位
    bookable = _list_bookable_seats(api, room_id, room_name, date_str, preferred_start)
    if not bookable:
        print("\n[!] 没有符合条件的座位")
        return

    # 默认座位
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

    # 解验证码 + 预约
    solver = CaptchaSolver(api)
    for book_try in range(MAX_BOOK_RETRIES):
        if book_try > 0:
            print(f"\n[*] 重试预约 ({book_try+1}/{MAX_BOOK_RETRIES})...")

        captcha_result = solver.solve(headless=False)
        if not captcha_result or not api._captcha_solved:
            if book_try < MAX_BOOK_RETRIES - 1:
                r = input("[!] 验证码未解决，重试？[Y/n]: ").strip().lower()
                if r == "n":
                    return
                continue
            else:
                print("[!] 验证码未解决，预约取消")
                return

        result = api.free_book(seat_id, date_str, best_start, best_end)
        api._captcha_solved = False
        api._captcha_authid = None

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
            msg = result.get("message", str(result))
            print(f"\n[!] 预约失败: {msg}")
            if "已有" in msg:
                return
            if book_try < MAX_BOOK_RETRIES - 1:
                r = input("重试？[Y/n]: ").strip().lower()
                if r == "n":
                    return
            else:
                print("[!] 已达最大重试次数")


if __name__ == "__main__":
    main()
