# 图书馆自动预约系统 — Android APK 打包指南

## 项目概述

将 Python 图书馆预约系统打包为 Android APK 安装包，包含完整的图形化界面（基于 Kivy 框架）。

## 文件结构

```
tushuguan/
├── library_kivy.py          # Kivy 图形界面（Android 版）
├── library_gui.py            # 原始 tkinter 界面（PC 版）
├── libseat_bot.py            # 核心业务逻辑
├── buildozer.spec            # APK 构建配置
├── build_apk.sh              # Linux/WSL 构建脚本
├── build_apk.bat             # Windows 一键构建脚本
├── requirements.txt          # Python 依赖
├── assets/
│   ├── icon.png              # 应用图标
│   ├── presplash.png         # 启动画面
│   └── icon_*.png            # 各尺寸图标
└── config.json               # 用户配置文件
```

## 方案一：Windows 一键构建（推荐）

### 前置条件
- Windows 10/11 已启用 WSL2
- 网络连接正常

### 操作步骤

1. **双击运行** `build_apk.bat`
   - 脚本会自动：
     - 安装 WSL Ubuntu（如未安装）
     - 配置完整的 Android 构建工具链
     - 编译生成 debug APK
     - 将 APK 复制到上级目录

2. **首次构建**需要下载约 3-5GB 的 SDK/NDK，耗时约 15-40 分钟
3. **后续增量编译**约 2-5 分钟

### 输出位置
```
C:\Users\PC\Desktop\打包\libraryseat-debug.apk
```

---

## 方案二：手动 WSL 构建

### 1. 安装 WSL Ubuntu
```powershell
# PowerShell（管理员）
wsl --install -d Ubuntu
# 重启电脑后，设置用户名和密码
```

### 2. 在 WSL 中执行构建
```bash
# 进入项目目录（路径需转换为 WSL 格式）
cd /mnt/c/Users/PC/Desktop/打包/tushuguan

# 赋予执行权限并运行
chmod +x build_apk.sh
bash build_apk.sh
```

### 3. 或手动逐步执行
```bash
# 更新系统
sudo apt-get update && sudo apt-get upgrade -y

# 安装依赖
sudo apt-get install -y \
    python3 python3-pip python3-dev \
    build-essential git zlib1g-dev \
    libncurses5-dev libncursesw5-dev \
    libstdc++6 pkg-config autoconf \
    libtool libffi-dev libssl-dev \
    openjdk-17-jdk-headless zip unzip ccache

# 设置 Java 环境
export JAVA_HOME=/usr/lib/jvm/java-17-openjdk-amd64
export PATH=$JAVA_HOME/bin:$PATH

# 安装 buildozer
pip3 install --user buildozer==1.5.0 cython==0.29.37
export PATH=$(python3 -c "import site; print(site.USER_BASE)")/bin:$PATH

# 构建 APK
buildozer android debug

# 输出文件在 bin/ 目录下
cp bin/*.apk /mnt/c/Users/PC/Desktop/打包/
```

---

## 方案三：使用 Docker 构建

```bash
# 使用 Kivy 官方 Docker 镜像
docker run --rm -it -v $(pwd):/home/user/src/host kivy/buildozer:latest android debug
```

---

## 方案四：在线构建服务

使用 [Kivy Launchpad](https://kivy.org/#launchpad) 在线构建：
1. 将项目打包为 zip 上传
2. 选择 Android 目标平台
3. 等待邮件通知下载 APK

---

## 应用功能说明

### GUI 功能（Kivy 版本完全复刻 tkinter 版）

| 功能 | 说明 |
|------|------|
| 学号/密码输入 | 支持 SSO 登录 |
| 房间选择 | 下拉选择自习室 |
| 日期配置 | 自动(明天) / 自定义 |
| 时间配置 | 自动 / 自定义(HH:MM) |
| 座位偏好 | 可指定首选座位号 |
| 测试登录 | 验证账号密码有效性 |
| 开始预约 | 自动完成登录→查座→验证码→预约全流程 |
| 运行日志 | 实时显示操作进度 |
| 配置保存 | 自动保存到 config.json |

### 核心依赖（已包含在 buildozer spec 中）

- `requests` — HTTP 请求
- `pycryptodome` — AES/HMAC 加密
- `beautifulsoup4` — HTML 解析
- `ddddocr` — 验证码 OCR 识别
- `opencv-python-headless` — 图像处理（验证码模板匹配）
- `numpy` — 数值计算
- `Pillow` — 图像处理
- `onnxruntime` — ddddocr 的推理引擎
- `kivy` — Android GUI 框架

---

## 发布版 APK（签名）

```bash
# 修改 buildozer.spec 中的以下字段：
android.release = True
android.signing = True
# 并配置密钥信息

# 执行发布构建
buildozer android release
```

---

## 故障排查

### 问题：WSL 安装失败
```
解决方案：确保 Windows 功能中启用了"适用于 Linux 的 Windows 子系统"
控制面板 → 程序 → 启用或关闭 Windows 功能 → 勾选 WSL → 重启
```

### 问题：Java 版本错误
```
错误：Unsupported class file major version XX
解决：确保安装 JDK 17（不是 JDK 21+）
sudo apt-get install openjdk-17-jdk-headless
export JAVA_HOME=/usr/lib/jvm/java-17-openjdk-amd64
```

### 问题：ddddocr/onnxruntime 编译失败
```
这是最常见的问题，因为 ONNX Runtime 需要为 ARM 编译。
buildozer 通常能自动处理，如果失败可尝试：

# 方法 A：降低 NDK 版本
# 在 buildozer.spec 中设置 android.ndk = 23c

# 方法 B：仅使用 arm64-v8a
# 在 buildozer.spec 中设置 android.archs = arm64-v8a

# 方法 C：手动添加 p4a recipe
# 创建 p4a_recipes/ 目录添加自定义编译配方
```

### 问题：网络超时
```
国内网络可能需要代理或镜像：
export PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
pip3 install --user buildozer
```

---

## 技术架构

```
┌─────────────────────────────┐
│      library_kivy.py        │  ← Kivy GUI 层
│  (图形界面 / 用户交互)       │
├─────────────────────────────┤
│       libseat_bot.py        │  ← 业务逻辑层
│  (SSO登录/OCR/加密/预约API)  │
├─────────────────────────────┤
│    Python-for-Android       │  ← 运行时环境
│  (Kivy + NDK + SDL2)        │
├─────────────────────────────┤
│      Android ARM64          │  ← 目标平台
└─────────────────────────────┘
```

---

## 版本信息

- **GUI 框架**: Kivy 2.3.1
- **构建工具**: Buildozer 1.5.0
- **目标 API**: Android 31 (Android 12)
- **最低 API**: Android 21 (Android 5.0)
- **架构**: arm64-v8a
- **构建日期**: 2026-06-27
