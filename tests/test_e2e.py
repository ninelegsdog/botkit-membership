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


async def test_trial_flow(db):
    from src.membership import service

    # Create plan
    async with db.transaction() as conn:
        await conn.execute(
            text("INSERT INTO plans (name, price, period_days) VALUES ('Basic', 500, 30)")
        )

    # Ensure subscriber
    await service.ensure_subscriber(db, 100, "User1", "u1")

    # Create trial
    sub_id = await service.create_trial(db, 100, 1, 3)
    assert sub_id > 0

    # Check subscription
    sub = await service.get_subscription(db, 100)
    assert sub is not None
    assert sub["status"] == "trial"

    # is_subscriber
    assert await service.is_subscriber(db, 100) is True


async def test_activate_and_cancel(db):
    from src.membership import service

    async with db.transaction() as conn:
        await conn.execute(
            text("INSERT INTO plans (name, price, period_days) VALUES ('Pro', 1000, 30)")
        )

    await service.ensure_subscriber(db, 200, "User2", "u2")

    sub_id = await service.activate_subscription(db, 200, 1, 30)
    assert sub_id > 0

    sub = await service.get_subscription(db, 200)
    assert sub is not None
    assert sub["status"] == "active"
    assert sub["auto_renew"] == 1

    # Cancel
    ok = await service.cancel_subscription(db, 200)
    assert ok is True


async def test_content_access_gate(db):
    from src.membership import service

    # No subscription → not subscriber
    assert await service.is_subscriber(db, 999) is False

    # Create plan + subscription
    async with db.transaction() as conn:
        await conn.execute(
            text("INSERT INTO plans (name, price, period_days) VALUES ('Basic', 500, 30)")
        )
    await service.ensure_subscriber(db, 300, "User3", "u3")
    await service.activate_subscription(db, 300, 1, 30)

    assert await service.is_subscriber(db, 300) is True
