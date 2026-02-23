# Architecture Patterns: AndreyVPN_bot

**Domain:** VPN Management Bot
**Researched:** 2025-02-24

## Recommended Architecture

The system follows a **Modular Monolith** structure within a Docker environment.

### Component Boundaries

| Component | Responsibility | Communicates With |
|-----------|---------------|-------------------|
| **Bot Handler** | Processes Telegram commands/messages. | Database, VPN Service |
| **VPN Service** | Wraps `amneziawg` CLI commands for peer management. | AmneziaWG Instance (Shared volume/commands) |
| **Database** | Stores user status, admin approval state, and traffic stats. | Bot Handler, VPN Service |
| **Admin Dashboard** | Special handlers for profile approval and traffic views. | Database, VPN Service |

### Data Flow

1. **User Request**: User `/start` -> CAPTCHA handler -> Status "Pending".
2. **Admin Notification**: Bot notifies Admin (Admin ID from `.env`).
3. **Approval**: Admin clicks "Approve" -> Status "Active" -> VPN Service generates peer keys.
4. **Config Delivery**: Bot generates `.conf` string and QR code -> Sends to User.
5. **Monitoring**: Background task (APScheduler or aiogram loop) -> Reads `wg show` -> Updates SQLite.

## Patterns to Follow

### Pattern 1: Repository Pattern for DB
**What:** Encapsulate all SQLite queries into a single `db/` service.
**When:** All bot handlers need to check user status.
**Example:**
```python
async def get_user_status(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT status FROM users WHERE telegram_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else None
```

### Pattern 2: Service Wrapper for VPN
**What:** Decouple Telegram logic from VPN commands.
**When:** Creating peers or reading traffic.
**Example:**
```python
class VPNService:
    def generate_peer(self, user_id: int) -> str:
        # Calls subprocess for amneziawg-go or uses shared volume
        pass
    
    def get_traffic_stats(self) -> dict:
        # Parses output of 'wg show'
        pass
```

## Anti-Patterns to Avoid

### Anti-Pattern 1: Blocking Subprocesses
**What:** Running heavy VPN commands synchronously in an `async` handler.
**Why bad:** Freezes the bot for all users during long operations.
**Instead:** Use `asyncio.create_subprocess_exec()` for all CLI calls.

### Anti-Pattern 2: Hardcoding User Paths
**What:** Using absolute paths like `/home/user/bot/data.db`.
**Why bad:** Breaks when moving to Docker or another server.
**Instead:** Use `os.path.join(ROOT_DIR, 'data', 'bot.db')` and map `/app/data` to a volume.

## Scalability Considerations

| Concern | At 10 users | At 100 users | At 1000 users |
|---------|-------------|--------------|---------------|
| **Database** | SQLite (fine) | SQLite (fine) | Consider PostgreSQL if many concurrent writes. |
| **VPN Performance**| KVM (fine) | KVM (fine) | Might need multiple VPN servers (load balancing). |
| **Bot Traffic** | Webhook or Polling | Polling (fine) | Webhook with Nginx for better efficiency. |

## Sources

- [aiogram 3 Project Structure Examples](https://github.com/aiogram/aiogram)
- [WireGuard Management Best Practices](https://github.com/pirate/wireguard-docs)
- [Dockerized Python App Best Practices](https://docs.docker.com/language/python/)
