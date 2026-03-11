"""
Базовая схема AndreyVPN_bot v1.0.
Создаёт все таблицы и индексы начального релиза.
"""
import aiosqlite

MIGRATION_ID = 1
DESCRIPTION = "Initial schema: users, approvals, vpn_profiles, daily_stats, configs"


async def up(db: aiosqlite.Connection) -> None:
    """Создать все таблицы начальной схемы."""
    await db.execute("""
        CREATE TABLE IF NOT EXISTS users (
            telegram_id INTEGER PRIMARY KEY,
            username    TEXT,
            full_name   TEXT,
            is_admin    BOOLEAN   DEFAULT 0,
            is_approved BOOLEAN   DEFAULT 0,
            registered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    await db.execute("""
        CREATE TABLE IF NOT EXISTS approvals (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id    INTEGER,
            status     TEXT      DEFAULT 'pending',
            admin_id   INTEGER,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (telegram_id)
        )
    """)
    await db.execute("""
        CREATE TABLE IF NOT EXISTS daily_stats (
            date           DATE    PRIMARY KEY,
            total_users    INTEGER DEFAULT 0,
            new_users      INTEGER DEFAULT 0,
            approved_count INTEGER DEFAULT 0,
            requests_count INTEGER DEFAULT 0
        )
    """)
    await db.execute("""
        CREATE TABLE IF NOT EXISTS configs (
            key   TEXT PRIMARY KEY,
            value TEXT
        )
    """)
    await db.execute("""
        CREATE TABLE IF NOT EXISTS vpn_profiles (
            id                   INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id              INTEGER,
            name                 TEXT,
            private_key          TEXT,
            public_key           TEXT,
            ipv4_address         TEXT,
            monthly_offset_bytes INTEGER   DEFAULT 0,
            created_at           TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (telegram_id)
        )
    """)
    await db.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_vpn_profiles_ipv4_unique
        ON vpn_profiles (ipv4_address)
        WHERE ipv4_address IS NOT NULL AND ipv4_address <> ''
    """)
    await db.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_vpn_profiles_public_key_unique
        ON vpn_profiles (public_key)
        WHERE public_key IS NOT NULL AND public_key <> ''
    """)


async def down(db: aiosqlite.Connection) -> None:
    """Удалить все таблицы начальной схемы."""
    await db.execute("DROP INDEX IF EXISTS idx_vpn_profiles_public_key_unique")
    await db.execute("DROP INDEX IF EXISTS idx_vpn_profiles_ipv4_unique")
    await db.execute("DROP TABLE IF EXISTS vpn_profiles")
    await db.execute("DROP TABLE IF EXISTS configs")
    await db.execute("DROP TABLE IF EXISTS daily_stats")
    await db.execute("DROP TABLE IF EXISTS approvals")
    await db.execute("DROP TABLE IF EXISTS users")
