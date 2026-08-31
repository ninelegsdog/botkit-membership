from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram import Router
from aiogram.types import (
    Chat,
    Message,
    User,
)

from src.core.auth import AdminGate, mark_admin_router, require_admin
from src.core.navigation import NavRegistry, NavSection, compose_message, escape_html, nav_header
from src.core.payments import (
    STARS_CURRENCY,
    MockPaymentProvider,
    attach_payment_handlers,
    create_payment_provider,
)


def _msg(user_id: int = 42) -> Message:
    return Message(
        message_id=1,
        date=datetime.now(UTC),
        chat=Chat(id=user_id, type="private"),
        from_user=User(id=user_id, is_bot=False, first_name="T"),
        text="hello",
    )


@pytest.mark.asyncio
async def test_admin_gate_throttle():
    gate = AdminGate("secret", [999])
    assert gate.is_admin(999) is True
    assert gate.is_admin(111) is False
    assert gate.authorize(111, "wrong") is False
    assert gate.is_throttled(111) is False
    for _ in range(5):
        gate.authorize(111, "wrong")
    assert gate.is_throttled(111) is True
    gate.authorize(111, "secret")
    assert gate.is_admin(111) is True
    assert gate.is_throttled(111) is False


@pytest.mark.asyncio
async def test_require_admin_allows_authorized():
    gate = AdminGate("secret", [42])
    called = {}

    @require_admin(gate)
    async def handler(message: Message):
        called["ok"] = True
        return "done"

    result = await handler(_msg(42))
    assert result == "done"
    assert called["ok"] is True


@pytest.mark.asyncio
async def test_require_admin_denies_unauthorized():
    gate = AdminGate("secret", [999])

    @require_admin(gate)
    async def handler(message: Message):
        return "done"

    msg = _msg(111)
    object.__setattr__(msg, "answer", AsyncMock())

    result = await handler(msg)
    assert result is None
    msg.answer.assert_awaited_once_with("⛔ Доступ запрещён.")


@pytest.mark.asyncio
async def test_require_admin_no_user_id():
    gate = AdminGate("secret", [999])

    @require_admin(gate)
    async def handler(message: Message):
        return "done"

    msg = _msg()
    object.__setattr__(msg, "from_user", None)

    result = await handler(msg)
    assert result is None


@pytest.mark.asyncio
async def test_mark_admin_router():
    r = Router()
    mark_admin_router(r)
    assert getattr(r, "_requires_admin", False) is True


def test_nav_registry_breadcrumbs():
    nav = NavRegistry()
    nav.register(NavSection("a", "Alpha"))
    nav.register(NavSection("b", "Beta"))
    assert nav.title("a") == "Alpha"
    assert nav.title("missing") == "missing"
    assert nav.breadcrumbs("a") == ["Alpha"]


def test_escape_html():
    assert escape_html("<script>") == "&lt;script&gt;"
    assert escape_html("hello") == "hello"
    assert escape_html("") == ""


def test_nav_header():
    assert nav_header([]) == ""
    assert nav_header(["a"]) == "a\n"
    assert nav_header(["a", "b"]) == "a › b\n"


def test_compose_message():
    assert compose_message([], "body") == "body"
    assert compose_message(["a"], "body") == "a\nbody"
    assert compose_message(["a", "b"], "body") == "a › b\nbody"


@pytest.mark.asyncio
async def test_mock_payment_provider():
    prov = MockPaymentProvider()
    link = await prov.create_invoice_link(title="t", description="d", payload="p", amount=100)
    assert "mock-bot/invoice/p" in link
    msg_ok = MagicMock()
    msg_ok.successful_payment = MagicMock(total_amount=100)
    assert await prov.verify_payment(msg_ok) is True
    msg_bad = MagicMock()
    msg_bad.successful_payment = None
    assert await prov.verify_payment(msg_bad) is False


def test_create_payment_provider():
    assert isinstance(create_payment_provider("mock"), MockPaymentProvider)
    with pytest.raises(ValueError):
        create_payment_provider("unknown")


@pytest.mark.asyncio
async def test_attach_payment_handlers():
    router = Router()
    provider = MockPaymentProvider()
    confirmed = {}

    async def on_confirmed(payload: str) -> None:
        confirmed["payload"] = payload

    attach_payment_handlers(router, provider, on_confirmed=on_confirmed)

    query = MagicMock()
    query.answer = AsyncMock()
    query.id = "q1"
    query.from_user = MagicMock()
    query.from_user.id = 1
    query.currency = "XTR"
    query.total_amount = 100
    query.invoice_payload = "payload123"

    for handler in router.pre_checkout_query.handlers:
        await handler.callback(query)
    query.answer.assert_awaited_once_with(ok=True)

    msg = MagicMock()
    msg.answer = AsyncMock()
    msg.successful_payment = MagicMock(
        total_amount=100,
        currency="XTR",
        invoice_payload="payload123",
    )

    for handler in router.message.handlers:
        await handler.callback(msg)
        break
    msg.answer.assert_awaited_with("Оплата подтверждена.")
    assert confirmed["payload"] == "payload123"


@pytest.mark.asyncio
async def test_payment_handler_unconfirmed():
    router = Router()
    provider = MockPaymentProvider()
    msg = MagicMock()
    msg.answer = AsyncMock()
    msg.successful_payment = MagicMock(
        total_amount=100,
        currency="XTR",
        invoice_payload="payload123",
    )
    provider.verify_payment = AsyncMock(return_value=False)
    attach_payment_handlers(router, provider)
    for handler in router.message.handlers:
        await handler.callback(msg)
        break
    msg.answer.assert_awaited_with("Оплата не подтверждена.")


def test_stars_currency():
    assert STARS_CURRENCY == "XTR"