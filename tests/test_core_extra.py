from __future__ import annotations

import asyncio
import time
from contextlib import suppress
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core import bot_factory, errors, fsm, metrics, payments, sentry, storage, throttling, webhook
from src.core.config import Settings, parse_admin_ids
from src.membership import models
from src.membership.nav import NAV_SECTION


# ---------- config ----------
def test_parse_admin_ids():
    assert parse_admin_ids(None) == []
    assert parse_admin_ids("") == []
    assert parse_admin_ids("1,2,3") == [1, 2, 3]
    assert parse_admin_ids(" 1 , 2 ") == [1, 2]


def test_settings_valid(monkeypatch):
    monkeypatch.setenv("BOTKIT__BOT_TOKEN", "tok")
    monkeypatch.setenv("BOTKIT__ADMIN_PASSWORD", "pw")
    monkeypatch.setenv("BOTKIT__ADMIN_IDS", "[1,2]")
    s = Settings()
    assert s.bot_token == "tok"
    assert s.admin_ids == [1, 2]
    assert s.metrics_port == 8085
    assert s.trial_days == 3
    assert s.grace_days == 3


@pytest.mark.parametrize("var", ["BOTKIT__BOT_TOKEN", "BOTKIT__ADMIN_PASSWORD", "BOTKIT__ADMIN_IDS"])
def test_settings_missing_required(var, monkeypatch):
    monkeypatch.delenv("BOTKIT__BOT_TOKEN", raising=False)
    monkeypatch.delenv("BOTKIT__ADMIN_PASSWORD", raising=False)
    monkeypatch.delenv("BOTKIT__ADMIN_IDS", raising=False)
    with pytest.raises(RuntimeError):
        Settings()


# ---------- fsm ----------
def test_is_command():
    assert fsm.is_command("/start") is True
    assert fsm.is_command("hi") is False
    assert fsm.is_command(None) is False


def test_text_not_command():
    assert fsm.text_not_command(SimpleNamespace(text="/x")) is False
    assert fsm.text_not_command(SimpleNamespace(text="hi")) is True


# ---------- nav ----------
def test_nav_section_constant():
    assert NAV_SECTION.slug == "membership"
    assert NAV_SECTION.title == "Клуб"


# ---------- storage ----------
def test_create_storage_memory():
    assert isinstance(storage.create_storage(None), storage.MemoryStorage)


def test_create_storage_redis(monkeypatch):
    fake = MagicMock()
    with patch.dict(
        "sys.modules",
        {
            "redis": MagicMock(),
            "redis.asyncio": MagicMock(from_url=lambda u: fake),
            "aiogram.fsm.storage.redis": MagicMock(RedisStorage=MagicMock),
        },
    ):
        result = storage.create_storage("redis://x")
    assert isinstance(result, MagicMock)


# ---------- throttling ----------
@pytest.fixture
def throttle_mw():
    mw = throttling.ThrottlingMiddleware("redis://x")
    mw._redis = AsyncMock()
    mw._redis.get.return_value = None
    return mw


async def test_throttle_allows_first(throttle_mw):
    handler = AsyncMock(return_value="ok")
    event = SimpleNamespace(from_user=SimpleNamespace(id=1))
    assert await throttle_mw(handler, event, {}) == "ok"
    assert handler.await_count == 1


async def test_throttle_blocks_recent(throttle_mw):
    handler = AsyncMock(return_value="ok")
    event = SimpleNamespace(from_user=SimpleNamespace(id=1))
    await throttle_mw(handler, event, {})
    throttle_mw._redis.get.return_value = str(time.time())
    assert await throttle_mw(handler, event, {}) is None
    assert handler.await_count == 1


async def test_throttle_no_user_passes(throttle_mw):
    handler = AsyncMock(return_value="ok")
    event = SimpleNamespace(from_user=None)
    assert await throttle_mw(handler, event, {}) == "ok"


async def test_throttle_redis_error_passes(throttle_mw):
    handler = AsyncMock(return_value="ok")
    throttle_mw._redis.get.side_effect = RuntimeError("boom")
    event = SimpleNamespace(from_user=SimpleNamespace(id=2))
    assert await throttle_mw(handler, event, {}) == "ok"


# ---------- webhook ----------
def test_build_webhook_app():
    from aiohttp import web

    app = webhook.build_webhook_app(MagicMock(), MagicMock(), "tok")
    assert isinstance(app, web.Application)
    paths = {r.resource.canonical for r in app.router.routes()}
    assert "/webhook" in paths


# ---------- metrics ----------
async def test_updates_middleware_counts():
    mw = metrics.UpdatesMiddleware()
    handler = AsyncMock(return_value="x")
    assert await mw(handler, object(), {}) == "x"
    assert handler.await_count == 1


async def test_health_and_metrics():
    resp = await metrics.health(MagicMock())
    assert resp.text == "ok"
    resp = await metrics.metrics(MagicMock())
    assert resp.body == metrics.generate_latest()


def test_create_metrics_app():
    app = metrics.create_metrics_app()
    paths = {r.resource.canonical for r in app.router.routes()}
    assert "/health" in paths and "/metrics" in paths


async def test_start_metrics_server():
    runner = await metrics.start_metrics_server(0)
    try:
        assert runner is not None
    finally:
        await runner.cleanup()


