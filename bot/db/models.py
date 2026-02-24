# SQL запросы для создания таблиц базы данных

CREATE_USERS_TABLE = """
CREATE TABLE IF NOT EXISTS users (
    telegram_id INTEGER PRIMARY KEY,
    username TEXT,
    full_name TEXT,
    is_admin BOOLEAN DEFAULT 0,
    is_approved BOOLEAN DEFAULT 0,
    registered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

CREATE_APPROVALS_TABLE = """
CREATE TABLE IF NOT EXISTS approvals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    status TEXT DEFAULT 'pending', -- pending, approved, rejected
    admin_id INTEGER,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users (telegram_id)
);
"""

CREATE_DAILY_STATS_TABLE = """
CREATE TABLE IF NOT EXISTS daily_stats (
    date DATE PRIMARY KEY,
    total_users INTEGER DEFAULT 0,
    new_users INTEGER DEFAULT 0,
    approved_count INTEGER DEFAULT 0,
    requests_count INTEGER DEFAULT 0
);
"""

CREATE_CONFIGS_TABLE = """
CREATE TABLE IF NOT EXISTS configs (
    key TEXT PRIMARY KEY,
    value TEXT
);
"""

CREATE_PROFILES_TABLE = """
CREATE TABLE IF NOT EXISTS vpn_profiles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    name TEXT,
    private_key TEXT,
    public_key TEXT,
    ipv4_address TEXT,
    monthly_offset_bytes INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users (telegram_id)
);
"""

CREATE_PROFILES_IPV4_UNIQUE_INDEX = """
CREATE UNIQUE INDEX IF NOT EXISTS idx_vpn_profiles_ipv4_unique
ON vpn_profiles(ipv4_address)
WHERE ipv4_address IS NOT NULL AND ipv4_address <> '';
"""

CREATE_PROFILES_PUBLIC_KEY_UNIQUE_INDEX = """
CREATE UNIQUE INDEX IF NOT EXISTS idx_vpn_profiles_public_key_unique
ON vpn_profiles(public_key)
WHERE public_key IS NOT NULL AND public_key <> '';
"""

ALL_TABLES = [
    CREATE_USERS_TABLE,
    CREATE_APPROVALS_TABLE,
    CREATE_DAILY_STATS_TABLE,
    CREATE_CONFIGS_TABLE,
    CREATE_PROFILES_TABLE,
    CREATE_PROFILES_IPV4_UNIQUE_INDEX,
    CREATE_PROFILES_PUBLIC_KEY_UNIQUE_INDEX,
]
