from datetime import datetime, timedelta

from sqlalchemy import text

from src.core.database import Database


async def get_active_plans(db: Database) -> list[dict[str, object]]:
    async with db.session() as conn:
        result = await conn.execute(
            text("SELECT id, name, price, period_days FROM plans WHERE is_active = 1 ORDER BY price")
        )
        return [dict(row._mapping) for row in result.all()]


async def get_plan(db: Database, plan_id: int) -> dict[str, object] | None:
    async with db.session() as conn:
        result = await conn.execute(text("SELECT * FROM plans WHERE id = :id"), {"id": plan_id})
        row = result.first()
        return dict(row._mapping) if row else None


async def ensure_subscriber(db: Database, user_id: int, name: str, username: str | None) -> None:
    async with db.transaction() as conn:
        await conn.execute(
            text(
                "INSERT INTO subscribers (user_id, name, username, is_active) "
                "VALUES (:uid, :name, :username, 1) "
                "ON CONFLICT(user_id) DO UPDATE SET name = :name, username = :username"
            ),
            {"uid": user_id, "name": name, "username": username or ""},
        )


async def get_subscription(db: Database, user_id: int) -> dict[str, object] | None:
    async with db.session() as conn:
        result = await conn.execute(
            text(
                "SELECT s.*, p.name as plan_name, p.period_days "
                "FROM subscriptions s JOIN plans p ON s.plan_id = p.id "
                "WHERE s.user_id = :uid AND s.status IN ('active', 'trial', 'grace') "
                "ORDER BY s.end_at DESC LIMIT 1"
            ),
            {"uid": user_id},
        )
        row = result.first()
        return dict(row._mapping) if row else None


async def is_subscriber(db: Database, user_id: int) -> bool:
    sub = await get_subscription(db, user_id)
    return sub is not None


async def create_trial(db: Database, user_id: int, plan_id: int, trial_days: int) -> int:
    now = datetime.now()
    end = now + timedelta(days=trial_days)
    async with db.transaction() as conn:
        result = await conn.execute(
            text(
                "INSERT INTO subscriptions (user_id, plan_id, start_at, end_at, auto_renew, status) "
                "VALUES (:uid, :pid, :start, :end, 0, 'trial') RETURNING id"
            ),
            {"uid": user_id, "pid": plan_id, "start": now.isoformat(), "end": end.isoformat()},
        )
        row = result.first()
        return int(row[0]) if row else 0


async def activate_subscription(
    db: Database, user_id: int, plan_id: int, period_days: int
) -> int:
    now = datetime.now()
    end = now + timedelta(days=period_days)
    async with db.transaction() as conn:
        # Deactivate old subscriptions
        await conn.execute(
            text(
                "UPDATE subscriptions SET status = 'expired' "
                "WHERE user_id = :uid AND status IN ('active', 'trial', 'grace')"
            ),
            {"uid": user_id},
        )
        result = await conn.execute(
            text(
                "INSERT INTO subscriptions (user_id, plan_id, start_at, end_at, auto_renew, status) "
                "VALUES (:uid, :pid, :start, :end, 1, 'active') RETURNING id"
            ),
            {"uid": user_id, "pid": plan_id, "start": now.isoformat(), "end": end.isoformat()},
        )
        row = result.first()
        return int(row[0]) if row else 0


async def cancel_subscription(db: Database, user_id: int) -> bool:
    async with db.transaction() as conn:
        result = await conn.execute(
            text("UPDATE subscriptions SET auto_renew = 0 WHERE user_id = :uid AND status = 'active'"),
            {"uid": user_id},
        )
        return bool(result.rowcount and result.rowcount > 0)  # type: ignore[attr-defined]


async def get_active_subscribers(db: Database) -> list[dict[str, object]]:
    async with db.session() as conn:
        result = await conn.execute(
            text(
                "SELECT u.user_id, u.name, u.username, s.end_at, p.name as plan_name "
                "FROM subscribers u "
                "JOIN subscriptions s ON u.user_id = s.user_id "
                "JOIN plans p ON s.plan_id = p.id "
                "WHERE s.status IN ('active', 'trial') "
                "ORDER BY s.end_at"
            )
        )
        return [dict(row._mapping) for row in result.all()]


