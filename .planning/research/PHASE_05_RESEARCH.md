# Research 05-01: Monitoring & Traffic Tracking

## Objective
Implement traffic consumption tracking and server status monitoring for AmneziaWG.

## Traffic Tracking Mechanism
- **Source**: The command `wg show <interface> transfer` provides a list of public keys and their respective received/sent bytes.
- **Mapping**: 
    - We have `public_key` stored in the `vpn_profiles` table.
    - We can execute `wg show all dump` to get a machine-readable format:
      `interface  public_key  preshared_key  endpoint  allowed_ips  latest_handshake  transfer_rx  transfer_tx  persistent_keepalive`
- **Logic**:
    1. Run `wg show <interface> dump`.
    2. Parse lines to find matching `public_key`.
    3. Sum `transfer_rx` and `transfer_tx` to get total bytes.

## Database Strategy
- **Requirement**: Track usage *per month*.
- **Problem**: WireGuard counters reset when the interface goes down or the peer is removed/re-added. They are cumulative since the peer was added to the *running* interface.
- **Solution**:
    - Keep a `total_traffic_bytes` field in `vpn_profiles`.
    - Periodically (or on-demand) fetch current `wg` counters.
    - If `current_wg_counter < last_seen_wg_counter` (meaning a reset happened), add `current_wg_counter` to a `base_traffic` offset.
    - Or simpler: Just show the *current* counters from the interface as "Current Session" and provide a way to see "Total" if we implement persistent logging.
    - **Refined Plan**: For V1, we will show "Current active traffic" from the interface. To support "Monthly reset", we need a table or field to store "Traffic at start of month".

## Server Status
- **Mechanism**: Check if the interface exists and is up.
- **Command**: `ip link show <interface>` or checking `wg show <interface>` return code.

## Reset Logic (MONITOR-03)
- **Task**: Reset counters at 00:00 on the 1st of every month.
- **Implementation**: A simple background task using `apscheduler` or a manual check on the first bot interaction of the month. Given the simplicity, a check in the DB during the first `/stats` call of the month might be enough, or a dedicated `asyncio` loop.

## Components to Implement:
1. `VPNService.get_traffic_stats()`: Parses `wg show` output.
2. `VPNService.get_server_status()`: Checks if WG is running.
3. `bot/handlers/monitoring.py`: `/stats` command for users, `/server_status` for admin.
