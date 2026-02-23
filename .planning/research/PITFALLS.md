# Domain Pitfalls: VPN Telegram Bot (AmneziaWG)

**Domain:** VPN Management via Telegram Bot
**Researched:** 2025-02-24
**Project:** AndreyVPN_bot

## Critical Pitfalls

### 1. AmneziaWG Kernel Module vs. Docker Compatibility
**What goes wrong:** The bot starts, the container runs, but the VPN interface fails to initialize or traffic doesn't flow.
**Why it happens:** AmneziaWG is a kernel-level modification of WireGuard. Running it in Docker requires the host OS (Ubuntu 22.04) to have the specific AmneziaWG kernel module installed, OR the container must use the `amnezia-wg-go` (userspace) implementation, which is slower and requires different configuration.
**Consequences:** Complete service failure or extremely poor performance/instability.
**Warning signs:** `RTNETLINK answers: Operation not supported` in container logs; `wg` command returns nothing inside the container.
**Prevention:** Standardize the host setup script to install the `amneziawg` kernel module before starting Docker, or explicitly use a container image that handles the Go-implementation fallback.
**Phase to address:** Phase 1: Infrastructure & Docker Setup.

### 2. Obfuscation Parameter Desync (Config Drift)
**What goes wrong:** Users suddenly lose connection and cannot reconnect even after restarting their client.
**Why it happens:** AmneziaWG relies on shared obfuscation parameters (Jc, Jmin, Jmax, S1, S2, H1, H2, H3, H4). If the admin changes these on the server (e.g., to better bypass DPI), *all* previously issued `.conf` and QR codes become invalid immediately.
**Consequences:** Mass service disruption. Admin must manually re-issue and users must re-import all profiles.
**Warning signs:** Server logs show handshake attempts that never complete; client logs show `No response from peer`.
**Prevention:** Treat obfuscation parameters as "Global Versioned State". If they change, the bot should flag all existing profiles as "Outdated" and notify users to regenerate. Store these parameters in SQLite, not just in the Docker environment.
**Phase to address:** Phase 3: VPN Management (Peer creation).

### 3. IP Address Exhaustion in VPN Subnet
**What goes wrong:** The bot fails to generate a new profile for a friend.
**Why it happens:** VPNs use a specific subnet (e.g., 10.0.0.0/24). If the bot allows creating many profiles (even if temporary) without a cleanup/deletion mechanism, it will eventually run out of unique internal IPs.
**Consequences:** New users cannot join.
**Warning signs:** Errors in the peer generation script/library indicating no available IPs.
**Prevention:** Implement a check for available IPs in the subnet before generation. Add a "Revoke Profile" feature for the admin to clean up unused peers.
**Phase to address:** Phase 3: VPN Management.

### 4. SQLite State Loss (Docker Volume Mismanagement)
**What goes wrong:** After a bot update or server reboot, all approved users and traffic stats disappear.
**Why it happens:** SQLite database or WireGuard configuration files are stored inside the container's ephemeral filesystem instead of a persistent Docker volume.
**Consequences:** Total loss of user data and VPN keys. Admin must re-approve everyone.
**Warning signs:** Bot starts as "fresh" after every `docker compose up`.
**Prevention:** Explicitly map `/data` or the database path to a host directory in `docker-compose.yml`. Use absolute paths for volume mappings.
**Phase to address:** Phase 1: Infrastructure & Docker Setup.

## Moderate Pitfalls

### 5. Telegram Rate Limiting for Files/QR Codes
**What goes wrong:** Bot becomes unresponsive or fails to send configs to multiple users at once.
**Prevention:** Use `aiogram`'s built-in throttling or a simple task queue for sending files/images. Avoid sending large bursts of messages.
**Phase to address:** Phase 2: Bot Core.

### 6. MTU Fragmentation (Packet Loss)
**What goes wrong:** VPN works, but some websites (especially those with heavy headers or specific security) fail to load or are extremely slow.
**Prevention:** Set a safe default MTU for AmneziaWG (usually 1280 or 1380 for better compatibility with mobile networks) in the generated client configs.
**Phase to address:** Phase 3: VPN Management.

### 7. Traffic Counter Resets
**What goes wrong:** Monthly traffic monitoring shows incorrect data (zeros) after a server reboot.
**Why it happens:** `wg show` counters reset to zero whenever the VPN interface or the server restarts.
**Prevention:** The bot must periodically (e.g., every 5-15 mins) read current counters, calculate the *delta* since the last check, and add that delta to a persistent "total_traffic" column in SQLite.
**Phase to address:** Phase 4: Monitoring & Extras.

## Minor Pitfalls

### 8. Admin ID Spoofing / Hardcoding
**What goes wrong:** Admin changes their Telegram handle, and the bot no longer recognizes them, or someone mimics the handle.
**Prevention:** Always use the unique **Telegram User ID** (integer) for the admin, not the @username. Store this ID in an environment variable or a protected config file.
**Phase to address:** Phase 2: Bot Core.

### 9. Timezone Desync in Traffic Stats
**What goes wrong:** "Monthly" traffic resets at the wrong time (e.g., middle of the day).
**Prevention:** Use UTC for all database timestamps and define a clear "billing cycle" logic (e.g., 1st of every month at 00:00 UTC).
**Phase to address:** Phase 4: Monitoring & Extras.

## Phase-Specific Warnings

| Phase Topic | Likely Pitfall | Mitigation |
|-------------|---------------|------------|
| Phase 1: Infrastructure | Kernel Module Mismatch | Use Ubuntu 22.04 with a specific install script that checks for `amneziawg` module availability. |
| Phase 2: Bot Core | Admin Lockout | Ensure the Admin ID is correctly set in `.env` and the bot logs it on startup for verification. |
| Phase 3: VPN MGMT | Config Drift | Store J-parameters in DB and include them in a "Config Version" check. |
| Phase 4: Monitoring | Volatile Counters | Use "Delta-Sync" strategy (Interface -> DB) instead of direct reporting from `wg show`. |

## Sources

- [AmneziaVPN Documentation - Common Errors](https://amnezia.org/)
- [WireGuard "wg show" behavior notes](https://www.wireguard.com/)
- [Aiogram 3.x Security Best Practices](https://docs.aiogram.dev/)
- Community discussions on AmneziaWG Docker images (GitHub Issues).
