# AXHU 图书馆座位自动预约系统

[![Python](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

> 🌐 [English](README_EN.md) | 中文

大学图书馆座位自动预约系统。支持 SSO CAS 认证登录、多策略验证码自动求解（OCR + 模板匹配 + AI 视觉）、基于 cron 的服务器无头部署。

## 功能特性

- **SSO 单点登录** — 自动完成 CAS 认证流程，AES-128-ECB 密码加密 + 验证码 OCR
- **HMAC 请求签名** — 逆向工程还原的 HMAC-SHA256 请求签名，所有 API 调用通过校验
- **多策略验证码求解** — 渐进降级：
  1. 文字验证码 OCR（ddddocr）
  2. 模板匹配（多通道 CV：灰度 + 边缘 + 二值化，66 个匹配管线）
  3. AI 视觉（豆包 / GPT-4V / 通义千问 VL 兼容）
  4. 手动点击（仅交互模式）
- **智能选座** — 按房间、时间、首选座位过滤；按匹配度排序
- **双模式运行** — 本地交互式 CLI + 服务器 cron 无头模式
- **可配置** — JSON 配置文件 + 环境变量；密钥永不硬编码
- **Webhook 通知** — 支持飞书 / 企业微信 / Discord，预约成功或失败即时通知

## 项目结构

```
axhu_library_bot/
├── core/                   # 核心库
│   ├── api_client.py       # SSO 登录、HMAC 签名、REST API 封装
│   ├── config.py           # 统一配置管理（env 优先于 config.json）
│   ├── constants.py        # 常量定义（无魔法数字）
│   ├── vision_solver.py    # AI 视觉验证码求解（豆包/GPT-4V）
│   └── captcha/
│       └── solver.py       # 多策略验证码求解编排器
├── cli/                    # 命令行界面
│   ├── interactive.py      # 交互式终端模式
│   └── headless.py         # 无头/服务器 cron 模式
├── setup_config.py         # 配置向导（首次使用运行）
├── config.example.json     # 配置文件模板
├── requirements.txt        # Python 依赖
├── Dockerfile              # Docker 镜像构建
├── docker-compose.yml      # Docker Compose 一键部署
├── README.md               # 英文文档
└── README_CN.md            # 中文文档（本文件）
```

## 快速开始

### 环境要求

- Python 3.10+
- 系统字体支持（ddddocr 所需）

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置

```bash
# 方式 A：运行配置向导（推荐）
python setup_config.py

# 方式 B：手动复制并编辑
cp config.example.json config.json
vim config.json
```

### 3. 运行（交互模式）

```bash
python -m cli.interactive
```

运行时如果当前目录有 `config.json`，会自动检测并提示是否读取。配置的字段会跳过手动输入，未配置的字段正常交互。

```
[!] 检测到配置文件 config.json
    学号: 2021000001
    房间: 第一自习室
    时间: 16:00
    座位: 043

是否读取配置？[回车=是 / 0=否]:
```

### 4. 运行（服务器无头模式）

```bash
python -m cli.headless
```

## Docker 部署

```bash
# 构建并运行
docker compose up -d

# 或手动运行
docker build -t library-bot .
docker run -v $(pwd)/config.json:/app/config.json library-bot
```

## Cron 定时任务

图书馆每天早上 8:00 开放当天和明天的预约。建议 8:01 执行：

```bash
crontab -e
# 添加：
1 8 * * * cd /path/to/axhu_library_bot && python -m cli.headless >> cron.log 2>&1
```

## 配置说明

### config.json（用户偏好）

```json
{
    "username": "你的学号",
    "password": "你的密码",
    "room": "第一自习室",
    "start_time": "16:00",
    "seat": "",
    "date": "auto",
    "webhook_url": "",
    "hmac_secret": "",
    "vision_api_key": "",
    "vision_base_url": "https://ark.cn-beijing.volces.com/api/v3/chat/completions",
    "vision_model": "doubao-seed-2-0-code-preview-260215"
}
```

| 配置项 | 必填 | 说明 |
|--------|------|------|
| `username` | ✅ | 学号 |
| `password` | ✅ | 密码 |
| `room` | ✅ | 房间名：第二自习室 / 308自习室 / 第三自习室 / 第一自习室 / 第一自习室A |
| `start_time` | ❌ | 开始时间 HH:MM，`"auto"` = 最早可用 |
| `seat` | ❌ | 默认座位号（三位数，如 `"043"`），空=自动选 |
| `date` | ❌ | `"auto"` = 明天，也可指定如 `"2026-06-15"` |
| `hmac_secret` | ✅ | API 签名密钥 |
| `vision_api_key` | ❌ | 豆包/OpenAI 兼容 API Key（不填则跳过 AI 求解） |
| `webhook_url` | ❌ | 飞书/企业微信 Webhook 通知地址 |

### 环境变量（替代 config.json，优先级更高）

| 变量 | 说明 |
|------|------|
| `LIBRARY_USERNAME` | 学号 |
| `LIBRARY_PASSWORD` | 密码 |
| `HMAC_SECRET` | API 签名密钥 |
| `VISION_API_KEY` | 豆包 API Key |
| `VISION_API_BASE_URL` | 视觉 API 地址 |
| `VISION_API_MODEL` | 视觉模型名 |
| `WEBHOOK_URL` | 通知 Webhook |

环境变量优先级高于 config.json，建议服务器部署时用环境变量存放敏感信息。

## 工作原理

### 登录流程

```
图书馆 SSO 入口 → SSO 登录页（AES 加密密码 + OCR 验证码）
  → CAS Ticket → ssoAuth API → 获取 Session Token
```

### 验证码求解策略

```
方案1: 文字验证码 OCR（ddddocr）
  ↓ 失败
方案2: 模板匹配（66通道 CV：灰度/边缘/二值 × CCOEFF/CCORR × 11尺度）
  ↓ 失败（最多重试3次不同验证码）
方案2.5: AI 视觉（豆包/GPT-4V 多模态识别）
  ↓ 失败
方案3: 手动点击（cv2 弹窗，仅交互模式）
```

### API 认证

所有需要认证的请求均携带：
- `Authorization: <session_token>` 头
- `X-request-id`、`X-request-date`、`X-hmac-request-key` HMAC-SHA256 签名头
- `loginType: PC` 头

## 重要说明

### ⚠️ 关于全自动化预约

要实现**完全无需人工干预**的自动预约，必须配置多模态视觉大模型的 API Key（如豆包、OpenAI GPT-4V、通义千问 VL 等）。原因如下：

- 点击式行为验证码需要找到目标汉字在图片中的位置，纯算法（模板匹配/OCR）存在成功率上限
- 多模态大模型天然具备汉字识别和空间定位能力，是目前唯一可靠的自动化方案
- 文字验证码 OCR（ddddocr）和模板匹配作为前置方案可覆盖部分场景，但无法保证 100% 通过率
- **不配置 AI 视觉方案，验证码求解可能失败，导致无法完成自动预约**

推荐使用豆包（火山方舟 Ark），注册即送免费额度，API 兼容 OpenAI 格式，成本极低。

### 💡 关于服务器部署

理论上将该脚本部署在云服务器上，配合 cron 定时任务，可以真正实现**无需早起的全自动预约**——每天 8:01 自动抢座，解决期末周图书馆一座难求的苦恼。

本人在云服务器上实测过完整流程，功能验证通过。但受限于物理条件：**学校未开放 VPN 客户端，无法通过公网挂载校园内网 VPN**，而图书馆预约系统仅限校内网络访问。因此服务器部署方案目前无法落地。

**退而求其次的方案：**
- 在个人电脑上设置**定时开机**（BIOS 设置或智能插座）
- 配合 **Windows 任务计划程序** 在开机后自动运行脚本
- 同样可以实现无需早起的自动化预约

> 其他高校的同学如果有 VPN 接入校园内网的条件，完全可以部署在服务器上实现真正的全自动化。

### 🏫 适用学校

**目前仅适用于安徽新华学院（AXHU）**。不同学校的 SSO 认证流程、API 接口、验证码类型各有差异，但本项目的架构（SSO CAS 登录 → HMAC 签名 → 多策略验证码求解 → 座位预约）可作为其他高校的参考框架进行二次开发。

## 支持的自习室

- 第二自习室
- 308自习室
- 第三自习室
- 第一自习室
- 第一自习室A

## 声明

本项目仅供学习研究使用。请合理使用，遵守所在图书馆的使用条款。作者对任何滥用或账号处罚不承担责任。

## 开源协议

MIT License — 详见 [LICENSE](LICENSE) 文件。
