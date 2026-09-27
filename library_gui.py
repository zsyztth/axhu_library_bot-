"""
图书馆自动预约系统 — 图形化界面
"""
import os
import sys
import json
import threading
import time
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
from datetime import date as dt_date, timedelta
import logging

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from libseat_bot import LibSeatBot, _list_bookable_seats, _min_to_time

CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")
ROOMS = ["第二自习室", "308自习室", "第三自习室", "第一自习室", "第一自习室A"]


class LogHandler(logging.Handler):
    def __init__(self, text_widget):
        super().__init__()
        self.text_widget = text_widget

    def emit(self, record):
        msg = self.format(record)
        self.text_widget.after(0, self._append, msg)

    def _append(self, msg):
        self.text_widget.insert(tk.END, msg + "\n")
        self.text_widget.see(tk.END)


class LibraryGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("图书馆自动预约系统")
        self.root.geometry("700x680")
        self.root.resizable(True, True)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        self.cfg = self._load_config()
        self._running = False
        self._build_ui()
        self._setup_logging()
        self._init_values()

    def _load_config(self):
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        return {"username": "", "password": "", "room": "", "start_time": "auto",
                "date": "auto", "seat": ""}

    def _save_config(self):
        self.cfg["username"] = self.username_var.get()
        self.cfg["password"] = self.password_var.get()
        self.cfg["room"] = self.room_var.get()
        self.cfg["start_time"] = self.time_var.get() if self.time_var.get() != "custom" else self.custom_time_var.get()
        self.cfg["date"] = self.date_var.get() if self.date_var.get() != "custom" else self.custom_date_var.get()
        self.cfg["seat"] = self.seat_var.get()
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(self.cfg, f, ensure_ascii=False, indent=4)

    def _init_values(self):
        self.username_var.set(self.cfg.get("username", ""))
        self.password_var.set(self.cfg.get("password", ""))
        self.room_var.set(self.cfg.get("room", ROOMS[0]))
        self.seat_var.set(self.cfg.get("seat", ""))

        start = self.cfg.get("start_time", "auto")
        if start in ("auto",):
            self.time_var.set("auto")
        elif start:
            self.time_var.set("custom")
            self.custom_time_var.set(start)

        date_val = self.cfg.get("date", "auto")
        if date_val in ("auto",):
            self.date_var.set("auto")
        elif date_val:
            self.date_var.set("custom")
            self.custom_date_var.set(date_val)

    def _build_ui(self):
        main_frame = ttk.Frame(self.root, padding=15)
        main_frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(main_frame, text="图书馆自动预约系统",
                  font=("Microsoft YaHei UI", 16, "bold")).pack(pady=(0, 15))

        # --- 配置区域 ---
        cfg_frame = ttk.LabelFrame(main_frame, text="预约配置", padding=12)
        cfg_frame.pack(fill=tk.X, pady=(0, 10))

        rows = [
            ("学号：", "username_var", None, 40),
            ("密码：", "password_var", "*", 40),
        ]
        for label_text, var_name, show, width in rows:
            f = ttk.Frame(cfg_frame)
            f.pack(fill=tk.X, pady=3)
            ttk.Label(f, text=label_text, width=12).pack(side=tk.LEFT)

        self.username_var = tk.StringVar()
        self.password_var = tk.StringVar()
        ttk.Entry(cfg_frame.winfo_children()[1], textvariable=self.username_var, width=40).pack(side=tk.LEFT, padx=5)
        ttk.Entry(cfg_frame.winfo_children()[3], textvariable=self.password_var, width=40, show="*").pack(side=tk.LEFT, padx=5)

        # 重新构建（上面搞复杂了，直接重建）
        cfg_frame.destroy()
        cfg_frame = ttk.LabelFrame(main_frame, text="预约配置", padding=12)
        cfg_frame.pack(fill=tk.X, pady=(0, 10))

        self.username_var = tk.StringVar()
        self.password_var = tk.StringVar()
        self.room_var = tk.StringVar()
        self.date_var = tk.StringVar()
        self.time_var = tk.StringVar()
        self.seat_var = tk.StringVar()
        self.custom_date_var = tk.StringVar()
        self.custom_time_var = tk.StringVar()

        # 学号
        r = ttk.Frame(cfg_frame); r.pack(fill=tk.X, pady=3)
        ttk.Label(r, text="学号：", width=12).pack(side=tk.LEFT)
        ttk.Entry(r, textvariable=self.username_var, width=40).pack(side=tk.LEFT, padx=5)

        # 密码
        r = ttk.Frame(cfg_frame); r.pack(fill=tk.X, pady=3)
        ttk.Label(r, text="密码：", width=12).pack(side=tk.LEFT)
        ttk.Entry(r, textvariable=self.password_var, width=40, show="*").pack(side=tk.LEFT, padx=5)

        # 房间
        r = ttk.Frame(cfg_frame); r.pack(fill=tk.X, pady=3)
        ttk.Label(r, text="房间：", width=12).pack(side=tk.LEFT)
        cb = ttk.Combobox(r, textvariable=self.room_var, values=ROOMS, width=37, state="readonly")
        cb.pack(side=tk.LEFT, padx=5)

        # 日期
        r = ttk.Frame(cfg_frame); r.pack(fill=tk.X, pady=3)
        ttk.Label(r, text="预约日期：", width=12).pack(side=tk.LEFT)
        df = ttk.Frame(r); df.pack(side=tk.LEFT, padx=5)
        ttk.Radiobutton(df, text="自动（明天）", variable=self.date_var, value="auto",
                        command=self._on_date_change).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Radiobutton(df, text="自定义：", variable=self.date_var, value="custom",
                        command=self._on_date_change).pack(side=tk.LEFT)
        self.date_entry = ttk.Entry(df, textvariable=self.custom_date_var, width=12, state="disabled")
        self.date_entry.pack(side=tk.LEFT, padx=3)

        # 时间
        r = ttk.Frame(cfg_frame); r.pack(fill=tk.X, pady=3)
        ttk.Label(r, text="开始时间：", width=12).pack(side=tk.LEFT)
        tf = ttk.Frame(r); tf.pack(side=tk.LEFT, padx=5)
        ttk.Radiobutton(tf, text="自动", variable=self.time_var, value="auto",
                        command=self._on_time_change).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Radiobutton(tf, text="自定义：", variable=self.time_var, value="custom",
                        command=self._on_time_change).pack(side=tk.LEFT)
        self.time_entry = ttk.Entry(tf, textvariable=self.custom_time_var, width=8, state="disabled")
        self.time_entry.pack(side=tk.LEFT, padx=3)
        ttk.Label(tf, text="（如 10:00）", foreground="gray").pack(side=tk.LEFT)

        # 座位
        r = ttk.Frame(cfg_frame); r.pack(fill=tk.X, pady=3)
        ttk.Label(r, text="默认座位：", width=12).pack(side=tk.LEFT)
        ttk.Entry(r, textvariable=self.seat_var, width=10).pack(side=tk.LEFT, padx=5)
        ttk.Label(r, text="（三位数，如 043，可选）", foreground="gray").pack(side=tk.LEFT)

        # --- 按钮 ---
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill=tk.X, pady=8)

        self.book_btn = ttk.Button(btn_frame, text="开始预约", command=self._start_booking, width=16)
        self.book_btn.pack(side=tk.LEFT, padx=(0, 10))

        self.save_btn = ttk.Button(btn_frame, text="保存配置", command=self._save_and_notify, width=14)
        self.save_btn.pack(side=tk.LEFT, padx=(0, 10))

        self.test_btn = ttk.Button(btn_frame, text="测试登录", command=self._test_login, width=14)
        self.test_btn.pack(side=tk.LEFT)

        self.status_var = tk.StringVar(value="就绪")
        ttk.Label(btn_frame, textvariable=self.status_var, foreground="gray").pack(side=tk.RIGHT)

        # --- 日志 ---
        log_frame = ttk.LabelFrame(main_frame, text="运行日志", padding=5)
        log_frame.pack(fill=tk.BOTH, expand=True)

        self.log_text = scrolledtext.ScrolledText(log_frame, height=16, font=("Consolas", 10),
                                                   wrap=tk.WORD)
        self.log_text.pack(fill=tk.BOTH, expand=True)

        ttk.Label(main_frame, text="提示：每天 8:00 左右开放次日座位预约，请在此之前启动预约。",
                  foreground="gray").pack(pady=(8, 0))

    def _on_date_change(self):
        if self.date_var.get() == "custom":
            self.date_entry.config(state="normal")
        else:
            self.date_entry.config(state="disabled")

    def _on_time_change(self):
        if self.time_var.get() == "custom":
            self.time_entry.config(state="normal")
        else:
            self.time_entry.config(state="disabled")

    def _setup_logging(self):
        self.logger = logging.getLogger("LibraryGUI")
        self.logger.setLevel(logging.INFO)
        handler = LogHandler(self.log_text)
        handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s",
                                                datefmt="%H:%M:%S"))
        self.logger.addHandler(handler)

    def _save_and_notify(self):
        self._save_config()
        self.logger.info("配置已保存")
        self.status_var.set("配置已保存")

    def _set_ui_state(self, enabled):
        state = "normal" if enabled else "disabled"
        self.book_btn.config(state=state)
        self.test_btn.config(state=state)
        self.status_var.set("就绪" if enabled else "运行中...")
        self._running = not enabled

    def _on_close(self):
        if self._running:
            if not messagebox.askyesno("确认退出", "预约正在运行中，确定退出吗？"):
                return
        self.root.destroy()

    def _parse_start_time(self, time_str):
        if not time_str or time_str == "auto":
            return None
        try:
            h, m = time_str.split(":")
            return int(h) * 60 + int(m)
        except:
            return None

    def _test_login(self):
        username = self.username_var.get().strip()
        password = self.password_var.get().strip()
        if not username or not password:
            messagebox.showwarning("提示", "请先填写学号和密码")
            return
        self._set_ui_state(False)
        self.log_text.delete(1.0, tk.END)
        threading.Thread(target=self._do_test_login, args=(username, password), daemon=True).start()

    def _do_test_login(self, username, password):
        try:
            self.logger.info("正在测试登录...")
            bot = LibSeatBot(username, password, headless=True)
            if bot.login():
                self.logger.info("登录成功！")
                bot.get_user_info()
            else:
                self.logger.error("登录失败，请检查账号密码")
        except Exception as e:
            self.logger.error(f"登录异常: {e}")
        finally:
            self.root.after(0, lambda: self._set_ui_state(True))

    def _start_booking(self):
        username = self.username_var.get().strip()
        password = self.password_var.get().strip()
        room = self.room_var.get()
        if not username or not password:
            messagebox.showwarning("提示", "请先填写学号和密码")
            return
        if not room:
            messagebox.showwarning("提示", "请选择房间")
            return

        date_str = (dt_date.today() + timedelta(days=1)).strftime("%Y-%m-%d") if self.date_var.get() == "auto" else self.custom_date_var.get()
        time_str = "auto" if self.time_var.get() == "auto" else self.custom_time_var.get()
        seat = self.seat_var.get().strip()

        msg = f"确认预约？\n\n日期：{date_str}\n房间：{room}\n时间：{time_str}"
        if seat:
            msg += f"\n座位：{seat}"
        if not messagebox.askyesno("确认预约", msg):
            return

        self._set_ui_state(False)
        self.log_text.delete(1.0, tk.END)
        threading.Thread(target=self._do_booking,
                         args=(username, password, room, date_str, time_str, seat),
                         daemon=True).start()

    def _do_booking(self, username, password, room_name, date_str, time_str, seat_pref):
        try:
            self.logger.info("=" * 50)
            self.logger.info("图书馆自动预约开始")
            self.logger.info(f"  账号: {username}")
            self.logger.info(f"  日期: {date_str}")
            self.logger.info(f"  房间: {room_name}")
            self.logger.info(f"  时间: {time_str}")
            if seat_pref:
                self.logger.info(f"  首选座位: {seat_pref}")
            self.logger.info("=" * 50)

            # 登录
            self.logger.info("正在登录...")
            bot = LibSeatBot(username, password, headless=True)
            if not bot.login():
                self.logger.error("登录失败！请检查账号密码")
                return
            self.logger.info("登录成功")
            bot.get_user_info()

            # 查房间ID
            self.logger.info("查询房间信息...")
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
                self.logger.error(f"未找到房间 '{room_name}'，可选: {list(rooms.keys())}")
                return

            room_id = int(rooms[room_name]["id"])
            self.logger.info(f"房间: {room_name} (ID={room_id}, 空闲 {rooms[room_name]['free']})")

            if rooms[room_name]["free"] == 0:
                self.logger.error(f"房间 '{room_name}' 已满！")
                return

            # 查询可选座位
            preferred_start = self._parse_start_time(time_str)
            self.logger.info("查询可选座位...")
            bookable = _list_bookable_seats(bot, room_id, room_name, date_str, preferred_start)

            if not bookable:
                self.logger.warning(f"房间 '{room_name}' 无符合时间条件的座位")
                return

            self.logger.info(f"找到 {len(bookable)} 个候选座位")

            # 默认座位优先
            if seat_pref:
                for i, s in enumerate(bookable):
                    if s["name"] == seat_pref:
                        bookable.insert(0, bookable.pop(i))
                        self.logger.info(f"首选座位 '{seat_pref}' 可用，优先尝试")
                        break
                else:
                    self.logger.warning(f"首选座位 '{seat_pref}' 不在候选列表中")

            # 逐个尝试
            for i, seat in enumerate(bookable):
                seat_id = seat["seat_id"]
                best_start = seat["start_time"]
                best_end = seat["end_time"]
                time_range = f"{_min_to_time(best_start)}-{_min_to_time(best_end)}"

                self.logger.info(f"[{i+1}/{len(bookable)}] 尝试: {seat.get('area','')} {seat['name']} ({time_range})")

                # 验证码
                bot._captcha_solved = False
                bot._captcha_authid = None
                self.logger.info("  正在识别验证码...")
                captcha_result = bot.solve_behavioral_captcha()

                if not captcha_result or not getattr(bot, '_captcha_solved', False):
                    self.logger.warning(f"  验证码未通过，跳过")
                    continue

                # 预约
                result = bot.free_book(seat_id, date_str, best_start, best_end)
                bot._captcha_solved = False
                bot._captcha_authid = None

                if result.get("status") == "success":
                    self.logger.info("=" * 50)
                    self.logger.info("预约成功！")
                    self.logger.info(f"  房间: {room_name}")
                    self.logger.info(f"  座位: {seat.get('area','')} {seat['name']}")
                    self.logger.info(f"  时间: {time_range}")
                    self.logger.info(f"  日期: {date_str}")
                    self.logger.info("=" * 50)
                    self.root.after(0, lambda: messagebox.showinfo("预约成功",
                        f"预约成功！\n房间：{room_name}\n座位：{seat.get('area','')} {seat['name']}\n"
                        f"时间：{time_range}\n日期：{date_str}"))
                    return
                else:
                    err_msg = result.get("message", str(result))
                    self.logger.warning(f"  失败: {err_msg}")
                    if "已有" in err_msg:
                        self.logger.info("已有有效预约，停止尝试")
                        return
                    if result.get("code") == "12":
                        self.logger.warning("Token 过期，重新登录...")
                        if bot.login():
                            self.logger.info("重登成功")
                            continue
                        else:
                            break

            self.logger.error(f"所有 {len(bookable)} 个候选座位均预约失败")

        except Exception as e:
            self.logger.error(f"预约异常: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
        finally:
            self.root.after(0, lambda: self._set_ui_state(True))


if __name__ == "__main__":
    root = tk.Tk()
    app = LibraryGUI(root)
    root.mainloop()
