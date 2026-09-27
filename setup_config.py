"""
配置脚本 — 在运行主脚本前执行，预存账号密码、座位和时间偏好
用法: python setup_config.py
"""
import os
import json

CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")

DEFAULT_CONFIG = {
    "username": "",
    "password": "",
    "room": "",
    "start_time": "",
    "seat": "",
}


def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return dict(DEFAULT_CONFIG)


def save_config(cfg):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=4)
    print(f"\n[+] 配置已保存到 {CONFIG_FILE}")


def main():
    cfg = load_config()

    print("=" * 50)
    print("  图书馆预约 — 配置向导")
    print("=" * 50)
    print()
    print("按回车跳过不修改，已有值会保留")
    print()

    # 账号
    cur = cfg.get("username", "")
    mask = cur if cur else "(未设置)"
    val = input(f"学号 [{mask}]: ").strip()
    if val:
        cfg["username"] = val

    # 密码
    cur = cfg.get("password", "")
    mask = "***" if cur else "(未设置)"
    val = input(f"密码 [{mask}]: ").strip()
    if val:
        cfg["password"] = val

    # 房间
    cur = cfg.get("room", "")
    mask = cur if cur else "(未设置，运行时可手动选)"
    print(f"可选: 第二自习室 / 308自习室 / 第三自习室 / 第一自习室 / 第一自习室A")
    val = input(f"默认房间 [{mask}]: ").strip()
    if val:
        cfg["room"] = val

    # 开始时间
    cur = cfg.get("start_time", "")
    mask = cur if cur else "(未设置，运行时可手动选)"
    print(f"格式: HH:MM，如 08:00、16:00")
    val = input(f"默认开始时间 [{mask}]: ").strip()
    if val:
        cfg["start_time"] = val

    # 默认座位
    cur = cfg.get("seat", "")
    mask = cur if cur else "(未设置)"
    print(f"格式: 三位数座位号，如 043、266")
    val = input(f"默认座位 [{mask}]: ").strip()
    if val:
        cfg["seat"] = val

    save_config(cfg)

    print()
    print("现在可以运行主脚本: python libseat_bot.py")


if __name__ == "__main__":
    main()
