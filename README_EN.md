# AXHU Library Seat Booking Bot

[![Python](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

> 🌐 [中文](README.md) | English

Automated seat reservation system for university libraries with SSO CAS authentication, multi-strategy captcha solving (OCR + template matching + AI vision), and cron-based headless deployment.

## Features

- **SSO CAS Login** — Automatic SSO authentication with AES-128-ECB password encryption and captcha OCR
- **HMAC Request Signing** — Reverse-engineered HMAC-SHA256 request signing for all API calls
- **Multi-Strategy Captcha Solving** — Progressive fallback:
  1. Text captcha OCR (ddddocr)
  2. Template matching (multi-channel CV: grayscale + edge + binary, 66 matching pipelines)
  3. AI vision (Doubao / GPT-4V / Qwen-VL compatible)
  4. Manual click (interactive mode only)
- **Smart Seat Selection** — Filter by room, time, preferred seat; sort by match quality
- **Dual Mode** — Interactive CLI for local use + headless mode for cron/server deployment
- **Configurable** — JSON config file + environment variables; secrets never hardcoded
- **Webhook Notifications** — Feishu / Discord / custom webhook on booking success/failure

## Architecture

```
axhu_library_bot/
├── core/                   # Core library
│   ├── api_client.py       # SSO login, HMAC signing, REST API
│   ├── config.py           # Configuration management
│   ├── constants.py        # Constants & magic numbers
│   ├── vision_solver.py    # AI vision captcha (Doubao/GPT-4V)
│   └── captcha/
│       └── solver.py       # Multi-strategy captcha solver
├── cli/                    # Command-line interfaces
│   ├── interactive.py      # Interactive terminal mode
│   └── headless.py         # Headless cron/server mode
├── setup_config.py         # Configuration wizard
├── config.example.json     # Config template
├── requirements.txt        # Python dependencies
├── Dockerfile              # Docker build
├── docker-compose.yml      # Docker Compose
└── README.md
```

## Quick Start

### Prerequisites

- Python 3.10+
- Tesseract or system fonts (for ddddocr)

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure

```bash
# Option A: Run the setup wizard
python setup_config.py

# Option B: Copy and edit manually
cp config.example.json config.json
vim config.json
```

### 3. Run (interactive mode)

```bash
python -m cli.interactive
```

### 4. Run (headless/server mode)

```bash
python -m cli.headless
```

## Docker Deployment

```bash
# Build and run
docker compose up -d

# Or manually
docker build -t library-bot .
docker run -v $(pwd)/config.json:/app/config.json library-bot
```

## Cron Setup

The library opens reservations at 8:00 AM daily. Schedule the bot to run at 8:01 AM:

```bash
crontab -e
# Add:
1 8 * * * cd /path/to/axhu_library_bot && python -m cli.headless >> cron.log 2>&1
```

## Configuration

### config.json (user preferences)

```json
{
    "username": "your_student_id",
    "password": "your_password",
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

### Environment Variables (alternative to config.json)

| Variable | Description |
|----------|-------------|
| `LIBRARY_USERNAME` | Student ID |
| `LIBRARY_PASSWORD` | Password |
| `HMAC_SECRET` | API signing key |
| `VISION_API_KEY` | Doubao/OpenAI-compatible API key |
| `VISION_API_BASE_URL` | Vision API endpoint |
| `VISION_API_MODEL` | Vision model name |
| `WEBHOOK_URL` | Notification webhook |

Environment variables take precedence over config.json.

## How It Works

### Login Flow

```
Library SSO Entry → SSO Login Page (AES-encrypted password + OCR captcha)
  → CAS Ticket → ssoAuth API → Session Token
```

### Captcha Solving Strategy

```
Text Captcha (ddddocr OCR)
  ↓ failure
Template Matching (66-channel CV: gray/edge/binary × CCOEFF/CCORR × 11 scales)
  ↓ failure (max 3 retries)
AI Vision (Doubao/GPT-4V multimodal)
  ↓ failure
Manual Click (cv2 window, interactive only)
```

### API Authentication

All authenticated requests include:
- `Authorization: <session_token>` header
- `X-request-id`, `X-request-date`, `X-hmac-request-key` HMAC-SHA256 signature headers
- `loginType: PC` header

## Important Notes

### ⚠️ Fully Automated Booking Requires AI Vision

To achieve **fully hands-free** automatic booking, you **must** configure a multimodal vision AI API key (Doubao, OpenAI GPT-4V, Qwen-VL, etc.). Here's why:

- The behavioral "click-text-in-order" captcha requires finding a specific Chinese character in an image
- Pure algorithmic approaches (template matching / OCR) have an upper limit on success rate
- Multimodal LLMs natively handle Chinese character recognition and spatial localization — currently the only reliable automation path
- Text captcha OCR (ddddocr) and template matching serve as pre-filters but cannot guarantee 100% pass rate
- **Without AI vision configured, captcha solving may fail, preventing automatic booking**

We recommend Doubao (Volcengine Ark) — free quota on registration, OpenAI-compatible API, minimal cost.

### 💡 On Server Deployment

In theory, deploying on a cloud server with cron scheduling enables truly automatic booking — wake up at 8:01 AM daily to grab seats without getting out of bed, solving the perennial finals-week library seat crisis. The author tested the full pipeline on a cloud server and it works.

However, there is a practical limitation: **the university does not provide a VPN client**, making it impossible to connect to the campus intranet from a public cloud server. The library booking system is only accessible from within the campus network. Therefore, full server automation is currently blocked by physical constraints.

**Workaround:**
- Set up **scheduled PC power-on** (BIOS timer or smart power plug)
- Use **Windows Task Scheduler** (or cron on Linux) to auto-run the script on boot
- This achieves the same hands-free experience without a server

> Students at other universities with campus VPN access can deploy entirely on a server for true full automation.

### 🏫 Supported University

**Currently only for Anhui Xinhua University (AXHU).** Different universities have different SSO flows, API endpoints, and captcha types, but this project's architecture (SSO CAS login → HMAC signing → multi-strategy captcha solving → seat booking) serves as a reference framework for adaptation to other schools.

## Supported Rooms

- 第二自习室 (Second Study Room)
- 308自习室 (308 Study Room)
- 第三自习室 (Third Study Room)
- 第一自习室 (First Study Room)
- 第一自习室A (First Study Room A)

## Disclaimer

This project is for educational purposes only. Use responsibly and comply with your library's terms of service. The authors are not responsible for any misuse or account penalties.

## License

MIT License — see [LICENSE](LICENSE) file for details.
