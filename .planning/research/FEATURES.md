# Feature Landscape: AndreyVPN_bot

**Domain:** VPN Management Bot
**Researched:** 2025-02-24

## Table Stakes

Features users expect in a private VPN bot.

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| **Admin Approval** | Critical for private access control. | Medium | Requires a state machine for "Pending" users. |
| **QR Code Config** | Easiest way to import VPN on mobile. | Low | Use `python-qrcode` library. |
| **.conf File Export**| Necessary for desktop/custom clients. | Low | Standard WireGuard format with AmneziaWG params. |
| **Anti-Bot Challenge**| Prevents spam/DDoS on the bot. | Low | Simple CAPTCHA or math question on `/start`. |
| **Server Status** | Users need to know if the VPN is up. | Low | Check if AmneziaWG interface is active. |

## Differentiators

Features that make this bot particularly useful for friends/groups.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| **Traffic Monitoring** | Prevents one user from hogging bandwidth. | High | Requires parsing `wg` output and persisting to DB. |
| **Auto Monthly Reset** | Zero maintenance for the admin. | Medium | Scheduled task to clear traffic stats in SQLite. |
| **Profile Revocation** | Easily kick users without SSH. | Medium | Bot must be able to edit AmneziaWG config and restart interface. |
| **Usage Alerts** | Admin knows when server is under load. | Medium | Notify admin if traffic/CPU exceeds threshold. |

## Anti-Features

Features to explicitly NOT build.

| Anti-Feature | Why Avoid | What to Do Instead |
|--------------|-----------|-------------------|
| **Public Registration** | High risk of IP blacklisting and abuse. | Keep mandatory admin approval. |
| **Multiple Protocols** | Increases attack surface and complexity. | Stick to AmneziaWG for its DPI-evasion value. |
| **Payment Integration**| Adds legal and technical complexity. | Keep it as a free service for friends. |

## Feature Dependencies

```
Bot Core (/start) -> Anti-Bot Challenge -> Admin Approval -> VPN Profile Generation -> QR/File Delivery
Traffic Monitoring -> Persistent Stats in SQLite -> Admin Dashboard
```

## MVP Recommendation

Prioritize:
1. **Infrastructure**: Dockerized AmneziaWG + SQLite.
2. **Onboarding**: Anti-bot -> Request Access -> Admin Approval.
3. **Core Utility**: Single-click Profile Generation (QR + File).
4. **Monitoring**: Basic "Current Traffic" view for the admin.

Defer:
- **Usage Alerts**: Nice to have but not critical for launch.
- **Bulk Profile Management**: Admin can handle individual requests for now.

## Sources

- [Competitor analysis: WireGuard Telegram bots (various GitHub projects)]
- [User feedback from similar self-hosted VPN communities]
