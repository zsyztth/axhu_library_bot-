"""
图书馆自动预约系统 — Kivy 图形化界面（Android APK 版本）
基于原 tkinter 版 library_gui.py 改写
"""
import os
import sys
import json
import threading
import time
from datetime import date as dt_date, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.button import Button
from kivy.uix.spinner import Spinner
from kivy.uix.togglebutton import ToggleButton
from kivy.uix.popup import Popup
from kivy.uix.screenmanager import ScreenManager, Screen
from kivy.core.window import Window
from kivy.clock import Clock
from kivy.metrics import dp, sp

# 尝试导入核心模块（APK 打包时需要）
try:
    from libseat_bot import LibSeatBot, _list_bookable_seats, _min_to_time
    BOT_AVAILABLE = True
except ImportError:
    BOT_AVAILABLE = False

CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")
ROOMS = ["第二自习室", "308自习室", "第三自习室", "第一自习室", "第一自习室A"]

# ==================== 颜色主题 ====================
COLOR_PRIMARY = (0.18, 0.55, 0.34, 1)       # 深绿
COLOR_PRIMARY_LIGHT = (0.22, 0.65, 0.40, 1)  # 浅绿
COLOR_ACCENT = (0.90, 0.45, 0.13, 1)         # 橙色
COLOR_BG = (0.96, 0.96, 0.96, 1)             # 浅灰背景
COLOR_WHITE = (1, 1, 1, 1)
COLOR_BLACK = (0.15, 0.15, 0.15, 1)
COLOR_GRAY = (0.5, 0.5, 0.5, 1)
COLOR_RED = (0.85, 0.25, 0.25, 1)
COLOR_SUCCESS = (0.18, 0.60, 0.35, 1)


class LogLabel(Label):
    """日志显示组件"""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.markup = True
        self.halign = 'left'
        self.valign = 'top'
        self.font_size = sp(12)
        self.color = COLOR_BLACK
        self.padding = [dp(8), dp(4)]
        self.bind(width=self._update_text)
        self._log_lines = []

    def add_log(self, msg, level="info"):
        """添加日志行"""
        timestamp = time.strftime("%H:%M:%S")
        if level == "error":
            color = "#D32F2F"
            prefix = "[ERROR]"
        elif level == "warning":
            color = "#F57C00"
            prefix = "[WARN]"
        elif level == "success":
            color = "#388E3C"
            prefix = "[OK]"
        else:
            color = "#424242"
            prefix = "[INFO]"

        line = f"[color={color}]{timestamp} {prefix}[/color] {msg}"
        self._log_lines.append(line)

        # 限制日志行数，避免内存膨胀
        if len(self._log_lines) > 500:
            self._log_lines = self._log_lines[-400:]

        self.text = "\n".join(self._log_lines)
        # 自动滚动到底部（通过触发父 ScrollView）
        self._scroll_to_bottom()

    def clear_log(self):
        """清空日志"""
        self._log_lines = []
        self.text = ""

    def _update_text(self, *args):
        self.text_size = (self.width - dp(16), None)
        self.texture_update()
        self.height = max(self.texture_size[1], dp(400))

    def _scroll_to_bottom(self):
        """延迟滚动到底部"""
        Clock.schedule_once(lambda dt: self._do_scroll(), 0.05)

    def _do_scroll(self):
        sv = self._get_parent_scrollview()
        if sv:
            sv.scroll_y = 0

    def _get_parent_scrollview(self):
        """查找父级 ScrollView"""
        widget = self.parent
        while widget:
            if isinstance(widget, ScrollView):
                return widget
            widget = widget.parent
        return None


class ConfirmPopup(Popup):
    """确认弹窗"""

    def __init__(self, title_text, message, on_confirm, on_cancel=None, **kwargs):
        super().__init__(**kwargs)
        self.title = title_text
        self.size_hint = (0.85, None)
        self.height = dp(200)
        self.auto_dismiss = False

        content = BoxLayout(orientation='vertical', padding=dp(16), spacing=dp(12))

        lbl = Label(
            text=message,
            font_size=sp(14),
            halign='center',
            valign='center',
            text_size=(None, None),
            color=COLOR_BLACK,
        )
        lbl.bind(texture_size=lambda inst, size: setattr(inst, 'text_size', size))
        content.add_widget(lbl)

        btn_layout = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(12))

        cancel_btn = Button(
            text='取消',
            background_color=COLOR_GRAY,
            background_normal='',
            font_size=sp(14),
        )
        cancel_btn.bind(on_press=lambda x: self._cancel(on_cancel))
        btn_layout.add_widget(cancel_btn)

        confirm_btn = Button(
            text='确认',
            background_color=COLOR_PRIMARY,
            background_normal='',
            font_size=sp(14),
        )
        confirm_btn.bind(on_press=lambda x: self._confirm(on_confirm))
        btn_layout.add_widget(confirm_btn)

        content.add_widget(btn_layout)
        self.add_widget(content)

    def _confirm(self, callback):
        self.dismiss()
        if callback:
            callback()

    def _cancel(self, callback):
        self.dismiss()
        if callback:
            callback()


