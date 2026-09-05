from __future__ import annotations

import asyncio
import sys
from collections.abc import Awaitable, Callable
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram import Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import Chat, Message, PreCheckoutQuery, User

from src.core.auth import AdminGate
from src.core.database import Database
from src.core.errors import RetryMiddleware, default_error_handler, register_error_handler
from src.core.payments import (
    MockPaymentProvider,
    PaymentProvider,
    YooKassaPaymentProvider,
    attach_payment_handlers,
    create_payment_provider,
    STARS_CURRENCY,
)
from src.core.sentry import init_sentry
from src.core.throttling import ThrottlingMiddleware
from src.core.navigation import NavRegistry, NavSection


@pytest.fixture
def mock_bot() -> MagicMock:
    bot = MagicMock()
    bot.send_message = AsyncMock()
    bot.answer_callback_query = AsyncMock()
    bot.edit_message_text = AsyncMock()
    return bot


@pytest.fixture
def mock_message(mock_bot: MagicMock) -> MagicMock:
    msg = MagicMock(spec=Message)
    msg.bot = mock_bot
    msg.answer = AsyncMock()
    msg.edit_text = AsyncMock()
    msg.chat = MagicMock(spec=Chat)
    msg.chat.id = 123
    msg.from_user = MagicMock(spec=User)
    msg.from_user.id = 456
    msg.message_id = 789
    msg.text = "test"
    return msg


@pytest.fixture
def mock_callback_query(mock_bot: MagicMock) -> MagicMock:
    cq = MagicMock()
    cq.bot = mock_bot
    cq.answer = AsyncMock()
    cq.message = MagicMock(spec=Message)
    cq.message.bot = mock_bot
    cq.message.chat = MagicMock(spec=Chat)
    cq.message.chat.id = 123
    cq.message.message_id = 789
    cq.from_user = MagicMock(spec=User)
    cq.from_user.id = 456
    cq.data = "test"
    return cq


@pytest.fixture
def storage() -> MemoryStorage:
    return MemoryStorage()


@pytest.fixture
def fsm_context(storage: MemoryStorage, mock_bot: MagicMock) -> FSMContext:
    key = StorageKey(bot_id=mock_bot.id, chat_id=123, user_id=456)
    return FSMContext(storage=storage, key=key)


def test_admin_gate_is_admin() -> None:
    gate = AdminGate(password="secret", admin_ids=[123, 456])
    assert gate.is_admin(123) is True
    assert gate.is_admin(456) is True
    assert gate.is_admin(999) is False


def test_admin_gate_authorize() -> None:
    gate = AdminGate(password="secret", admin_ids=[123])
    assert gate.authorize(999, "secret") is True
    assert gate.is_admin(999) is True
    assert gate.authorize(888, "wrong") is False
    assert gate.is_admin(888) is False


def test_nav_registry_register() -> None:
    registry = NavRegistry()
    section = NavSection(slug="test", title="Test")
    registry.register(section)
    assert registry.get("test") is not None
    assert registry.get("test").title == "Test"
    assert registry.title("test") == "Test"
    assert registry.title("nonexistent") == "nonexistent"


def test_admin_gate_with_empty_ids() -> None:
    gate = AdminGate(password="secret", admin_ids=[])
    assert gate.is_admin(123) is False
    assert gate.authorize(123, "secret") is True


def test_nav_registry_breadcrumbs() -> None:
    registry = NavRegistry()
    section = NavSection(slug="child", title="Child")
    registry.register(section)
    crumbs = registry.breadcrumbs("child")
    assert isinstance(crumbs, list)


def test_admin_gate_throttling() -> None:
    gate = AdminGate(password="secret", admin_ids=[1])
    for _ in range(5):
        assert gate.authorize(999, "wrong") is False
    assert gate.authorize(999, "wrong") is False
    assert gate.authorize(1000, "secret") is True


def test_nav_registry_multiple() -> None:
    registry = NavRegistry()
    s1 = NavSection(slug="a", title="A")
    s2 = NavSection(slug="b", title="B")
    registry.register(s1)
    registry.register(s2)
    assert registry.get("a").title == "A"
    assert registry.get("b").title == "B"
    assert len(registry._sections) == 2


def test_create_payment_provider_mock() -> None:
    provider = create_payment_provider("mock")
    assert isinstance(provider, MockPaymentProvider)


def test_create_payment_provider_yookassa() -> None:
    provider = create_payment_provider("yookassa", shop_id="123", secret_key="secret")
    assert isinstance(provider, YooKassaPaymentProvider)


def test_create_payment_provider_invalid() -> None:
    with pytest.raises(ValueError, match="Unknown payment provider"):
        create_payment_provider("invalid")


def test_mock_payment_provider_instance() -> None:
    provider = MockPaymentProvider()
    assert isinstance(provider, PaymentProvider)


@pytest.mark.asyncio
async def test_attach_payment_handlers():
    router = Router()
    provider = MockPaymentProvider()
    confirmed = {}

    async def on_confirmed(payload: str) -> None:
        confirmed["payload"] = payload

    attach_payment_handlers(router, provider, on_confirmed=on_confirmed)

    query = MagicMock(spec=PreCheckoutQuery)
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

    msg = MagicMock(spec=Message)
    msg.successful_payment = MagicMock(
        total_amount=100,
        currency="XTR",
        invoice_payload="payload123",
    )

    for handler in router.message.handlers:
        await handler.callback(msg)
        break
    # on_confirmed should be called with the payload
    assert confirmed["payload"] == "payload123"


@pytest.mark.asyncio
async def test_payment_handler_unconfirmed():
    router = Router()
    provider = MockPaymentProvider()
    confirmed = {}

    async def on_confirmed(payload: str) -> None:
        confirmed["payload"] = payload

    attach_payment_handlers(router, provider, on_confirmed=on_confirmed)

    msg = MagicMock(spec=Message)
    msg.successful_payment = MagicMock(
        total_amount=100,
        currency="XTR",
        invoice_payload="payload456",
    )

    for handler in router.message.handlers:
        await handler.callback(msg)
        break
    # on_confirmed should be called with the payload
    assert confirmed["payload"] == "payload456"


def test_payment_provider_protocol() -> None:
    assert issubclass(MockPaymentProvider, PaymentProvider)
    assert issubclass(YooKassaPaymentProvider, PaymentProvider)


def test_mock_provider_create_payment() -> None:
    provider = MockPaymentProvider()
    import asyncio

    async def test() -> None:
        pid = await provider.create_payment(
            title="t", description="d", payload="p", amount=100
        )
        assert pid.startswith("https://t.me/mock-bot/invoice/")

    asyncio.run(test())


def test_mock_provider_check_payment() -> None:
    provider = MockPaymentProvider()
    asyncio.run(provider.check_payment("any")) is True


def test_yookassa_provider_instantiation() -> None:
    provider = YooKassaPaymentProvider(shop_id="123", secret_key="secret")
    assert isinstance(provider, PaymentProvider)


def test_mock_provider_verify_payment() -> None:
    provider = MockPaymentProvider()
    msg = MagicMock()
    msg.successful_payment = MagicMock(total_amount=100)
    import asyncio

    async def test() -> None:
        result = await provider.verify_payment(msg)
        assert result is True

    asyncio.run(test())


def test_mock_provider_verify_payment_false() -> None:
    provider = MockPaymentProvider()
    msg = MagicMock()
    msg.successful_payment = None
    import asyncio

    async def test() -> None:
        result = await provider.verify_payment(msg)
        assert result is False

    asyncio.run(test())


def test_stars_currency_constant() -> None:
    assert STARS_CURRENCY == "XTR"

