#!/bin/bash
# ============================================================
#  图书馆预约系统 — Android APK 自动构建脚本
#  环境: Ubuntu/Debian (WSL2 或原生 Linux)
#  用法: bash build_apk.sh
#  输出: ../libraryseat-debug.apk
# ============================================================
set -e

echo "=============================================="
echo "  图书馆预约系统 APK 构建脚本"
echo "=============================================="

# ---- 颜色定义 ----
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

info()    { echo -e "${GREEN}[INFO]${NC} $1"; }
warn()    { echo -e "${YELLOW}[WARN]${NC} $1"; }
error()   { echo -e "${RED}[ERROR]${NC} $1"; exit 1; }

# ---- 检测项目目录 ----
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$SCRIPT_DIR"
OUTPUT_DIR="$(dirname "$SCRIPT_DIR")"

if [ ! -f "$PROJECT_DIR/library_kivy.py" ]; then
    error "未找到 library_kivy.py，请确保脚本在项目根目录运行"
fi

info "项目目录: $PROJECT_DIR"
info "输出目录: $OUTPUT_DIR"

# ---- 1. 安装系统依赖 ----
echo ""
info "步骤 1/6: 检查并安装系统依赖..."

if ! command -v python3 &>/dev/null; then
    warn "Python3 未安装，正在安装..."
    sudo apt-get update -qq
    sudo apt-get install -y -qq python3 python3-pip python3-dev
fi

info "Python3: $(python3 --version)"

# Buildozer 系统依赖
BUILD_DEPS="build-essential git zlib1g-dev libncurses5-dev \
libncursesw5-dev libstdc++6 pkg-config autoconf libtool \
libffi-dev libssl-dev openjdk-17-jdk-headless \
zip unzip ccache"

sudo apt-get update -qq
sudo apt-get install -y -qq $BUILD_DEPS

# 设置 JAVA_HOME
export JAVA_HOME=/usr/lib/jvm/java-17-openjdk-amd64
export PATH=$JAVA_HOME/bin:$PATH
info "Java: $(java -version 2>&1 | head -1)"

# ---- 2. 安装 Python 依赖 ----
echo ""
info "步骤 2/6: 安装 Python 依赖..."

pip3 install --user --upgrade pip setuptools wheel 2>/dev/null || true

# buildozer 及其依赖
pip3 install --user buildozer==1.5.0 cython==0.29.37 2>&1 | tail -3

# 将用户 pip 路径加入 PATH
LOCAL_BIN=$(python3 -c "import site; print(site.USER_BASE)")/bin
export PATH=$LOCAL_BIN:$PATH

info "Buildozer: $(buildozer --version 2>/dev/null || echo '安装中...')"

# ---- 3. 初始化 Android SDK/NDK ----
echo ""
info "步骤 3/6: 初始化 Android SDK/NDK（首次运行需要下载约 2-4GB）..."

cd "$PROJECT_DIR"

# 首次运行会自动下载 SDK/NDK
buildozer android debug 2>&1 | head -50 || true

# 检查是否需要初始化
if [ ! -d "$HOME/.buildozer/android/platform" ]; then
    info "首次构建，正在初始化 Android 平台..."
    buildozer android clean 2>&1 | tail -5 || true
fi

# ---- 4. 构建 APK ----
echo ""
info "步骤 4/6: 开始编译 APK（耗时约 10-30 分钟）..."
echo ""

# 使用 buildozer 构建 debug APK
buildozer android debug 2>&1 | tee "$PROJECT_DIR/build_log.txt"

BUILD_RESULT=${PIPESTATUS[0]}

# ---- 5. 复制输出文件 ----
echo ""
info "步骤 5/6: 复制 APK 到输出目录..."

APK_PATTERN="$PROJECT_DIR/bin/*.apk"
if ls $APK_PATTERN 1>/dev/null 2>&1; then
    cp $APK_PATTERN "$OUTPUT_DIR/" 2>/dev/null || true
    info "APK 文件已复制到: $OUTPUT_DIR/"
    ls -la "$OUTPUT_DIR"/*.apk 2>/dev/null || warn "未找到生成的 APK"
else
    # 尝试其他可能的位置
    find "$PROJECT_DIR" -name "*.apk" -type f 2>/dev/null | while read apk; do
        cp "$apk" "$OUTPUT_DIR/" 2>/dev/null || true
        info "找到 APK: $apk"
    done
fi

# ---- 6. 完成 ----
echo ""
info "步骤 6/6: 构建完成！"
echo ""
echo "=============================================="
echo "  输出位置: $OUTPUT_DIR/"
echo "  日志文件: $PROJECT_DIR/build_log.txt"
echo "=============================================="
echo ""
echo "如需发布版 APK，请执行:"
echo "  cd $PROJECT_DIR && buildozer android release"
echo ""
