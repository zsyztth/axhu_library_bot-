# 图书馆预约系统 — APK 打包完成报告

## 执行摘要

已将 Python 图书馆自动预约系统完整转换为 **Android APK 可打包项目**，包含基于 **Kivy 框架**的全功能图形化界面。

**当前状态**: 所有源码、配置、构建脚本均已就绪。由于 Windows 环境限制（需 Linux 工具链编译 Android NDK），APK 最终编译需要在 WSL/Linux/Docker/CI 环境中执行。

---

## 已完成的产出文件

### 核心应用文件

| 文件 | 大小 | 说明 |
|------|------|------|
| `library_kivy.py` | 28.6 KB | **Kivy 图形界面（Android 版）** - 完整复刻 tkinter 版全部功能 |
| `buildozer.spec` | 2.6 KB | Buildozer APK 构建配置 |
| `assets/icon.png` | 3.3 KB | 应用图标 (512x512) |
| `assets/presplash.png` | 32.1 KB | 启动画面 (1080x1920) |
| `assets/icon.ico` | 15.6 KB | Windows 图标（备用） |

### 构建脚本

| 文件 | 说明 |
|------|------|
| `build_apk.sh` | Linux/WSL 一键构建脚本（Bash） |
| `build_apk.bat` | Windows 构建 launcher（调用 WSL） |
| `build_smart.bat` | 智能构建脚本（多方案自动尝试） |
| `library_win.spec` | PyInstaller Windows 打包配置（备用） |
| `.github/workflows/build_apk.yml` | GitHub Actions CI/CD 自动构建 |

### 文档

| 文件 | 说明 |
|------|------|
| `APK_BUILD_GUIDE.md` | 完整构建指南（4 种方案详解） |

---

## Kivy GUI 功能清单

### 已实现的功能（与原 tkinter 版完全对等）

- [x] 学号/密码输入框
- [x] 房间下拉选择（5个自习室）
- [x] 日期配置：自动(明天) / 自定义
- [x] 时间配置：自动 / 自定义(HH:MM)
- [x] 座位偏好输入（3位数字）
- [x] **开始预约** 按钮 → 完整流程：登录→查房→验证码→逐座尝试预约
- [x] **测试登录** 按钮 → 验证账号密码
- [x] **保存配置** 按钮 → 持久化到 config.json
- [x] 运行日志面板（带颜色标记：INFO/WARN/ERROR/SUCCESS）
- [x] 清空日志按钮
- [x] 状态栏显示
- [x] 确认弹窗（预约前二次确认）
- [x] 成功弹窗（预约结果展示）
- [x] 配置自动加载（启动时读取 config.json）
- [x] 多线程执行（UI 不阻塞）

### UI 适配优化（针对手机端）

- 竖屏布局（portrait）
- 触控友好的按钮尺寸
- ScrollView 支持内容滚动
- 自适应字体大小（sp 单位）
- 深绿色主题配色（#2D8B57）
- 启动画面（presplash）

---

## 快速构建指南

### 方法一：WSL 一键构建（推荐）

```powershell
# 1. 确保 WSL Ubuntu 已安装（如未安装会提示安装）
# 2. 双击运行 build_smart.bat
#    或在 tushuguan 目录下执行：
cd C:\Users\PC\Desktop\打包\tushuguan
.\build_smart.bat
```

### 方法二：手动 WSL 构建

```bash
# 1. 安装 WSL Ubuntu（管理员 PowerShell）
wsl --install -d Ubuntu
# 重启后设置用户名密码

# 2. 在 WSL 中执行
cd /mnt/c/Users/PC/Desktop/打包/tushuguan
chmod +x build_apk.sh && bash build_apk.sh
```

### 方法三：GitHub Actions（零配置）

1. 将 `tushuguan/` 目录推送到 GitHub 仓库
2. GitHub Actions 会自动检测 `.github/workflows/build_apk.yml`
3. 在 Actions 页面触发构建
4. 从 Artifacts 下载 APK

### 方法四：Docker 构建

```bash
docker run --rm -it -v $(pwd):/home/user/src/host \
  kivy/buildozer:latest android debug
```

---

## 技术细节

### 依赖清单（buildozer.spec 中配置）

```
python3, kivy, requests, pycryptodome, beautifulsoup4,
ddddocr, numpy, Pillow, opencv-python-headless, onnxruntime
```

### 目标平台参数

| 参数 | 值 |
|------|-----|
| Target API | 31 (Android 12) |
| Min API | 21 (Android 5.0) |
| Architecture | arm64-v8a |
| Bootstrap | sdl2 |
| Orientation | portrait |

### 文件依赖关系

```
library_kivy.py (入口)
├── libseat_bot.py (核心业务)
│   ├── requests (HTTP)
│   ├── pycryptodome (AES/HMAC)
│   ├── beautifulsoup4 (HTML解析)
│   ├── ddddocr (OCR验证码)
│   │   └── onnxruntime (推理引擎)
│   ├── opencv-python-headless (图像处理)
│   └── numpy (数值计算)
├── config.json (用户配置)
└── assets/ (图标资源)
```

---

## 预期输出

构建成功后，APK 文件位于：

```
C:\Users\PC\Desktop\打包\libraryseat-debug.apk
```

或

```
tushuguan/bin\libraryseat-debug.apk
```

---

## 故障排查速查

| 问题 | 解决方案 |
|------|----------|
| WSL 未安装 | `wsl --install -d Ubuntu` + 重启 |
| Java 版本错误 | 安装 JDK 17（非21+） |
| ddddocr 编译失败 | 使用 `android.ndk = 23c` 或仅 `arm64-v8a` |
| 网络超时 | 设置 pip 镜像: `PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple` |
| Git clone 失败 | 检查代理/防火墙设置，或使用 GitHub 镜像 |

---

## 项目版本信息

- **GUI 框架**: Kivy 2.3.1
- **构建工具**: Buildozer 1.6.0 + python-for-android 2026.05.09
- **创建日期**: 2026-06-27
- **原始项目**: library_gui.py (tkinter 版, 18KB)
- **转换产物**: library_kivy.py (Kivy 版, 29KB)
