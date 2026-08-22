from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.pool import StaticPool

from src.core.database import Database
from src.core.migrations import MigrationRegistry
from src.membership import service
from src.membership.models import register_migrations


class FakeBot:
    def __init__(self) -> None:
        self.sent: list[tuple[int, str]] = []

    async def send_message(self, chat_id: int, text: str, **kwargs: Any) -> None:
        self.sent.append((chat_id, text))


@pytest.fixture
async def db() -> Database:
    registry = MigrationRegistry()
    register_migrations(registry)
    database = Database("sqlite+aiosqlite://", poolclass=StaticPool)
    await database.init_database(registry)
    yield database
    await database.dispose()


async def _seed_expiring(db: Database, days_from_now: int = 2) -> int:
    from datetime import datetime, timedelta

    end_at = (datetime.now() + timedelta(days=days_from_now)).isoformat()
    async with db.transaction() as conn:
        await conn.execute(text("INSERT INTO plans (name, price) VALUES ('Club', 500)"))
        row = await conn.execute(text("SELECT id FROM plans LIMIT 1"))
        plan_id = int(row.scalar_one())
        await conn.execute(
            text(
                "INSERT INTO subscriptions (user_id, plan_id, start_at, end_at, status)"
                " VALUES (42, :pid, :start, :end, 'active')"
            ),
            {"pid": plan_id, "start": datetime.now().isoformat(), "end": end_at},
        )
        row = await conn.execute(text("SELECT id FROM subscriptions LIMIT 1"))
        return int(row.scalar_one())


async def test_reminder_sent_once_not_spammed(db: Database) -> None:
    sub_id = await _seed_expiring(db)
    bot = FakeBot()

    first = await service.get_expiring_subscriptions(db, days_ahead=3)
    assert len(first) == 1
    for sub in first:
        await bot.send_message(int(str(sub["user_id"])), "remind")
        await service.mark_renewal_reminded(db, int(str(sub["id"])))

    second = await service.get_expiring_subscriptions(db, days_ahead=3)
    assert second == []
    assert len(bot.sent) == 1

    async with db.session() as conn:
        row = await conn.execute(
            text("SELECT renewal_reminded_at FROM subscriptions WHERE id = :sid"),
            {"sid": sub_id},
        )
        assert row.scalar_one() is not None


async def test_renewal_migration_applied(db: Database) -> None:
    async with db.session() as conn:
        cols = (await conn.execute(text("PRAGMA table_info(subscriptions)"))).all()
    names = {row[1] for row in cols}
    assert "renewal_reminded_at" in names


async def test_far_subscription_not_reminded_early(db: Database) -> None:
    await _seed_expiring(db, days_from_now=30)
    assert await service.get_expiring_subscriptions(db, days_ahead=3) == []
