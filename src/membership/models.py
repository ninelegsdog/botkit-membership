from src.core.migrations import Migration, MigrationRegistry

MIGRATION = Migration(
    version=1,
    name="membership_init",
    statements=(
        """CREATE TABLE IF NOT EXISTS plans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            price INTEGER NOT NULL DEFAULT 0,
            period_days INTEGER NOT NULL DEFAULT 30,
            is_active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )""",
        """CREATE TABLE IF NOT EXISTS subscribers (
            user_id INTEGER PRIMARY KEY,
            name TEXT,
            username TEXT,
            is_active INTEGER NOT NULL DEFAULT 1
        )""",
        """CREATE TABLE IF NOT EXISTS subscriptions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES subscribers(user_id),
            plan_id INTEGER NOT NULL REFERENCES plans(id),
            start_at TEXT NOT NULL,
            end_at TEXT NOT NULL,
            auto_renew INTEGER NOT NULL DEFAULT 1,
            payment_id TEXT,
            status TEXT NOT NULL DEFAULT 'active',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )""",
        """CREATE TABLE IF NOT EXISTS payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            subscription_id INTEGER NOT NULL REFERENCES subscriptions(id),
            provider TEXT NOT NULL,
            amount INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            external_id TEXT,
            UNIQUE(external_id)
        )""",
        """CREATE TABLE IF NOT EXISTS content_sections (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            position INTEGER NOT NULL DEFAULT 0,
            is_active INTEGER NOT NULL DEFAULT 1
        )""",
        """CREATE TABLE IF NOT EXISTS content_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            section_id INTEGER NOT NULL REFERENCES content_sections(id),
            type TEXT NOT NULL DEFAULT 'text',
            payload TEXT NOT NULL,
            is_active INTEGER NOT NULL DEFAULT 1
        )""",
        """CREATE TABLE IF NOT EXISTS polls (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            question TEXT NOT NULL,
            options TEXT NOT NULL,
            is_active INTEGER NOT NULL DEFAULT 1,
            anonymous INTEGER NOT NULL DEFAULT 1
        )""",
        """CREATE TABLE IF NOT EXISTS poll_votes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            poll_id INTEGER NOT NULL REFERENCES polls(id),
            user_id INTEGER NOT NULL,
            option INTEGER NOT NULL,
            UNIQUE(poll_id, user_id)
        )""",
        """CREATE TABLE IF NOT EXISTS broadcasts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            text TEXT NOT NULL,
            sent_at TEXT,
            delivered INTEGER NOT NULL DEFAULT 0,
            failed INTEGER NOT NULL DEFAULT 0
        )""",
        "CREATE INDEX IF NOT EXISTS idx_subscriptions_user_status ON subscriptions(user_id, status)",
        "CREATE INDEX IF NOT EXISTS idx_subscriptions_end_at ON subscriptions(end_at)",
        "CREATE INDEX IF NOT EXISTS idx_payments_external ON payments(external_id)",
        "CREATE INDEX IF NOT EXISTS idx_content_items_section ON content_items(section_id, is_active)",
    ),
)


def register_migrations(registry: MigrationRegistry) -> None:
    registry.add(MIGRATION)
