# Phase 1: Foundation & Data Layer - Research

**Researched:** 2025-02-23
**Domain:** Telegram Bot Foundation (aiogram 3.x) & SQLite (aiosqlite)
**Confidence:** HIGH

## Summary

This phase focuses on setting up the project scaffolding for `AndreyVPN_bot` and defining the database schema. Based on the tech stack requirements (Python, aiogram, sqlite3), the standard expert approach in 2025 is to use **aiogram 3.x** for the bot framework and **aiosqlite** as an asynchronous wrapper for SQLite. This prevents the database operations from blocking the bot's asynchronous event loop.

Configuration management will be handled by **pydantic-settings**, which provides a robust, type-safe way to load environment variables from a `.env` file. The project will follow a modular architecture using **Routers** for handlers and **Middleware** for database connection injection.

**Primary recommendation:** Use `aiosqlite` instead of raw `sqlite3` to maintain non-blocking performance, and implement a `DbMiddleware` to inject database connections directly into handlers.

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| aiogram | 3.17+ | Bot Framework | Latest stable version with modern Router/Middleware API. |
| aiosqlite | 0.20.0+ | Async SQLite | Standard async wrapper for SQLite to avoid blocking event loop. |
| pydantic-settings | 2.7+ | Config Management | Type-safe loading of .env variables with validation. |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| python-dotenv | 1.0+ | Env Loading | Used by pydantic-settings to read .env files. |
| loguru | 0.7+ | Logging | Easier setup than standard logging (optional but recommended). |

**Installation:**
```bash
pip install aiogram aiosqlite pydantic-settings python-dotenv
```

## Architecture Patterns

### Recommended Project Structure
```
AndreyVPN_bot/
├── .env                  # Environment variables (git-ignored)
├── .env.example          # Template for .env
├── requirements.txt      # Project dependencies
├── main.py               # Entry point (bot initialization & polling)
├── config.py             # Pydantic settings model
├── database/
│   ├── __init__.py
│   ├── engine.py         # DB connection & table initialization
│   └── models.py         # Table definitions & schema strings
├── handlers/
│   ├── __init__.py
│   ├── start.py          # /start & registration
│   ├── admin.py          # Approval & admin commands
│   └── stats.py          # Statistics commands
├── keyboards/
│   ├── __init__.py
│   └── menu.py           # Reusable keyboard layouts
├── middlewares/
│   ├── __init__.py
│   └── db_middleware.py  # Injects aiosqlite connection into handlers
└── states/
    ├── __init__.py
    └── user_states.py    # FSM states for multi-step processes
```

### Pattern 1: Database Middleware Injection
Instead of opening/closing connections in every handler, we use middleware to provide a fresh connection for every update.
**Example:**
```python
# middlewares/db_middleware.py
import aiosqlite
from aiogram import BaseMiddleware

class DbMiddleware(BaseMiddleware):
    def __init__(self, db_path: str):
        self.db_path = db_path

    async def __call__(self, handler, event, data):
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row # Enables dict-like access
            data["db"] = db
            return await handler(event, data)
```

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Config Parsing | Custom `.ini` or `json` parser | `pydantic-settings` | Handles types, defaults, and secrets automatically. |
| Async SQL | Thread pools for `sqlite3` | `aiosqlite` | Battle-tested async wrapper. |
| State Storage | Custom dict-based state | `MemoryStorage` (aiogram) | Built-in, supports transitions and TTL. |

## Common Pitfalls

### Pitfall 1: Synchronous Database Calls
**What goes wrong:** Using `sqlite3` directly in an `async def` handler.
**Why it happens:** Standard `sqlite3` is synchronous; it blocks the entire bot while waiting for the disk.
**How to avoid:** Always use `aiosqlite` or run sync calls in `run_in_executor`.

### Pitfall 2: Hardcoded Configs
**What goes wrong:** Committing `BOT_TOKEN` or `ADMIN_ID` to git.
**How to avoid:** Use `.env` and `pydantic-settings`. Include `.env.example` in repo.

## Code Examples

### Database Schema (DATA-01)
Verified schema for users, approvals, and stats:

```sql
-- database/models.py

-- Users table
CREATE TABLE IF NOT EXISTS users (
    telegram_id INTEGER PRIMARY KEY,
    username TEXT,
    full_name TEXT,
    is_admin BOOLEAN DEFAULT 0,
    is_approved BOOLEAN DEFAULT 0,
    registered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Approvals tracking
CREATE TABLE IF NOT EXISTS approvals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER REFERENCES users(telegram_id),
    status TEXT CHECK(status IN ('pending', 'approved', 'rejected')) DEFAULT 'pending',
    admin_id INTEGER,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Daily Stats
CREATE TABLE IF NOT EXISTS daily_stats (
    date DATE PRIMARY KEY,
    total_users INTEGER DEFAULT 0,
    new_users INTEGER DEFAULT 0,
    approved_count INTEGER DEFAULT 0,
    requests_count INTEGER DEFAULT 0
);
```

### Handler with Injected DB
```python
# handlers/start.py
from aiogram import Router, types
from aiogram.filters import CommandStart
import aiosqlite

router = Router()

@router.message(CommandStart())
async def cmd_start(message: types.Message, db: aiosqlite.Connection):
    # db is injected by DbMiddleware
    await db.execute(
        "INSERT OR IGNORE INTO users (telegram_id, username, full_name) VALUES (?, ?, ?)",
        (message.from_user.id, message.from_user.username, message.from_user.full_name)
    )
    await db.commit()
    await message.answer("Registration successful or already exists.")
```

## Open Questions

1. **Deployment Environment?**
   - What we know: Bot will use SQLite.
   - What's unclear: Will it run in Docker or directly on VPS?
   - Recommendation: Plan for Docker (volume for SQLite) but support simple VPS run.

## Sources

### Primary (HIGH confidence)
- aiogram 3.x Docs - Official Router/Middleware patterns.
- aiosqlite GitHub - Standard usage examples.
- Pydantic Settings Docs - Environment variable management.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - Industry standard for Python bots.
- Architecture: HIGH - Follows official aiogram modular design.
- Pitfalls: HIGH - Covers most common "bottleneck" issues in bot dev.

**Research date:** 2025-02-23
**Valid until:** 2025-05-23