# ---------- payments ----------
async def test_mock_provider():
    p = payments.MockPaymentProvider()
    link = await p.create_invoice_link(title="t", description="d", payload="P1", amount=5)
    assert link == "https://t.me/mock-bot/invoice/P1"
    assert await p.verify_payment(SimpleNamespace(successful_payment=SimpleNamespace(total_amount=10))) is True
    assert await p.verify_payment(SimpleNamespace(successful_payment=None)) is False


def test_create_payment_provider():
    assert isinstance(payments.create_payment_provider("mock"), payments.MockPaymentProvider)
    with pytest.raises(ValueError):
        payments.create_payment_provider("bad")


def test_create_payment_provider_yookassa(monkeypatch):
    if pytest.importorskip("yookassa", reason="yookassa not installed") is None:
        return
    prov = payments.create_payment_provider("yookassa", shop_id="s", secret_key="k")
    assert isinstance(prov, payments.YooKassaPaymentProvider)


def test_attach_payment_handlers():
    from aiogram import Router

    router = Router()
    captured = {}

    async def on_confirmed(payload: str) -> None:
        captured["p"] = payload

    payments.attach_payment_handlers(router, payments.MockPaymentProvider(), on_confirmed=on_confirmed)
    assert len(router.observers.get("pre_checkout_query").handlers) >= 1
    assert len(router.observers.get("message").handlers) >= 1


# ---------- sentry ----------
def test_init_sentry_none():
    assert sentry.init_sentry(None) is None


def test_init_sentry_no_raise():
    # should never raise, regardless of whether sentry_sdk is installed
    sentry.init_sentry("https://example@sentry.io/1")


# ---------- bot_factory ----------
def test_create_bot():
    from aiogram import Bot

    assert isinstance(bot_factory.create_bot("123456789:AAfake"), Bot)


def test_build_dispatcher():
    from aiogram import Dispatcher, Router

    dp = bot_factory.build_dispatcher()
    assert isinstance(dp, Dispatcher)
    r = Router()
    dp2 = bot_factory.build_dispatcher(routers=[r])
    assert len(dp2.sub_routers) == 1
    dp3 = bot_factory.build_dispatcher(storage=storage.MemoryStorage())
    assert dp3.storage is not None
    dp4 = bot_factory.build_dispatcher(throttling=object())
    assert isinstance(dp4, Dispatcher) and dp4.message.middleware is not None


# ---------- app ----------
def test_collect_routers():
    from aiogram import Router

    from src.core.auth import AdminGate
    from src.core.navigation import NavRegistry

    routers = __import__("src.app", fromlist=["collect_routers"]).collect_routers(
        gate=AdminGate("x"), nav=NavRegistry(), db=MagicMock()
    )
    assert len(routers) == 2
    assert all(isinstance(r, Router) for r in routers)


# ---------- scheduler ----------
async def test_expiration_loop_runs_once():
    db = MagicMock()
    bot = MagicMock()
    bot.send_message = AsyncMock()
    with patch("src.membership.service.expire_subscriptions", new=AsyncMock(return_value=2)), patch(
        "src.membership.service.get_expiring_subscriptions",
        new=AsyncMock(return_value=[{"id": 1, "user_id": 5, "end_at": "2030-01-01"}]),
    ), patch("src.membership.service.mark_renewal_reminded", new=AsyncMock()):
        task = asyncio.create_task(
            __import__("src.reminder.scheduler", fromlist=["expiration_loop"]).expiration_loop(
                db, bot, interval=0.01
            )
        )
        await asyncio.sleep(0.05)
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task
        from src.membership import service
        assert service.expire_subscriptions.await_count >= 1
        assert service.get_expiring_subscriptions.await_count >= 1
        assert bot.send_message.await_count >= 1
        assert service.mark_renewal_reminded.await_count >= 1


# ---------- errors ----------
async def test_default_error_handler_retry_after():
    e = __import__("aiogram.exceptions", fromlist=["TelegramRetryAfter"]).TelegramRetryAfter(None, "r", 0)
    await errors.default_error_handler(object(), e)


async def test_default_error_handler_network():
    e = __import__("aiogram.exceptions", fromlist=["TelegramNetworkError"]).TelegramNetworkError(None, "n")
    await errors.default_error_handler(object(), e)


async def test_default_error_handler_unhandled():
    await errors.default_error_handler(object(), RuntimeError("x"))


def test_register_error_handler():
    fake_dp = SimpleNamespace(error=MagicMock(return_value=MagicMock()))
    errors.register_error_handler(fake_dp)  # must not raise


async def test_retry_middleware_retries():
    mw = errors.RetryMiddleware(max_retries=3, delay=0)
    calls = {"n": 0}

    async def handler(event, data):
        calls["n"] += 1
        if calls["n"] < 3:
            e = __import__("aiogram.exceptions", fromlist=["TelegramRetryAfter"]).TelegramRetryAfter(None, "r", 0)
            raise e
        return "ok"

    assert await mw(handler, object(), {}) == "ok"
    assert calls["n"] == 3


# ---------- membership models ----------
def test_register_migrations():
    reg = MagicMock()
    models.register_migrations(reg)
    assert reg.add.call_count == 2
