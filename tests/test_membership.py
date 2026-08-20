import pytest
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


async def test_get_active_plans_empty(db):
    from src.membership.service import get_active_plans

    result = await get_active_plans(db)
    assert result == []


async def test_get_plan_not_found(db):
    from src.membership.service import get_plan

    result = await get_plan(db, 999)
    assert result is None


async def test_ensure_subscriber(db):
    from src.membership.service import ensure_subscriber

    await ensure_subscriber(db, 123, "Test", "test_user")
    # Should not raise on second call (upsert)
    await ensure_subscriber(db, 123, "Test2", "test_user2")


async def test_get_subscription_none(db):
    from src.membership.service import get_subscription

    result = await get_subscription(db, 999)
    assert result is None


async def test_is_subscriber_false(db):
    from src.membership.service import is_subscriber

    result = await is_subscriber(db, 999)
    assert result is False


async def test_cancel_subscription_false(db):
    from src.membership.service import cancel_subscription

    result = await cancel_subscription(db, 999)
    assert result is False


async def test_get_active_subscribers_empty(db):
    from src.membership.service import get_active_subscribers

    result = await get_active_subscribers(db)
    assert result == []


async def test_get_content_sections_empty(db):
    from src.membership.service import get_content_sections

    result = await get_content_sections(db)
    assert result == []


async def test_get_active_polls_empty(db):
    from src.membership.service import get_active_polls

    result = await get_active_polls(db)
    assert result == []


async def test_create_poll_and_vote(db):
    from src.membership.service import create_poll, get_active_polls, get_poll_results, vote_poll

    poll_id = await create_poll(db, "Test?", '["Yes","No"]')
    assert poll_id > 0

    ok = await vote_poll(db, poll_id, 100, 0)
    assert ok is True

    # Duplicate vote fails
    ok2 = await vote_poll(db, poll_id, 100, 1)
    assert ok2 is False

    results = await get_poll_results(db, poll_id)
    assert len(results) == 1
    assert results[0]["votes"] == 1

    polls = await get_active_polls(db)
    assert len(polls) == 1