async def get_expiring_subscriptions(db: Database, days_ahead: int = 3) -> list[dict[str, object]]:
    cutoff = (datetime.now() + timedelta(days=days_ahead)).isoformat()
    async with db.session() as conn:
        result = await conn.execute(
            text(
                "SELECT s.id, s.user_id, s.end_at, p.name as plan_name "
                "FROM subscriptions s JOIN plans p ON s.plan_id = p.id "
                "WHERE s.status = 'active' AND s.end_at <= :cutoff "
                "AND s.renewal_reminded_at IS NULL "
                "ORDER BY s.end_at"
            ),
            {"cutoff": cutoff},
        )
        return [dict(row._mapping) for row in result.all()]


async def mark_renewal_reminded(db: Database, subscription_id: int) -> None:
    async with db.transaction() as conn:
        await conn.execute(
            text(
                "UPDATE subscriptions SET renewal_reminded_at = :now WHERE id = :sid"
            ),
            {"now": datetime.now().isoformat(), "sid": subscription_id},
        )


async def expire_subscriptions(db: Database, grace_days: int) -> int:
    now = datetime.now()
    grace_cutoff = (now - timedelta(days=grace_days)).isoformat()
    async with db.transaction() as conn:
        # Active → grace (past end_at)
        result = await conn.execute(
            text(
                "UPDATE subscriptions SET status = 'grace' "
                "WHERE status = 'active' AND end_at < :now AND end_at > :grace"
            ),
            {"now": now.isoformat(), "grace": grace_cutoff},
        )
        grace_count = int(result.rowcount or 0)  # type: ignore[attr-defined]

        # Grace → expired (past grace period)
        result2 = await conn.execute(
            text("UPDATE subscriptions SET status = 'expired' WHERE status = 'grace' AND end_at <= :grace"),
            {"grace": grace_cutoff},
        )
        expired_count = int(result2.rowcount or 0)  # type: ignore[attr-defined]

        return grace_count + expired_count


async def get_content_sections(db: Database) -> list[dict[str, object]]:
    async with db.session() as conn:
        result = await conn.execute(
            text("SELECT id, title, position FROM content_sections WHERE is_active = 1 ORDER BY position")
        )
        return [dict(row._mapping) for row in result.all()]


async def get_content_items(db: Database, section_id: int) -> list[dict[str, object]]:
    async with db.session() as conn:
        result = await conn.execute(
            text("SELECT id, type, payload FROM content_items WHERE section_id = :sid AND is_active = 1"),
            {"sid": section_id},
        )
        return [dict(row._mapping) for row in result.all()]


async def create_poll(db: Database, question: str, options: str, anonymous: bool = True) -> int:
    async with db.transaction() as conn:
        result = await conn.execute(
            text(
                "INSERT INTO polls (question, options, is_active, anonymous) "
                "VALUES (:q, :o, 1, :an) RETURNING id"
            ),
            {"q": question, "o": options, "an": 1 if anonymous else 0},
        )
        row = result.first()
        return int(row[0]) if row else 0


async def vote_poll(db: Database, poll_id: int, user_id: int, option: int) -> bool:
    async with db.transaction() as conn:
        try:
            await conn.execute(
                text("INSERT INTO poll_votes (poll_id, user_id, option) VALUES (:pid, :uid, :opt)"),
                {"pid": poll_id, "uid": user_id, "opt": option},
            )
            return True
        except Exception:
            return False


async def get_poll_results(db: Database, poll_id: int) -> list[dict[str, object]]:
    async with db.session() as conn:
        result = await conn.execute(
            text(
                "SELECT option, COUNT(*) as votes FROM poll_votes WHERE poll_id = :pid GROUP BY option ORDER BY option"
            ),
            {"pid": poll_id},
        )
        return [dict(row._mapping) for row in result.all()]


async def get_active_polls(db: Database) -> list[dict[str, object]]:
    async with db.session() as conn:
        result = await conn.execute(
            text("SELECT id, question, options, anonymous FROM polls WHERE is_active = 1")
        )
        return [dict(row._mapping) for row in result.all()]
