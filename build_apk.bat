@echo off
chcp 65001 >nul 2>&1
setlocal enabledelayedexpansion
:: ============================================================
::  图书馆预约系统 — APK 构建启动脚本 (Windows)
::  功能: 自动配置 WSL2 + Ubuntu 并构建 Android APK
::  用法: 双击运行 或 cmd 中执行 build_apk.bat
:: ============================================================

echo ==============================================
echo   图书馆预约系统 - APK 自动构建工具
echo ==============================================
echo.

set "PROJECT_DIR=%~dp0"
set "OUTPUT_DIR=%PROJECT_DIR%.."

:: 检查项目文件
if not exist "%PROJECT_DIR%library_kivy.py" (
    echo [错误] 未找到 library_kivy.py
    echo 请确保此脚本在 tushuguan 目录中运行
    pause
    exit /b 1
)

echo [信息] 项目目录: %PROJECT_DIR%
echo [信息] 输出目录: %OUTPUT_DIR%
echo.

:: ---- 步骤 1: 检查/安装 WSL Ubuntu ----
echo [步骤 1/4] 检查 WSL 环境...
wsl -l -q >nul 2>&1
if errorlevel 1 (
    echo.
    echo [提示] 未检测到 WSL 发行版，正在安装 Ubuntu...
    echo       这可能需要几分钟，请耐心等待...
    echo.
    wsl --install -d Ubuntu --no-launch
    if errorlevel 1 (
        echo [警告] WSL 安装可能需要重启电脑后完成
        echo        请重启后再次运行此脚本
        pause
        exit /b 1
    )
    echo.
    echo [提示] Ubuntu 已安装，首次使用需要设置用户名和密码
    echo        将自动打开 WSL 窗口进行初始化...
    echo.
    wsl -d Ubuntu -e bash -c "echo WSL_READY"
    if errorlevel 1 (
        echo [提示] 请在弹出的 WSL 窗口中完成初始化（设置用户名密码）
        echo        完成后按任意键继续构建...
        pause >nul
    )
) else (
    echo [OK] WSL 已就绪
)

:: ---- 步骤 2: 复制项目到 WSL 并安装依赖 ----
echo.
echo [步骤 2/4] 准备构建环境...

:: 获取 WSL 中的路径 (转换为 Linux 格式)
for %%I in ("%PROJECT_DIR%") do set "WIN_PATH=%%~fI"
for %%I in ("%OUTPUT_DIR%") do set "WIN_OUTPUT=%%~fI"

:: 转换 Windows 路径为 WSL 路径
set "WSL_PATH=%WIN_PATH:\=/%"
set "WSL_PATH=%WSL_PATH: =\040%"
set "WSL_PATH=/mnt%c:%WSL_PATH:~3%"

set "WSL_OUTPUT=%WIN_OUTPUT:\=/%"
set "WSL_OUTPUT=%WSL_OUTPUT: =\040%"
set "WSL_OUTPUT=/mnt%c:%WSL_OUTPUT:~3%"

echo [信息] WSL 项目路径: %WSL_PATH%
echo [信息] WSL 输出路径: %WSL_OUTPUT%

:: 在 WSL 中执行构建
echo.
echo [步骤 3/4] 开始在 WSL 中构建 APK...
echo        首次构建约需 10-30 分钟（下载 SDK/NDK/编译）
echo.
wsl -d Ubuntu -- bash -c '
    set -e
    
    # 进入项目目录
    cd "%WSL_PATH%"
    
    echo "============================================"
    echo "  在 WSL Ubuntu 中执行构建"
    echo "============================================"
    
    # 更新包列表
    sudo apt-get update -qq || true
    
    # 安装系统依赖
    echo ""
    echo "[1/5] 安装系统依赖..."
    sudo apt-get install -y -qq \
        python3 python3-pip python3-dev \
        build-essential git zlib1g-dev \
        libncurses5-dev libncursesw5-dev \
        libstdc++6 pkg-config autoconf \
        libtool libffi-dev libssl-dev \
        openjdk-17-jdk-headless zip unzip ccache \
        2>&1 | tail -3
    
    # 设置 Java
    export JAVA_HOME=/usr/lib/jvm/java-17-openjdk-amd64
    export PATH=$JAVA_HOME/bin:$PATH
    echo "[OK] Java: $(java -version 2>&1 | head -1)"
    
    # 安装 Python 包
    echo ""
    echo "[2/5] 安装 Python 构建工具..."
    pip3 install --user --upgrade pip setuptools wheel 2>/dev/null || true
    pip3 install --user buildozer==1.5.0 cython==0.29.37 2>&1 | tail -3
    
    # 添加用户 bin 到 PATH
    LOCAL_BIN=$(python3 -c "import site; print(site.USER_BASE)")/bin
    export PATH=$LOCAL_BIN:$PATH
    echo "[OK] Buildozer: $(buildozer --version 2>/dev/null || echo '' )"
    
    # 初始化 Android 平台（首次）
    echo ""
    echo "[3/5] 初始化 Android 平台..."
    buildozer android clean 2>&1 | tail -3 || true
    
    # 构建 debug APK
    echo ""
    echo "[4/5] 编译 APK（耗时较长，请耐心等待）..."
    echo ""
    buildozer android debug 2>&1 | tee build_log.txt
    
    # 复制输出
    echo ""
    echo "[5/5] 复制 APK..."
    cp -v bin/*.apk "%WSL_OUTPUT%/" 2>/dev/null || true
    find . -name "*.apk" -type f 2>/dev/null | while read f; do
        cp -v "$f" "%WSL_OUTPUT%/" 2>/dev/null || true
    done
    
    echo ""
    echo "============================================"
    echo "  构建完成！"
    echo "  输出位置: %WSL_OUTPUT%/"
    echo "============================================"
'

echo.
echo [步骤 4/4] 构建流程结束
echo.
echo ==============================================
echo   请检查以下目录获取 APK 文件:
echo   %OUTPUT_DIR%
echo ==============================================
echo.
pause
