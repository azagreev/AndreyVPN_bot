"""
Слой доступа к данным. Все SQL-запросы сосредоточены здесь.
"""
from __future__ import annotations

import aiosqlite


# ── Users ─────────────────────────────────────────────────────────────────────

async def get_user(db: aiosqlite.Connection, telegram_id: int) -> aiosqlite.Row | None:
    cursor = await db.execute(
        "SELECT * FROM users WHERE telegram_id = ?", (telegram_id,)
    )
    return await cursor.fetchone()


async def create_user(
    db: aiosqlite.Connection,
    telegram_id: int,
    username: str | None,
    full_name: str | None,
    *,
    is_admin: bool = False,
    is_approved: bool = False,
) -> None:
    await db.execute(
        "INSERT OR IGNORE INTO users (telegram_id, username, full_name, is_admin, is_approved) "
        "VALUES (?, ?, ?, ?, ?)",
        (telegram_id, username, full_name, int(is_admin), int(is_approved)),
    )
    await db.commit()


async def set_user_approved(db: aiosqlite.Connection, telegram_id: int, approved: bool) -> None:
    await db.execute(
        "UPDATE users SET is_approved = ? WHERE telegram_id = ?",
        (int(approved), telegram_id),
    )
    await db.commit()


async def get_users_page(db: aiosqlite.Connection, page: int, page_size: int) -> tuple[list, int]:
    cursor = await db.execute("SELECT COUNT(*) as cnt FROM users")
    total = (await cursor.fetchone())["cnt"]
    cursor = await db.execute(
        "SELECT telegram_id, full_name, username, is_approved FROM users "
        "ORDER BY registered_at DESC LIMIT ? OFFSET ?",
        (page_size, page * page_size),
    )
    rows = [dict(r) for r in await cursor.fetchall()]
    return rows, total


async def get_user_detail(db: aiosqlite.Connection, telegram_id: int) -> tuple[str, bool]:
    """Возвращает (html_text, is_approved)."""
    import html as html_module
    cursor = await db.execute(
        "SELECT full_name, username, is_approved, registered_at FROM users WHERE telegram_id = ?",
        (telegram_id,),
    )
    user = await cursor.fetchone()
    if not user:
        return "Пользователь не найден.", False

    cursor = await db.execute(
        "SELECT id, name, ipv4_address FROM vpn_profiles WHERE user_id = ?", (telegram_id,)
    )
    profiles = await cursor.fetchall()

    status = "✅ Одобрен" if user["is_approved"] else "❌ Заблокирован / Ожидает"
    reg_date = user["registered_at"][:10] if user["registered_at"] else "—"
    full_name = html_module.escape(user["full_name"]) if user["full_name"] else "—"
    username = html_module.escape(user["username"]) if user["username"] else "—"

    text = (
        f"👤 <b>{full_name}</b>\n"
        f"🔗 @{username}\n"
        f"🆔 <code>{telegram_id}</code>\n"
        f"📅 {reg_date}\n"
        f"Статус: {status}\n\n"
        f"🔑 Профили ({len(profiles)}):\n"
    )
    for p in profiles:
        text += f"  • {html_module.escape(p['name'])} ({p['ipv4_address']})\n"
    if not profiles:
        text += "  Нет профилей\n"

    return text, bool(user["is_approved"])


# ── Approvals ─────────────────────────────────────────────────────────────────

async def create_approval(db: aiosqlite.Connection, user_id: int) -> None:
    await db.execute(
        "INSERT INTO approvals (user_id, status) VALUES (?, 'pending')", (user_id,)
    )
    await db.commit()


async def get_pending_approvals(
    db: aiosqlite.Connection, page: int, page_size: int
) -> tuple[list, int]:
    cursor = await db.execute(
        "SELECT COUNT(*) as cnt FROM approvals WHERE status = 'pending'"
    )
    total = (await cursor.fetchone())["cnt"]
    cursor = await db.execute(
        """SELECT a.user_id, u.full_name, u.username
           FROM approvals a
           JOIN users u ON a.user_id = u.telegram_id
           WHERE a.status = 'pending'
           ORDER BY a.id
           LIMIT ? OFFSET ?""",
        (page_size, page * page_size),
    )
    rows = [dict(r) for r in await cursor.fetchall()]
    return rows, total


