[app]

# (str) 应用版本
version = 1.0.0

# (str) 应用标题
title = 图书馆预约系统

# (str) 包名
package.name = libraryseat
package.domain = edu.axhu.library

# (str) 源代码目录（相对于 .spec 文件）
source.dir = .

# (list) 源文件
source.include_exts = py,png,jpg,kv,atlas,json,txt,onnx

# (str) 应用入口点
source.main_py = library_kivy.py

# (list) 需要包含的 Python 模块
requirements = python3,kivy,requests,pycryptodome,beautifulsoup4,ddddocr,numpy,Pillow,opencv-python-headless,onnxruntime

# (str) 自定义 Android recipe 仓库（可选）
# p4a.branch = master

# (int) 目标 Android API 版本
android.api = 31

# (int) 最小 API 版本
android.minapi = 21

# (str) 目标 SDK 版本
android.sdk = 28

# (str) NDK 版本
android.ndk = 25b

# (bool) 是否使用 --private 方式创建发布版
android.release = False

# (list) Android 权限
android.permissions = INTERNET,ACCESS_NETWORK_STATE

# (list) Android 服务（可选）
# android.services =

# (list) Android 广播接收器（可选）
# android.broadcast_receivers =

# (int) 强制 API 级别
android.force_api_level = True

# (str) Android 附加参数
# android.add_src =

# (list) Java/Android 库
# android.gradle_dependencies =

# (list) Java/Android 仓库
# android.gradle_repos =

# (str) 日志级别
log_level = 2

# (int) 日志最大行数
# log_max_lines =

# (str) 全局变量前缀
# fullscreen = 0

# (bool) 是否全屏
fullscreen = 0

# (str) 应用方向
orientation = portrait

# (bool) 是否允许调试
android.debug = True

# (list) 白名单源（可选）
# android.whitelist =

# (bool) 是否复制库而非符号链接
android.copy_libs = 1

# ==================== 打包选项 ====================

# (str) 输出目录
output.dir = ../

# (str) 签名密钥（可选，不填则使用 debug key）
# android.key_alias =
# android.keystore =
# android.key_pass =
# android.keystore_pass =

# (str) 图标文件路径
icon.filename = assets/icon.png

# (str) 横屏图标
icon.filename_landscape =

# (str) 竖屏图标
icon.filename_portrait =

# (str) 启动画面
presplash.filename = assets/presplash.png

# (str) 启动背景色
presplash.color = #2D8B57

# (str) OUYA 分类
# ouya.category =

# (list) 需要排除的文件/目录
# source.exclude_patterns =

# (str) 应用归档格式
android.archs = arm64-v8a

# (bool) 是否签署发布版本
android.signing = False

# (bool) 是否进行 zip 对齐
android.zipalign = False

# ==================== 构建选项 ====================
# (str) 构建 bootstrap
p4a.bootstrap = sdl2

# (str) 额外编译参数
# android.extra_args =
