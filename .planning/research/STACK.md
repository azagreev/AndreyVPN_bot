# Technology Stack: AndreyVPN_bot

**Project:** AndreyVPN_bot
**Researched:** 2025-02-24

## Recommended Stack

### Core Frameworks
| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| **Python** | 3.11+ | Programming Language | Industry standard for Telegram bots and automation scripts. |
| **aiogram** | 3.x | Telegram Bot Framework | Modern, asynchronous, and supports latest Bot API features. |
| **AmneziaWG** | Latest | VPN Protocol | Modified WireGuard with obfuscation to bypass DPI/censorship. |

### Database
| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| **SQLite** | 3.x | Persistent Storage | Lightweight, file-based, sufficient for <100 users, easy backups. |
| **aiosqlite** | Latest | Async DB Driver | Non-blocking database operations for the bot. |

### Infrastructure & Deployment
| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| **Docker** | Latest | Containerization | Isolates VPN and Bot environments, ensures reproducible setups. |
| **Docker Compose**| 2.x | Orchestration | Manages multi-container setup (Bot + VPN). |
| **Ubuntu** | 22.04 LTS | Host Operating System | Stable, long-term support, excellent Docker and WireGuard support. |

### Supporting Libraries
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| **pydantic** | 2.x | Data Validation | Validating environment variables and config structures. |
| **python-qrcode**| Latest | QR Code Generation| Converting VPN configs into scannable QR codes for users. |
| **python-dotenv**| Latest | Env Management | Loading sensitive tokens and IDs from `.env` files. |

## Alternatives Considered

| Category | Recommended | Alternative | Why Not |
|----------|-------------|-------------|---------|
| **Database** | SQLite | PostgreSQL | Overkill for a personal/small-group bot; adds management overhead. |
| **VPN Protocol**| AmneziaWG | OpenVPN | AmneziaWG (WireGuard-based) is faster and harder to detect via DPI. |
| **Bot Lib** | aiogram 3 | python-telegram-bot | aiogram 3 is built for `asyncio` from the ground up and has better middleware support. |

## Installation

```bash
# Core dependencies
pip install aiogram aiosqlite pydantic python-dotenv qrcode[pil]

# Infrastructure
# Assuming Docker and Docker Compose are installed on Ubuntu 22.04
sudo apt update && sudo apt install -y docker-ce docker-compose-plugin
```

## Sources

- [aiogram 3.x Documentation](https://docs.aiogram.dev/)
- [AmneziaWG GitHub Repository](https://github.com/amnezia-vpn/amnezia-wg)
- [Official Docker Documentation for Ubuntu](https://docs.docker.com/engine/install/ubuntu/)
