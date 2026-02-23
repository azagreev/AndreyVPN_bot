# Project Research Summary

**Project:** AndreyVPN_bot
**Domain:** VPN Management Bot
**Researched:** 2025-02-24
**Confidence:** HIGH

## Executive Summary

AndreyVPN_bot is a private VPN management solution designed for small groups and individuals, utilizing Telegram as a user interface and AmneziaWG for secure, obfuscated connectivity. Experts in this domain typically build such systems by wrapping VPN CLI tools in a bot framework, focusing on ease of onboarding (QR codes) and strict access control (Admin approval) to prevent IP blacklisting.

The recommended approach centers on a Python-based stack using `aiogram 3.x` for the bot logic and `Docker` for orchestration. This ensures a portable environment while leveraging AmneziaWG's superior DPI-evasion capabilities compared to standard WireGuard or OpenVPN. Data persistence is handled via `SQLite` for its simplicity and low overhead for the target user base (<100 users).

The primary technical risks involve the integration of the AmneziaWG kernel module with Dockerized environments and the potential for "config drift" if obfuscation parameters are changed without a migration strategy. These risks are mitigated through a standardized host setup script and a versioned approach to global VPN configurations stored in the database.

## Key Findings

### Recommended Stack

The stack prioritizes modern, asynchronous Python libraries and robust infrastructure tools that simplify deployment and maintenance.

**Core technologies:**
- **Python 3.11+ / aiogram 3.x**: Bot Framework — Modern, asynchronous, and well-supported for Telegram Bot API features.
- **AmneziaWG**: VPN Protocol — A modified WireGuard protocol that provides obfuscation to bypass Deep Packet Inspection (DPI).
- **SQLite / aiosqlite**: Database — Lightweight, file-based storage suitable for small user counts with non-blocking async operations.
- **Docker / Docker Compose**: Orchestration — Isolates the VPN and Bot environments, ensuring reproducible setups across different VPS providers.

### Expected Features

The feature set is divided between critical access control and user-friendly profile delivery.

**Must have (table stakes):**
- **Admin Approval** — Mandatory for private access control.
- **QR Code & .conf Export** — Simplifies VPN setup on mobile and desktop clients.
- **Anti-Bot Challenge** — Basic CAPTCHA to prevent automated spam on the bot.

**Should have (competitive):**
- **Traffic Monitoring** — Prevents bandwidth hogging and provides usage visibility.
- **Profile Revocation** — Allows the admin to kick users directly via the bot interface.

**Defer (v2+):**
- **Payment Integration** — Adds unnecessary legal and technical complexity for a private/friend-focused service.
- **Usage Alerts** — Non-critical for launch, can be added as a monitoring enhancement.

### Architecture Approach

The system follows a **Modular Monolith** pattern within Docker, separating Telegram interaction logic from low-level VPN command execution.

**Major components:**
1. **Bot Handler** — Manages user states and processes Telegram commands.
2. **VPN Service** — An asynchronous wrapper around AmneziaWG CLI commands for peer management.
3. **Database Layer** — Uses the Repository pattern to encapsulate all persistent state operations.
4. **Admin Dashboard** — A specialized set of handlers for managing pending requests and viewing server health.

### Critical Pitfalls

1. **AmneziaWG Kernel Module Mismatch** — Ensure the host OS has the kernel module installed before running Docker to avoid interface initialization failures.
2. **Obfuscation Parameter Desync** — Treat J-parameters as global versioned state to avoid breaking all existing user profiles on update.
3. **IP Address Exhaustion** — Implement tracking and cleanup for assigned internal IPs in the VPN subnet.
4. **SQLite State Loss** — Use absolute paths and explicit Docker volume mappings for the database and VPN configs.

## Implications for Roadmap

Based on research, suggested phase structure:

### Phase 1: Infrastructure & Docker Setup
**Rationale:** Establishing the environment first is critical because AmneziaWG's kernel-level dependencies are the biggest technical hurdle.
**Delivers:** Functional Docker Compose setup with AmneziaWG kernel module verification.
**Addresses:** Base connectivity and persistence.
**Avoids:** Pitfall 1 (Kernel Module Mismatch) and Pitfall 4 (State Loss).

### Phase 2: Bot Core & Onboarding
**Rationale:** Once infrastructure is ready, communication must be established to handle the user flow.
**Delivers:** Basic bot loop, Anti-bot challenge, and Admin notification system.
**Uses:** `aiogram 3.x` and `.env` for Admin ID.
**Implements:** Bot Handler component.

### Phase 3: VPN Management (Peer Creation)
**Rationale:** The core value proposition—issuing VPN profiles—requires both the bot and the VPN service to be operational.
**Delivers:** QR code generation, `.conf` file delivery, and Peer CRUD operations.
**Addresses:** All "Must have" features from FEATURES.md.
**Avoids:** Pitfall 3 (IP Exhaustion).

### Phase 4: Monitoring & Maintenance
**Rationale:** Enhances the service but isn't required for the first user to connect.
**Delivers:** Traffic tracking (delta-sync), auto-reset tasks, and Admin status dashboard.
**Uses:** `aiosqlite` for persistent traffic stats.
**Implements:** Background monitoring tasks.

### Phase Ordering Rationale

- **Infrastructure First**: Prevents building high-level bot logic on a broken VPN foundation.
- **Security-Led Onboarding**: Places Admin approval and Anti-bot challenges before VPN generation to protect the server from day one.
- **Monitoring Last**: Separates "nice-to-have" statistics from "must-have" connectivity, allowing for a faster MVP launch.

### Research Flags

Phases likely needing deeper research during planning:
- **Phase 1: Infrastructure**: Deep dive into AmneziaWG kernel module installation scripts for common cloud providers (Hetzner, DigitalOcean).
- **Phase 3: VPN Management**: Research specific AmneziaWG-go vs. Kernel-mode performance impacts for lower-end VPS instances.

Phases with standard patterns (skip research-phase):
- **Phase 2: Bot Core**: Follows standard `aiogram 3.x` patterns.
- **Phase 4: Monitoring**: Uses standard periodic task patterns (APScheduler or aiogram loops).

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | Tech is modern and well-documented. |
| Features | HIGH | Domain is well-understood with clear user expectations. |
| Architecture | HIGH | Standard patterns (Repository, Service Wrapper) apply well here. |
| Pitfalls | HIGH | Critical domain-specific risks identified. |

**Overall confidence: HIGH**

### Gaps to Address

- **AmneziaWG Host Setup**: The exact shell commands for installing the kernel module on various Ubuntu flavors need validation during the Infrastructure phase.
- **MTU Fine-tuning**: Optimal MTU for mobile carrier compatibility should be tested during Phase 3.

## Sources

### Primary (HIGH confidence)
- [aiogram 3.x Documentation](https://docs.aiogram.dev/)
- [AmneziaWG GitHub Repository](https://github.com/amnezia-vpn/amnezia-wg)
- [Official Docker Documentation for Ubuntu](https://docs.docker.com/engine/install/ubuntu/)

### Secondary (MEDIUM confidence)
- WireGuard Management Best Practices (community docs)
- Competitor analysis of existing WG/Amnezia Telegram bots.

---
*Research completed: 2025-02-24*
*Ready for roadmap: yes*