async def set_approval_status(
    db: aiosqlite.Connection, user_id: int, status: str, admin_id: int
) -> None:
    await db.execute(
        "UPDATE approvals SET status = ?, admin_id = ? WHERE user_id = ? AND status = 'pending'",
        (status, admin_id, user_id),
    )
    await db.commit()


# ── VPN Profiles ──────────────────────────────────────────────────────────────

async def count_user_profiles(db: aiosqlite.Connection, user_id: int) -> int:
    cursor = await db.execute(
        "SELECT COUNT(*) as cnt FROM vpn_profiles WHERE user_id = ?", (user_id,)
    )
    return (await cursor.fetchone())["cnt"]


async def get_profiles(db: aiosqlite.Connection, user_id: int) -> list:
    cursor = await db.execute(
        "SELECT id, name, ipv4_address FROM vpn_profiles WHERE user_id = ? ORDER BY created_at",
        (user_id,),
    )
    return [dict(r) for r in await cursor.fetchall()]


async def get_profile_owner(db: aiosqlite.Connection, profile_id: int) -> int | None:
    cursor = await db.execute(
        "SELECT user_id FROM vpn_profiles WHERE id = ?", (profile_id,)
    )
    row = await cursor.fetchone()
    return row["user_id"] if row else None


async def get_profile_for_config(
    db: aiosqlite.Connection, profile_id: int
) -> aiosqlite.Row | None:
    cursor = await db.execute(
        "SELECT name, private_key, ipv4_address FROM vpn_profiles WHERE id = ?",
        (profile_id,),
    )
    return await cursor.fetchone()


async def insert_vpn_profile(
    db: aiosqlite.Connection,
    user_id: int,
    name: str,
    encrypted_key: str,
    public_key: str,
    ipv4: str,
) -> None:
    await db.execute(
        "INSERT INTO vpn_profiles (user_id, name, private_key, public_key, ipv4_address) "
        "VALUES (?, ?, ?, ?, ?)",
        (user_id, name, encrypted_key, public_key, ipv4),
    )


async def delete_vpn_profile(db: aiosqlite.Connection, profile_id: int) -> None:
    await db.execute("DELETE FROM vpn_profiles WHERE id = ?", (profile_id,))
    await db.commit()


async def get_profile_public_key(db: aiosqlite.Connection, profile_id: int) -> str | None:
    cursor = await db.execute(
        "SELECT public_key FROM vpn_profiles WHERE id = ?", (profile_id,)
    )
    row = await cursor.fetchone()
    return row["public_key"] if row else None


async def get_monthly_usage_rows(
    db: aiosqlite.Connection, user_id: int
) -> list[aiosqlite.Row]:
    cursor = await db.execute(
        "SELECT id, name, public_key, ipv4_address, monthly_offset_bytes "
        "FROM vpn_profiles WHERE user_id = ?",
        (user_id,),
    )
    return await cursor.fetchall()


async def get_all_active_profiles(db: aiosqlite.Connection) -> list[aiosqlite.Row]:
    """All profiles with public_key and ipv4 — used for peer recovery on startup."""
    cursor = await db.execute(
        "SELECT public_key, ipv4_address FROM vpn_profiles"
    )
    return await cursor.fetchall()


# ── Statistics ─────────────────────────────────────────────────────────────────

async def get_global_stats(db: aiosqlite.Connection) -> aiosqlite.Row:
    cursor = await db.execute(
        """SELECT
            (SELECT COUNT(*) FROM users) AS total_users,
            (SELECT COUNT(*) FROM users WHERE is_approved = 1) AS approved,
            (SELECT COUNT(*) FROM approvals WHERE status = 'pending') AS pending,
            (SELECT COUNT(*) FROM vpn_profiles) AS total_profiles,
            (SELECT COUNT(*) FROM users WHERE DATE(registered_at) = DATE('now')) AS new_today,
            (SELECT COUNT(*) FROM users WHERE DATE(registered_at) >= DATE('now', '-7 days')) AS new_week
        """
    )
    return await cursor.fetchone()


