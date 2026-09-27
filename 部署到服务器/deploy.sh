#!/bin/bash
# 图书馆预约系统 — 服务器一键部署
# 用法: chmod +x deploy.sh && ./deploy.sh

set -e

echo "====================================="
echo "  图书馆自动预约 - 服务器部署"
echo "====================================="

# Python 检查
if ! command -v python3 &>/dev/null; then
    echo "[!] 请先安装 Python 3.10+"
    echo "    Ubuntu: sudo apt install python3 python3-pip"
    echo "    CentOS: sudo yum install python3 python3-pip"
    exit 1
fi

echo "[*] Python: $(python3 --version)"

# 安装依赖
echo "[*] 安装 Python 依赖..."
pip3 install -r requirements.txt

# 检查配置文件
if [ ! -f "config.json" ]; then
    echo "[!] 配置文件 config.json 不存在，正在创建模板..."
    cat > config.json << 'EOF'
{
    "username": "你的学号",
    "password": "你的密码",
    "date": "auto",
    "room": "第二自习室",
    "start_time": "10:00",
    "seat": "",
    "log_file": "auto_book.log",
    "webhook_url": ""
}
EOF
    echo "[!] 请编辑 config.json 填入你的账号密码！"
    exit 1
fi

# 测试
echo ""
echo "[*] 测试预约脚本（不实际抢座）..."
python3 -c "
from libseat_bot import LibSeatBot
from auto_book_headless import load_config
cfg = load_config('config.json')
print(f'配置: 账号={cfg[\"username\"]}, 房间={cfg[\"room\"]}, 时间={cfg.get(\"start_time\",\"auto\")}')
print('依赖加载 OK')
"

echo ""
echo "====================================="
echo "  部署完成！"
echo "====================================="
echo ""
echo "手动测试: python3 auto_book_headless.py"
echo ""
echo "设置定时任务 (每天早上 8:01):"
echo "  crontab -e"
echo "  1 8 * * * cd $(pwd) && python3 auto_book_headless.py >> cron.log 2>&1"
echo ""
