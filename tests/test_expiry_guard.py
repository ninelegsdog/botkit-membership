"""F4: доступ по подписке закрывается по ДАТЕ синхронно, а не фоновым циклом.

Факт плана bot-fixes F4: ветка «подписка истекла» из кода недостижима —
get_subscription фильтрует только по status, а status пишет лишь
expiration_loop. Строка с датой глубоко в прошлом циклом не двигается
(переход active→grace берёт только окно вокруг истечения), а триал не
переводится вовсе — триал-доступ бессрочен. Ферменный кейс
membership-expired-closes-access закрывал фикстуру ручным status='expired',
маскируя дефект.

Негативный контроль (план: «убрать гард — кейс падает»): убрать фильтр
`end_at > :cutoff` из get_subscription — тесты с лapsed-датой падают (доступ
открыт), как ферменный кейс без гарда.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.pool import StaticPool

from src.core.database import Database
from src.core.migrations import MigrationRegistry
from src.membership import service
from src.membership.models import register_migrations

GRACE_DAYS = 3


@pytest.fixture
async def db() -> Database:
    registry = MigrationRegistry()
    register_migrations(registry)
    database = Database("sqlite+aiosqlite://", poolclass=StaticPool)
    await database.init_database(registry)
    yield database
    await database.dispose()


async def _seed_sub(
    db: Database, *, status: str, days_from_end: float, user_id: int = 77
) -> int:
    """Подписка user_id: срок относительно сейчас (−10 = прошло на 10 дней)."""
    now = datetime.now()
    end = (now + timedelta(days=days_from_end)).isoformat()
    async with db.transaction() as conn:
        await conn.execute(text("INSERT INTO plans (name, price) VALUES ('Клуб', 590)"))
        row = await conn.execute(text("SELECT id FROM plans ORDER BY id DESC LIMIT 1"))
        plan_id = int(row.scalar_one())
        await conn.execute(
            text(
                "INSERT INTO subscriptions (user_id, plan_id, start_at, end_at, status)"
                " VALUES (:uid, :pid, :start, :end, :status)"
            ),
            {
                "uid": user_id,
                "pid": plan_id,
                "start": now.isoformat(),
                "end": end,
                "status": status,
            },
        )
    return user_id


async def _status(db: Database, user_id: int) -> str | None:
    async with db.session() as conn:
        row = await conn.execute(
            text("SELECT status FROM subscriptions WHERE user_id = :uid"),
            {"uid": user_id},
        )
        return row.scalar_one_or_none()


# ---------- синхронный гард по дате (ядро F4) ----------


async def test_active_sub_with_lapsed_date_closes_access_synchronously(db):
    """Срок прошёл больше grace_days — доступ закрыт НЕМЕДЛЕННО, без цикла.

    Красное до правки: get_subscription смотрит только на status='active' и
    возвращает строку — разделы контента открыты при любой давности срока.
    """
    uid = await _seed_sub(db, status="active", days_from_end=-10)
    assert await service.get_subscription(db, uid) is None
    assert await service.is_subscriber(db, uid) is False


async def test_trial_sub_with_lapsed_date_closes_access_synchronously(db):
    """Триал с прошедшим сроком: раньше висел активным вечно — триала в цикле
    переходов не было вообще."""
    uid = await _seed_sub(db, status="trial", days_from_end=-10)
    assert await service.is_subscriber(db, uid) is False


async def test_grace_window_still_opens_access(db):
    """Продуктова семантика grace не страдает: срок прошёл на день, внутри
    grace_days=3 доступ остаётся."""
    uid = await _seed_sub(db, status="active", days_from_end=-1)
    assert await service.is_subscriber(db, uid) is True


async def test_future_sub_opens_access(db):
    uid = await _seed_sub(db, status="active", days_from_end=21)
    assert await service.is_subscriber(db, uid) is True


# ---------- фоновый цикл дописывает статусы по данным ----------


async def test_expire_flips_lapsed_active_to_grace(db):
    """Истёк в пределах grace-окна — уходит в grace (исходное поведение цикла,
    пин против регрессии при расширении переходов)."""
    uid = await _seed_sub(db, status="active", days_from_end=-1)
    assert await service.expire_subscriptions(db, GRACE_DAYS) >= 1
    assert await _status(db, uid) == "grace"


async def test_expire_flips_trial_to_grace_then_expired(db):
    """Красное до правки: expire_subscriptions двигает только status='active',
    trial-строка навсегда остаётся 'trial'."""
    uid = await _seed_sub(db, status="trial", days_from_end=-1)
    await service.expire_subscriptions(db, GRACE_DAYS)
    assert await _status(db, uid) == "grace"

    async with db.transaction() as conn:
        await conn.execute(
            text(
                "UPDATE subscriptions SET end_at = :end WHERE user_id = :uid"
            ),
            {
                "end": (datetime.now() - timedelta(days=10)).isoformat(),
                "uid": uid,
            },
        )
    await service.expire_subscriptions(db, GRACE_DAYS)
    assert await _status(db, uid) == "expired"


async def test_expire_flips_deep_lapsed_active_straight_to_expired(db):
    """Красное до правки: дата глубоко в прошлом выпадает из grace-окна, и
    строка висит status='active' вечно, пока её не тронет покупка."""
    uid = await _seed_sub(db, status="active", days_from_end=-10)
    await service.expire_subscriptions(db, GRACE_DAYS)
    assert await _status(db, uid) == "expired"