class InfoPopup(Popup):
    """信息提示弹窗"""

    def __init__(self, title_text, message, **kwargs):
        super().__init__(**kwargs)
        self.title = title_text
        self.size_hint = (0.85, None)
        self.height = dp(180)
        self.auto_dismiss = True

        content = BoxLayout(orientation='vertical', padding=dp(16), spacing=dp(12))

        lbl = Label(
            text=message,
            font_size=sp(14),
            halign='center',
            valign='center',
            text_size=(None, None),
            color=COLOR_BLACK,
        )
        lbl.bind(texture_size=lambda inst, size: setattr(inst, 'text_size', size))
        content.add_widget(lbl)

        close_btn = Button(
            text='确定',
            background_color=COLOR_PRIMARY,
            background_normal='',
            font_size=sp(14),
            size_hint_y=None,
            height=dp(44),
        )
        close_btn.bind(on_press=self.dismiss)
        content.add_widget(close_btn)

        self.add_widget(content)


class LibraryMainScreen(Screen):
    """主界面屏幕"""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.name = 'main'
        self.cfg = self._load_config()
        self._running = False
        self.bot = None
        self._build_ui()

    def _load_config(self):
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {
            "username": "", "password": "", "room": "",
            "start_time": "auto", "date": "auto", "seat": ""
        }

    def _save_config(self):
        self.cfg["username"] = self.username_input.text.strip()
        self.cfg["password"] = self.password_input.text
        self.cfg["room"] = self.room_spinner.text
        self.cfg["date"] = "auto" if self.date_auto.active else self.date_custom_input.text.strip()
        self.cfg["start_time"] = "auto" if self.time_auto.active else self.time_custom_input.text.strip()
        self.cfg["seat"] = self.seat_input.text.strip()
        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(self.cfg, f, ensure_ascii=False, indent=4)
        except Exception as e:
            self.log_label.add_log(f"保存配置失败: {e}", "error")

    def _build_ui(self):
        outer = BoxLayout(orientation='vertical', padding=dp(10), spacing=dp(8))

        # === 标题栏 ===
        title_bar = BoxLayout(size_hint_y=None, height=dp(50), spacing=dp(8))
        title_lbl = Label(
            text='图书馆自动预约系统',
            font_size=sp(20),
            bold=True,
            color=COLOR_WHITE,
            halign='center',
            valign='center',
        )
        title_lbl.bind(texture_size=lambda inst, size: setattr(inst, 'text_size', size))
        title_bar.add_widget(title_lbl)
        title_bar.canvas.before.clear()
        with title_bar.canvas.before:
            from kivy.graphics import Color, Rectangle
            Color(*COLOR_PRIMARY)
            self.title_bg = Rectangle(pos=title_bar.pos, size=title_bar.size)
        title_bar.bind(pos=self._update_title_bg, size=self._update_title_bg)
        outer.add_widget(title_bar)

        # === 可滚动内容区 ===
        scroll_content = BoxLayout(orientation='vertical', size_hint_y=None, spacing=dp(8), padding=dp(4))
        scroll_content.bind(minimum_height=scroll_content.setter('height'))

        # --- 配置区域 ---
        cfg_grid = GridLayout(cols=1, size_hint_y=None, spacing=dp(6), padding=dp(8))
        cfg_grid.canvas.before.clear()
        with cfg_grid.canvas.before:
            from kivy.graphics import Color, RoundedRectangle
            Color(*COLOR_WHITE)
            self.cfg_bg = RoundedRectangle(pos=cfg_grid.pos, size=cfg_grid.size, radius=[dp(8)])
        cfg_grid.bind(pos=self._update_cfg_bg, size=self._update_cfg_bg)

        cfg_inner = BoxLayout(orientation='vertical', spacing=dp(8), padding=dp(4))

        # 学号
        row_user = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(8))
        row_user.add_widget(Label(text='学号：', size_hint_x=None, width=dp(65),
                                  font_size=sp(13), color=COLOR_BLACK, halign='right', valign='center'))
        self.username_input = TextInput(
            text=self.cfg.get("username", ""),
            multiline=False, font_size=sp(13),
            hint_text='请输入学号',
            write_tab=False,
        )
        row_user.add_widget(self.username_input)
        cfg_inner.add_widget(row_user)

        # 密码
        row_pwd = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(8))
        row_pwd.add_widget(Label(text='密码：', size_hint_x=None, width=dp(65),
                                 font_size=sp(13), color=COLOR_BLACK, halign='right', valign='center'))
        self.password_input = TextInput(
            text=self.cfg.get("password", ""),
            multiline=False, font_size=sp(13),
            password=True, hint_text='请输入密码',
            write_tab=False,
        )
        row_pwd.add_widget(self.password_input)
        cfg_inner.add_widget(row_pwd)

        # 房间选择
        row_room = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(8))
        row_room.add_widget(Label(text='房间：', size_hint_x=None, width=dp(65),
                                  font_size=sp(13), color=COLOR_BLACK, halign='right', valign='center'))
        default_room = self.cfg.get("room", ROOMS[0]) if self.cfg.get("room") in ROOMS else ROOMS[0]
        self.room_spinner = Spinner(
            text=default_room,
            values=ROOMS,
            size_hint_y=None, height=dp(40),
            font_size=sp(13),
            sync_height=True,
        )
        row_room.add_widget(self.room_spinner)
        cfg_inner.add_widget(row_room)

        # 日期选择
        row_date = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(6))
        row_date.add_widget(Label(text='日期：', size_hint_x=None, width=dp(58),
                                  font_size=sp(13), color=COLOR_BLACK, halign='right', valign='center'))
        self.date_auto = ToggleButton(
            text='自动(明天)', state='down' if self.cfg.get("date", "auto") == "auto" else 'normal',
            group='date_type', size_hint_x=None, width=dp(100),
            font_size=sp(11), background_color=COLOR_PRIMARY_LIGHT, background_normal='',
        )
        row_date.add_widget(self.date_auto)
        self.date_custom = ToggleButton(
            text='自定义:', group='date_type',
            state='normal' if self.cfg.get("date", "auto") == "auto" else 'down',
            size_hint_x=None, width=dp(80),
            font_size=sp(11), background_color=(0.78, 0.78, 0.78, 1), background_normal='',
        )
        row_date.add_widget(self.date_custom)
        self.date_custom_input = TextInput(
            text=self.cfg.get("date", "") if self.cfg.get("date", "auto") != "auto" else '',
            multiline=False, font_size=sp(12), hint_text='YYYY-MM-DD',
            size_hint_x=None, width=dp(110), disabled=True, write_tab=False,
        )
        row_date.add_widget(self.date_custom_input)
        self.date_auto.bind(state=lambda *a: self._on_date_toggle())
        self.date_custom.bind(state=lambda *a: self._on_date_toggle())
        cfg_inner.add_widget(row_date)

        # 时间选择
        row_time = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(6))
        row_time.add_widget(Label(text='时间：', size_hint_x=None, width=dp(58),
                                  font_size=sp(13), color=COLOR_BLACK, halign='right', valign='center'))
        self.time_auto = ToggleButton(
            text='自动', state='down' if self.cfg.get("start_time", "auto") == "auto" else 'normal',
            group='time_type', size_hint_x=None, width=dp(70),
            font_size=sp(11), background_color=COLOR_PRIMARY_LIGHT, background_normal='',
        )
        row_time.add_widget(self.time_auto)
        self.time_custom = ToggleButton(
            text='自定义:', group='time_type',
            state='normal' if self.cfg.get("start_time", "auto") == "auto" else 'down',
            size_hint_x=None, width=dp(80),
            font_size=sp(11), background_color=(0.78, 0.78, 0.78, 1), background_normal='',
        )
        row_time.add_widget(self.time_custom)
        self.time_custom_input = TextInput(
            text=self.cfg.get("start_time", "") if self.cfg.get("start_time", "auto") != "auto" else '',
            multiline=False, font_size=sp(12), hint_text='10:00',
            size_hint_x=None, width=dp(80), disabled=True, write_tab=False,
        )
        row_time.add_widget(self.time_custom_input)
        time_hint = Label(text='如 10:00', font_size=sp(10), color=COLOR_GRAY, size_hint_x=None, width=dp(60))
        row_time.add_widget(time_hint)
        self.time_auto.bind(state=lambda *a: self._on_time_toggle())
        self.time_custom.bind(state=lambda *a: self._on_time_toggle())
        cfg_inner.add_widget(row_time)

        # 座位偏好
        row_seat = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(8))
        row_seat.add_widget(Label(text='座位：', size_hint_x=None, width=dp(65),
                                  font_size=sp(13), color=COLOR_BLACK, halign='right', valign='center'))
        self.seat_input = TextInput(
            text=self.cfg.get("seat", ""),
            multiline=False, font_size=sp(13), hint_text='如 043（可选）',
            size_hint_x=None, width=dp(120), write_tab=False,
        )
        row_seat.add_widget(self.seat_input)
        seat_hint = Label(text='三位数，可选', font_size=sp(10), color=COLOR_GRAY)
        row_seat.add_widget(seat_hint)
        cfg_inner.add_widget(row_seat)

        cfg_grid.add_widget(cfg_inner)
        scroll_content.add_widget(cfg_grid)

        # --- 按钮区域 ---
        btn_row = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(8), padding=dp(4))

        self.book_btn = Button(
            text='开始预约',
            background_color=COLOR_PRIMARY, background_normal='',
            font_size=sp(14), bold=True,
        )
        self.book_btn.bind(on_press=self._on_start_booking)
        btn_row.add_widget(self.book_btn)

        self.save_btn = Button(
            text='保存配置',
            background_color=(0.30, 0.55, 0.75, 1), background_normal='',
            font_size=sp(13),
        )
        self.save_btn.bind(on_press=self._on_save_config)
        btn_row.add_widget(self.save_btn)

        self.test_btn = Button(
            text='测试登录',
            background_color=COLOR_ACCENT, background_normal='',
            font_size=sp(13),
        )
        self.test_btn.bind(on_press=self._on_test_login)
        btn_row.add_widget(self.test_btn)

        scroll_content.add_widget(btn_row)

        # 状态标签
        status_row = BoxLayout(size_hint_y=None, height=dp(28), padding=dp(4, 0))
        self.status_label = Label(text='就绪', font_size=sp(11), color=COLOR_GRAY, halign='center')
        status_row.add_widget(self.status_label)
        scroll_content.add_widget(status_row)

        # --- 日志区域 ---
        log_frame = BoxLayout(orientation='vertical', size_hint_y=None)
        log_frame.bind(minimum_height=log_frame.setter('height'))

        log_header = BoxLayout(size_hint_y=None, height=dp(32))
        log_title = Label(text='运行日志', font_size=sp(13), bold=True, color=COLOR_PRIMARY,
                          size_hint_x=None, halign='left', valign='center', padding=dp(4, 0))
        log_header.add_widget(log_title)
        clear_btn = Button(text='清空', font_size=sp(10), size_hint_x=None, width=dp(56),
                           background_color=(0.88, 0.88, 0.88, 1), background_normal='')
        clear_btn.bind(on_press=lambda x: self.log_label.clear_log())
        log_header.add_widget(clear_btn)
        log_frame.add_widget(log_header)

        self.log_label = LogLabel(size_hint_y=None)
        log_frame.add_widget(self.log_label)

        scroll_content.add_widget(log_frame)

        # 提示文字
        tip_lbl = Label(
            text='提示：每天 8:00 左右开放次日座位预约，请在此之前启动预约。',
            font_size=sp(10), color=COLOR_GRAY, size_hint_y=None, height=dp(28),
            halign='center', valign='center',
        )
        scroll_content.add_widget(tip_lbl)

        # 计算最小高度
        scroll_content.height = sum(w.height for w in scroll_content.children) + dp(300)

        sv = ScrollView(bar_width=dp(3), bar_color=(*COLOR_PRIMARY[:3], 0.5),
                        bar_inactive_color=(*COLOR_PRIMARY[:3], 0.2))
        sv.add_widget(scroll_content)
        outer.add_widget(sv)

        self.add_widget(outer)

        # 初始化日志
        if not BOT_AVAILABLE:
            Clock.schedule_once(lambda dt: self.log_label.add_log(
                "核心模块未加载（APK调试模式），部分功能不可用", "warning"), 1)

    def _update_title_bg(self, instance, value):
        self.title_bg.pos = instance.pos
        self.title_bg.size = instance.size

    def _update_cfg_bg(self, instance, value):
        self.cfg_bg.pos = instance.pos
        self.cfg_bg.size = instance.size

    def _on_date_toggle(self):
        is_custom = self.date_custom.state == 'down'
        self.date_custom_input.disabled = not is_custom
        if not is_custom:
            self.date_custom_input.text = ''

    def _on_time_toggle(self):
        is_custom = self.time_custom.state == 'down'
        self.time_custom_input.disabled = not is_custom
        if not is_custom:
            self.time_custom_input.text = ''

    def _set_ui_state(self, enabled):
        state = 'normal' if enabled else 'disabled'
        self.book_btn.disabled = not enabled
        self.test_btn.disabled = not enabled
        self.status_label.text = '运行中...' if not enabled else '就绪'
        self.status_label.color = COLOR_ACCENT if not enabled else COLOR_GRAY
        self._running = not enabled

    def _on_save_config(self, instance):
        self._save_config()
        self.log_label.add_log("配置已保存", "success")
        self.status_label.text = '配置已保存'

    def _parse_start_time(self, time_str):
        if not time_str or time_str == "auto":
            return None
        try:
            h, m = time_str.split(":")
            return int(h) * 60 + int(m)
        except Exception:
            return None

    def _on_test_login(self, instance):
        username = self.username_input.text.strip()
        password = self.password_input.text
        if not username or not password:
            InfoPopup(title_text='提示', message='请先填写学号和密码').open()
            return
        self._set_ui_state(False)
        self.log_label.clear_log()
        threading.Thread(target=self._do_test_login, args=(username, password), daemon=True).start()

    def _do_test_login(self, username, password):
        try:
            self.log_label.add_log("正在测试登录...")
            bot = LibSeatBot(username, password, headless=True)
            if bot.login():
                self.log_label.add_log("登录成功！", "success")
                bot.get_user_info()
            else:
                self.log_label.add_log("登录失败，请检查账号密码", "error")
        except Exception as e:
            self.log_label.add_log(f"登录异常: {e}", "error")
        finally:
            Clock.schedule_once(lambda dt: self._set_ui_state(True), 0.1)

    def _on_start_booking(self, instance):
        username = self.username_input.text.strip()
        password = self.password_input.text
        room = self.room_spinner.text
        if not username or not password:
            InfoPopup(title_text='提示', message='请先填写学号和密码').open()
            return
        if not room or room not in ROOMS:
            InfoPopup(title_text='提示', message='请选择房间').open()
            return

        date_str = (dt_date.today() + timedelta(days=1)).strftime("%Y-%m-%d") \
            if self.date_auto.state == 'down' else self.date_custom_input.text.strip()
        time_str = "auto" if self.time_auto.state == 'down' else self.time_custom_input.text.strip()
        seat = self.seat_input.text.strip()

        msg = f"确认预约？\n\n日期：{date_str}\n房间：{room}\n时间：{time_str}"
        if seat:
            msg += f"\n座位：{seat}"

        ConfirmPopup(
            title_text='确认预约',
            message=msg,
            on_confirm=lambda: self._confirm_booking(username, password, room, date_str, time_str, seat),
        ).open()

    def _confirm_booking(self, username, password, room_name, date_str, time_str, seat_pref):
        self._set_ui_state(False)
        self.log_label.clear_log()
        threading.Thread(target=self._do_booking,
                         args=(username, password, room_name, date_str, time_str, seat_pref),
                         daemon=True).start()

    def _do_booking(self, username, password, room_name, date_str, time_str, seat_pref):
        try:
            self.log_label.add_log("=" * 40)
            self.log_label.add_log("图书馆自动预约开始")
            self.log_label.add_log(f"  账号: {username}")
            self.log_label.add_log(f"  日期: {date_str}")
            self.log_label.add_log(f"  房间: {room_name}")
            self.log_label.add_log(f"  时间: {time_str}")
            if seat_pref:
                self.log_label.add_log(f"  首选座位: {seat_pref}")
            self.log_label.add_log("=" * 40)

            # 登录
            self.log_label.add_log("正在登录...")
            bot = LibSeatBot(username, password, headless=True)
            if not bot.login():
                self.log_label.add_log("登录失败！请检查账号密码", "error")
                return
            self.log_label.add_log("登录成功", "success")
            bot.get_user_info()

            # 查房间ID
            self.log_label.add_log("查询房间信息...")
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
                self.log_label.add_log(f"未找到房间 '{room_name}'，可选: {list(rooms.keys())}", "error")
                return

            room_id = int(rooms[room_name]["id"])
            self.log_label.add_log(f"房间: {room_name} (ID={room_id}, 空闲 {rooms[room_name]['free']})")

            if rooms[room_name]["free"] == 0:
                self.log_label.add_log(f"房间 '{room_name}' 已满！", "error")
                return

            # 查询可选座位
            preferred_start = self._parse_start_time(time_str)
            self.log_label.add_log("查询可选座位...")
            bookable = _list_bookable_seats(bot, room_id, room_name, date_str, preferred_start)

            if not bookable:
                self.log_label.add_log(f"房间 '{room_name}' 无符合时间条件的座位", "warning")
                return

            self.log_label.add_log(f"找到 {len(bookable)} 个候选座位")

            # 默认座位优先
            if seat_pref:
                for i, s in enumerate(bookable):
                    if s["name"] == seat_pref:
                        bookable.insert(0, bookable.pop(i))
                        self.log_label.add_log(f"首选座位 '{seat_pref}' 可用，优先尝试")
                        break
                else:
                    self.log_label.add_log(f"首选座位 '{seat_pref}' 不在候选列表中", "warning")

            # 逐个尝试
            for i, seat in enumerate(bookable):
                seat_id = seat["seat_id"]
                best_start = seat["start_time"]
                best_end = seat["end_time"]
                time_range = f"{_min_to_time(best_start)}-{_min_to_time(best_end)}"

                self.log_label.add_log(f"[{i+1}/{len(bookable)}] 尝试: "
                                        f"{seat.get('area','')} {seat['name']} ({time_range})")

                # 验证码
                bot._captcha_solved = False
                bot._captcha_authid = None
                self.log_label.add_log("  正在识别验证码...")
                captcha_result = bot.solve_behavioral_captcha()

                if not captcha_result or not getattr(bot, '_captcha_solved', False):
                    self.log_label.add_log("  验证码未通过，跳过", "warning")
                    continue

                # 预约
                result = bot.free_book(seat_id, date_str, best_start, best_end)
                bot._captcha_solved = False
                bot._captcha_authid = None

                if result.get("status") == "success":
                    self.log_label.add_log("=" * 40, "success")
                    self.log_label.add_log("预约成功！", "success")
                    self.log_label.add_log(f"  房间: {room_name}")
                    self.log_label.add_log(f"  座位: {seat.get('area','')} {seat['name']}")
                    self.log_label.add_log(f"  时间: {time_range}")
                    self.log_label.add_log(f"  日期: {date_str}")
                    self.log_label.add_log("=" * 40, "success")
                    Clock.schedule_once(lambda dt: InfoPopup(
                        title_text='预约成功',
                        message=f"预约成功！\n房间：{room_name}\n"
                                f"座位：{seat.get('area','')} {seat['name']}\n"
                                f"时间：{time_range}\n日期：{date_str}",
                    ).open(), 0.2)
                    return
                else:
                    err_msg = result.get("message", str(result))
                    self.log_label.add_log(f"  失败: {err_msg}", "warning")
                    if "已有" in err_msg:
                        self.log_label.add_log("已有有效预约，停止尝试")
                        return
                    if result.get("code") == "12":
                        self.log_label.add_log("Token 过期，重新登录...", "warning")
                        if bot.login():
                            self.log_label.add_log("重登成功")
                            continue
                        else:
                            break

            self.log_label.add_log(f"所有 {len(bookable)} 个候选座位均预约失败", "error")

        except Exception as e:
            self.log_label.add_log(f"预约异常: {e}", "error")
            import traceback
            self.log_label.add_log(traceback.format_exc(), "error")
        finally:
            Clock.schedule_once(lambda dt: self._set_ui_state(True), 0.1)


class LibraryApp(App):
    """Kivy 应用入口"""

    def build(self):
        Window.clearcolor = COLOR_BG
        sm = ScreenManager()
        main_screen = LibraryMainScreen()
        sm.add_widget(main_screen)
        sm.current = 'main'
        return sm

    def on_stop(self):
        """应用退出时清理"""
        pass


if __name__ == "__main__":
    LibraryApp().run()
