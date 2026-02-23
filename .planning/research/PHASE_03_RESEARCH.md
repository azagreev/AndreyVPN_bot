# Phase 03 Research: VPN Service Integration

**Phase:** 3
**Focus:** AmneziaWG Peer Management & Key Generation
**Date:** 2025-02-24

## Key Generation

AmneziaWG uses standard WireGuard (Curve25519) keys. These can be generated using:
- `wg genkey` -> returns a private key.
- `echo <private_key> | wg pubkey` -> returns a public key.

In Python, this should be done using `asyncio.create_subprocess_exec` to avoid blocking the bot's event loop.

## AmneziaWG Parameters

AmneziaWG adds obfuscation parameters to the standard WireGuard configuration. These parameters must match between the server and the client for the connection to work.

### Required Fields for Client Config:
- `[Interface]`
  - `PrivateKey`: Generated for the client.
  - `Address`: Unique IP in the VPN network (e.g., `10.8.0.2/32`).
  - `DNS`: Usually `1.1.1.1` or `8.8.8.8`.
  - `Jc`, `Jmin`, `Jmax`, `S1`, `S2`, `H1`, `H2`, `H3`, `H4`: Obfuscation parameters (provided via `.env`).
- `[Peer]`
  - `PublicKey`: Server's public key (provided via `.env`).
  - `Endpoint`: Server's IP/Domain and Port (provided via `.env`).
  - `AllowedIPs`: Usually `0.0.0.0/0, ::/0` for full tunneling.

## Database Schema Update

A new table `vpn_profiles` is needed to store generated keys and metadata.

```sql
CREATE TABLE IF NOT EXISTS vpn_profiles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    name TEXT NOT NULL, -- e.g., "Default" or "Mobile"
    private_key TEXT NOT NULL,
    public_key TEXT NOT NULL,
    ipv4_address TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users (telegram_id)
);
```

## IP Address Management

The bot needs to assign unique IP addresses within a defined range (e.g., `10.8.0.0/24`). 
- Strategy: Increment the last octet or store the next available IP in `configs` table.
- Default Range: `10.8.0.0/24` (usable IPs `10.8.0.2` to `10.8.0.254`).

## Implementation Steps

1. Update `Settings` in `bot/core/config.py` to include AmneziaWG server parameters.
2. Update `bot/db/models.py` to include the `vpn_profiles` table.
3. Create `bot/services/vpn_service.py` with:
   - `generate_key_pair()`
   - `generate_config(user_id, private_key, ipv4)`
   - `get_next_available_ip()`
4. Integrate `VPNService` into the database initialization flow.

## Risks & Pitfalls

- **Duplicate IPs**: Need a reliable way to ensure two users don't get the same IP.
- **CLI Dependency**: `wg` command must be installed in the environment/container.
- **Security**: Private keys must be stored securely (encrypted at rest is ideal, but plain SQLite is the current project scope).
