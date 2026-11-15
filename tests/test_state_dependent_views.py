"""State-dependent view tests for membership."""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.pool import StaticPool

from src.core.database import Database
from src.core.migrations import MigrationRegistry
from src.membership.models import register_migrations


@pytest.fixture
async def db():
    registry = MigrationRegistry()
    register_migrations(registry)
    database = Database("sqlite+aiosqlite://", poolclass=StaticPool)
    await database.init_database(registry)
    yield database
    await database.dispose()


@pytest.mark.asyncio
async def test_active_plans_empty_vs_populated(db):
    from src.membership.service import get_active_plans

    assert await get_active_plans(db) == []

    async with db.transaction() as conn:
        await conn.execute(
            text("INSERT INTO plans (id, name, price, period_days, is_active) VALUES (1, 'Basic', 100, 30, 1)")
        )
    plans = await get_active_plans(db)
    assert len(plans) == 1
    assert plans[0]["name"] == "Basic"


@pytest.mark.asyncio
async def test_get_plan_missing_vs_present(db):
    from src.membership.service import get_plan

    assert await get_plan(db, 9999) is None

    async with db.transaction() as conn:
        await conn.execute(
            text("INSERT INTO plans (id, name, price, period_days, is_active) VALUES (1, 'Basic', 100, 30, 1)")
        )
    plan = await get_plan(db, 1)
    assert plan is not None
    assert plan["name"] == "Basic"


@pytest.mark.asyncio
async def test_is_subscriber_false_vs_true(db):
    from src.membership.service import is_subscriber

    assert await is_subscriber(db, user_id=1) is False

    async with db.transaction() as conn:
        await conn.execute(text("INSERT INTO subscribers (user_id, name, is_active) VALUES (1, 'U', 1)"))
        await conn.execute(
            text("INSERT INTO plans (id, name, price, period_days, is_active) VALUES (1, 'Basic', 100, 30, 1)")
        )
        await conn.execute(
            text(
                "INSERT INTO subscriptions (id, user_id, plan_id, start_at, end_at, status) "
                "VALUES (1, 1, 1, datetime('now'), datetime('now', '+30 days'), 'active')"
            )
        )

    assert await is_subscriber(db, user_id=1) is True


@pytest.mark.asyncio
async def test_content_sections_empty_vs_populated(db):
    from src.membership.service import get_content_sections

    assert await get_content_sections(db) == []

    async with db.transaction() as conn:
        await conn.execute(
            text("INSERT INTO content_sections (id, title, position, is_active) VALUES (1, 'Sec1', 0, 1)")
        )
    sections = await get_content_sections(db)
    assert len(sections) == 1


@pytest.mark.asyncio
async def test_active_polls_empty_vs_populated(db):
    from src.membership.service import get_active_polls

    assert await get_active_polls(db) == []

    async with db.transaction() as conn:
        await conn.execute(
            text("INSERT INTO polls (id, question, options, is_active) VALUES (1, 'Q?', '[\"a\",\"b\"]', 1)")
        )
    polls = await get_active_polls(db)
    assert len(polls) == 1


@pytest.mark.asyncio
async def test_get_subscription_none_vs_present(db):
    from src.membership.service import ensure_subscriber, get_subscription

    await ensure_subscriber(db, user_id=1, name="U", username=None)
    assert await get_subscription(db, user_id=1) is None

    async with db.transaction() as conn:
        await conn.execute(
            text("INSERT INTO plans (id, name, price, period_days, is_active) VALUES (1, 'Basic', 100, 30, 1)")
        )
        await conn.execute(
            text(
                "INSERT INTO subscriptions (id, user_id, plan_id, start_at, end_at, status) "
                "VALUES (1, 1, 1, datetime('now'), datetime('now', '+30 days'), 'active')"
            )
        )

    sub = await get_subscription(db, user_id=1)
    assert sub is not None
