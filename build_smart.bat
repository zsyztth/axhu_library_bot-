@echo off
chcp 65001 >nul 2>&1
:: ============================================================
::  图书馆预约系统 — 智能构建脚本 (Windows)
::  自动尝试多种方式构建 Android APK
:: ============================================================

echo.
echo ================================================
echo   图书馆预约系统 - APK 智能构建工具 v2.0
echo ================================================
echo.

set "PROJECT_DIR=%~dp0"
set "OUTPUT_DIR=%~dp0.."

:: 检查项目文件
if not exist "%PROJECT_DIR%library_kivy.py" (
    echo [错误] 未找到 library_kivy.py
    pause & exit /b 1
)

:: ---- 方法 1: WSL + Buildozer（推荐）----
echo [方法 1] 尝试 WSL + Buildozer 构建...
wsl -l -q >nul 2>&1
if not errorlevel 1 (
    echo [OK] 检测到 WSL 发行版，开始构建...
    goto :wsl_build
) else (
    echo [跳过] WSL 未配置发行版
)

:: ---- 方法 2: 尝试安装 WSL Ubuntu ----
echo.
echo [方法 2] 尝试自动安装 WSL Ubuntu...
echo        这需要网络连接和可能的用户交互...
echo.
choice /C YN /M "是否尝试安装 WSL Ubuntu"
if errorlevel 2 goto :method_3
if errorlevel 1 (
    echo 正在安装 Ubuntu...
    wsl --install -d Ubuntu --no-launch
    if not errorlevel 1 (
        echo.
        echo 安装成功！请在弹出的窗口中完成初始化设置。
        echo 设置完成后按任意键继续构建...
        pause >nul
        goto :wsl_build
    ) else (
        echo [失败] 安装失败，尝试其他方法...
    )
)

:method_3
:: ---- 方法 3: Docker ----
echo.
echo [方法 3] 检查 Docker...
docker --version >nul 2>&1
if not errorlevel 1 (
    echo [OK] Docker 可用，使用 Docker 构建...
    docker run --rm -it -v "%PROJECT_DIR%:/home/user/src/host" kivy/buildozer:latest android debug
    if not errorlevel 1 (
        echo [成功] Docker 构建完成！
        goto :done
    )
) else (
    echo [跳过] Docker 未安装
)

:: ---- 方法 4: 在线构建服务 ----
echo.
echo [方法 4] 无法本地构建，请使用在线构建服务：
echo.
echo   方式 A: Kivy Launchpad
echo     访问 https://kivy.org/#launchpad 上传项目
echo.
echo   方式 B: GitHub Actions
echo     将项目推送到 GitHub，.github/workflows/build_apk.yml 会自动构建
echo.
echo   方式 C: 手动 Linux 环境
echo     在任何 Linux 机器上执行: bash build_apk.sh
echo.
goto :done

:wsl_build
:: ====== WSL 构建流程 ======
for %%I in ("%PROJECT_DIR%") do set "WP=%%~fI"
set "WSLP=%WP:\=/%"
set "WSLP=/mnt%c:%WSLP:~3%"

for %%I in ("%OUTPUT_DIR%") set "WO=%%~fI"
set "WSLO=%WO:\=/%"
set "WSLO=/mnt%c:%WSLO:~3%"

wsl -d Ubuntu -- bash -c '
set -e
cd "%WSLP%"
echo "============================================"
echo "  WSL Buildozer 构建启动"
echo "============================================"

# 系统依赖
sudo apt-get update -qq
sudo apt-get install -y -qq python3 python3-pip python3-dev \
    build-essential git zlib1g-dev libncurses5-dev libncursesw5-dev \
    libstdc++6 pkg-config autoconf libtool libffi-dev libssl-dev \
    openjdk-17-jdk-headless zip unzip ccache 2>&1 | tail -2

export JAVA_HOME=/usr/lib/jvm/java-17-openjdk-amd64
export PATH=$JAVA_HOME/bin:$PATH

# Python 工具
pip3 install --user buildozer==1.5.0 cython==0.29.37 2>&1 | tail -2
export PATH=$(python3 -c "import site; print(site.USER_BASE)")/bin:$PATH

# 构建
echo ""
echo ">>> 开始编译 APK..."
buildozer android debug 2>&1 | tee build_log.txt

# 输出
cp -v bin/*.apk "%WSLO%/" 2>/dev/null || true
find . -name "*.apk" -type f -exec cp -v {} "%WSLO%/" \; 2>/dev/null || true

echo ""
echo "============================================"
echo "  构建完成！APK 在: %WSLO%/"
echo "============================================
'
goto :done

:done
echo.
echo ================================================
echo   构建流程结束
echo   输出目录: %OUTPUT_DIR%
echo ================================================
pause
