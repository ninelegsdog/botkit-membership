"""Tests for membership + admin handlers and core auth (coverage boost)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiogram import Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import Chat, Message, User

from src.admin.handlers import create_router as create_admin_router
from src.core.auth import ADMIN_GATE_ATTR, AdminGate, mark_admin_router, require_admin
from src.core.navigation import NavRegistry
from src.membership.handlers import create_router as create_membership_router


def _user(uid: int) -> User:
    return User(id=uid, is_bot=False, first_name="Test User", username="test_user")


def _chat(cid: int = 123) -> Chat:
    return Chat(id=cid, type="private")


def _make_message(
    uid: int = 456, cid: int = 123, mid: int = 789, text: str | None = None
) -> Any:
    msg = MagicMock()
    msg.bot = MagicMock()
    msg.chat = _chat(cid)
    msg.from_user = _user(uid)
    msg.message_id = mid
    msg.text = text
    msg.answer = AsyncMock()
    msg.edit_text = AsyncMock()
    return msg


def _make_callback(data: str, uid: int = 456, cid: int = 123) -> Any:
    cq = MagicMock()
    cq.bot = MagicMock()
    cq.data = data
    cq.from_user = _user(uid)
    cq.message = _make_message(uid=uid, cid=cid)
    cq.answer = AsyncMock()
    return cq


def _find(router: Any, attr: str, name: str) -> Any:
    for h in getattr(router, attr).handlers:
        cb = h.callback
        if hasattr(cb, "__name__") and cb.__name__ == name:
            return cb
    raise AssertionError(f"handler {name!r} not found")


def _unwrap(wrapper: Any) -> Any:
    for cell in wrapper.__closure__ or []:
        if callable(cell.cell_contents):
            return cell.cell_contents
    raise AssertionError("unable to unwrap admin handler")


def _admin_callbacks(router: Any) -> dict[str, Any]:
    return {_unwrap(h.callback).__name__: _unwrap(h.callback) for h in router.callback_query.handlers}


@pytest.fixture
def gate() -> AdminGate:
    return AdminGate(password="secret", admin_ids=[999])


@pytest.fixture
def nav() -> NavRegistry:
    return NavRegistry()


@pytest.fixture
def db() -> MagicMock:
    return MagicMock()


@pytest.fixture
def fsm() -> FSMContext:
    return FSMContext(
        storage=MemoryStorage(),
        key=StorageKey(bot_id=0, chat_id=999, user_id=999),
    )


class TestMembershipPublicHandlers:

    async def test_start_registers_subscriber(self, gate, nav, db):
        router = create_membership_router(gate=gate, nav=nav, db=db, trial_days=3)
        handler = _find(router, "message", "start")
        msg = _make_message(uid=456)
        with patch("src.membership.service.ensure_subscriber", new=AsyncMock()) as mock_ensure:
            await handler(msg)
            mock_ensure.assert_awaited_once()
        msg.answer.assert_awaited_once()
        _, kwargs = msg.answer.await_args
        assert "reply_markup" in kwargs

    async def test_list_plans_empty(self, gate, nav, db):
        router = create_membership_router(gate=gate, nav=nav, db=db)
        handler = _find(router, "callback_query", "list_plans")
        cb = _make_callback("mem:plans")
        with patch("src.membership.service.get_active_plans", new=AsyncMock(return_value=[])):
            await handler(cb)
        cb.answer.assert_awaited_with("Тарифов пока нет.", show_alert=True)

    async def test_list_plans_with_plans(self, gate, nav, db):
        router = create_membership_router(gate=gate, nav=nav, db=db)
        handler = _find(router, "callback_query", "list_plans")
        cb = _make_callback("mem:plans")
        plans = [
            {"id": 1, "name": "Basic", "price": 100, "period_days": 30},
            {"id": 2, "name": "Premium", "price": 200, "period_days": 30},
        ]
        with patch("src.membership.service.get_active_plans", new=AsyncMock(return_value=plans)):
            await handler(cb)
        cb.message.edit_text.assert_awaited_once()
        args, kwargs = cb.message.edit_text.await_args
        assert "Выберите тариф:" in args[0]
        assert "reply_markup" in kwargs

    async def test_select_plan_not_found(self, gate, nav, db):
        router = create_membership_router(gate=gate, nav=nav, db=db)
        handler = _find(router, "callback_query", "select_plan")
        cb = _make_callback("mem:plan:999")
        with patch("src.membership.service.get_plan", new=AsyncMock(return_value=None)):
            await handler(cb)
        cb.answer.assert_awaited_with("Тариф не найден.", show_alert=True)

    async def test_select_plan_found(self, gate, nav, db):
        router = create_membership_router(gate=gate, nav=nav, db=db)
        handler = _find(router, "callback_query", "select_plan")
        cb = _make_callback("mem:plan:1")
        plan = {"id": 1, "name": "Basic", "price": 100, "period_days": 30}
        with patch("src.membership.service.get_plan", new=AsyncMock(return_value=plan)):
            await handler(cb)
        cb.message.edit_text.assert_awaited_once()
        args, kwargs = cb.message.edit_text.await_args
        assert "Basic" in args[0]
        assert "100" in args[0]
        assert "Оформить подписку?" in args[0]
        assert "reply_markup" in kwargs

    async def test_subscribe_not_found(self, gate, nav, db):
        router = create_membership_router(gate=gate, nav=nav, db=db)
        handler = _find(router, "callback_query", "subscribe")
        cb = _make_callback("mem:subscribe:999")
        with patch("src.membership.service.get_plan", new=AsyncMock(return_value=None)):
            await handler(cb)
        cb.answer.assert_awaited_with("Тариф не найден.", show_alert=True)

    async def test_subscribe_success(self, gate, nav, db):
        router = create_membership_router(gate=gate, nav=nav, db=db)
        handler = _find(router, "callback_query", "subscribe")
        cb = _make_callback("mem:subscribe:1")
        plan = {"id": 1, "name": "Basic", "price": 100, "period_days": 30}
        with patch("src.membership.service.get_plan", new=AsyncMock(return_value=plan)), \
             patch("src.membership.service.activate_subscription", new=AsyncMock(return_value=1)):
            await handler(cb)
        cb.answer.assert_awaited_with("Подписка оформлена!", show_alert=True)

    async def test_subscribe_failure(self, gate, nav, db):
        router = create_membership_router(gate=gate, nav=nav, db=db)
        handler = _find(router, "callback_query", "subscribe")
        cb = _make_callback("mem:subscribe:1")
        plan = {"id": 1, "name": "Basic", "price": 100, "period_days": 30}
        with patch("src.membership.service.get_plan", new=AsyncMock(return_value=plan)), \
             patch("src.membership.service.activate_subscription", new=AsyncMock(return_value=0)):
            await handler(cb)
        cb.answer.assert_awaited_with("Ошибка оформления.", show_alert=True)

    async def test_content_not_subscriber(self, gate, nav, db):
        router = create_membership_router(gate=gate, nav=nav, db=db)
        handler = _find(router, "callback_query", "list_content")
        cb = _make_callback("mem:content")
        with patch("src.membership.service.is_subscriber", new=AsyncMock(return_value=False)):
            await handler(cb)
        cb.message.edit_text.assert_awaited_once()
        args, kwargs = cb.message.edit_text.await_args
        assert "Это для участников клуба" in args[0]
        assert "reply_markup" in kwargs

    async def test_content_subscriber_empty(self, gate, nav, db):
        router = create_membership_router(gate=gate, nav=nav, db=db)
        handler = _find(router, "callback_query", "list_content")
        cb = _make_callback("mem:content")
        with patch("src.membership.service.is_subscriber", new=AsyncMock(return_value=True)), \
             patch("src.membership.service.get_content_sections", new=AsyncMock(return_value=[])):
            await handler(cb)
        cb.message.edit_text.assert_awaited_with("Контента пока нет.")

    async def test_content_subscriber_sections(self, gate, nav, db):
        router = create_membership_router(gate=gate, nav=nav, db=db)
        handler = _find(router, "callback_query", "list_content")
        cb = _make_callback("mem:content")
        sections = [{"id": 1, "title": "Финансы", "position": 1}]
        with patch("src.membership.service.is_subscriber", new=AsyncMock(return_value=True)), \
             patch("src.membership.service.get_content_sections", new=AsyncMock(return_value=sections)):
            await handler(cb)
        cb.message.edit_text.assert_awaited_once()
        args, kwargs = cb.message.edit_text.await_args
        assert "Разделы:" in args[0]
        assert "reply_markup" in kwargs

    async def test_view_section_empty(self, gate, nav, db):
        router = create_membership_router(gate=gate, nav=nav, db=db)
        handler = _find(router, "callback_query", "view_section")
        cb = _make_callback("mem:section:1")
        with patch("src.membership.service.get_content_items", new=AsyncMock(return_value=[])):
            await handler(cb)
        cb.message.edit_text.assert_awaited_with("В разделе пока нет контента.")

    async def test_view_section_items(self, gate, nav, db):
        router = create_membership_router(gate=gate, nav=nav, db=db)
        handler = _find(router, "callback_query", "view_section")
        cb = _make_callback("mem:section:1")
        items = [{"type": "text", "payload": "Привет"}, {"type": "video", "payload": "https://x"}]
        with patch("src.membership.service.get_content_items", new=AsyncMock(return_value=items)):
            await handler(cb)
        cb.message.edit_text.assert_awaited_once()
        args, _ = cb.message.edit_text.await_args
        assert "text: Привет" in args[0]
        assert "video: https://x" in args[0]

    async def test_my_subscription_none(self, gate, nav, db):
        router = create_membership_router(gate=gate, nav=nav, db=db)
        handler = _find(router, "callback_query", "my_subscription")
        cb = _make_callback("mem:my")
        with patch("src.membership.service.get_subscription", new=AsyncMock(return_value=None)):
            await handler(cb)
        cb.message.edit_text.assert_awaited_once()
        args, kwargs = cb.message.edit_text.await_args
        assert "нет активной подписки" in args[0]
        assert "reply_markup" in kwargs

    async def test_my_subscription_auto_renew(self, gate, nav, db):
        router = create_membership_router(gate=gate, nav=nav, db=db)
        handler = _find(router, "callback_query", "my_subscription")
        cb = _make_callback("mem:my")
        sub = {"plan_name": "Premium", "end_at": "2026-12-31 23:59:59", "auto_renew": True}
        with patch("src.membership.service.get_subscription", new=AsyncMock(return_value=sub)):
            await handler(cb)
        cb.message.edit_text.assert_awaited_once()
        args, kwargs = cb.message.edit_text.await_args
        assert "Premium" in args[0]
        assert "2026-12-31" in args[0]
        assert "Автопродление: да" in args[0]
        assert kwargs.get("reply_markup") is not None

    async def test_my_subscription_no_renew(self, gate, nav, db):
        router = create_membership_router(gate=gate, nav=nav, db=db)
        handler = _find(router, "callback_query", "my_subscription")
        cb = _make_callback("mem:my")
        sub = {"plan_name": "Basic", "end_at": "2026-12-31 23:59:59", "auto_renew": False}
        with patch("src.membership.service.get_subscription", new=AsyncMock(return_value=sub)):
            await handler(cb)
        cb.message.edit_text.assert_awaited_once()
        _, kwargs = cb.message.edit_text.await_args
        assert kwargs.get("reply_markup") is None

    async def test_cancel_success(self, gate, nav, db):
        router = create_membership_router(gate=gate, nav=nav, db=db)
        handler = _find(router, "callback_query", "cancel_sub")
        cb = _make_callback("mem:cancel")
        with patch("src.membership.service.cancel_subscription", new=AsyncMock(return_value=True)):
            await handler(cb)
        cb.answer.assert_awaited_with("Автопродление отменено.", show_alert=True)

    async def test_cancel_failure(self, gate, nav, db):
        router = create_membership_router(gate=gate, nav=nav, db=db)
        handler = _find(router, "callback_query", "cancel_sub")
        cb = _make_callback("mem:cancel")
        with patch("src.membership.service.cancel_subscription", new=AsyncMock(return_value=False)):
            await handler(cb)
        cb.answer.assert_awaited_with("Не удалось отменить.", show_alert=True)

    async def test_list_polls_empty(self, gate, nav, db):
        router = create_membership_router(gate=gate, nav=nav, db=db)
        handler = _find(router, "callback_query", "list_polls")
        cb = _make_callback("mem:polls")
        with patch("src.membership.service.get_active_polls", new=AsyncMock(return_value=[])):
            await handler(cb)
        cb.message.edit_text.assert_awaited_with("Опросов пока нет.")
        cb.answer.assert_awaited_once()

    async def test_list_polls_with_polls(self, gate, nav, db):
        router = create_membership_router(gate=gate, nav=nav, db=db)
        handler = _find(router, "callback_query", "list_polls")
        cb = _make_callback("mem:polls")
        polls = [{"id": 1, "question": "Как дела?"}]
        with patch("src.membership.service.get_active_polls", new=AsyncMock(return_value=polls)):
            await handler(cb)
        cb.message.edit_text.assert_awaited_once()
        args, kwargs = cb.message.edit_text.await_args
        assert "Активные опросы:" in args[0]
        assert "reply_markup" in kwargs

    async def test_view_poll_not_found(self, gate, nav, db):
        router = create_membership_router(gate=gate, nav=nav, db=db)
        handler = _find(router, "callback_query", "view_poll")
        cb = _make_callback("mem:poll:5")
        with patch("src.membership.service.get_active_polls", new=AsyncMock(return_value=[])):
            await handler(cb)
        cb.answer.assert_awaited_with("Опрос не найден.", show_alert=True)

    async def test_view_poll_found(self, gate, nav, db):
        router = create_membership_router(gate=gate, nav=nav, db=db)
        handler = _find(router, "callback_query", "view_poll")
        cb = _make_callback("mem:poll:1")
        polls = [{"id": 1, "question": "Любимый цвет?", "options": '["A", "B"]'}]
        with patch("src.membership.service.get_active_polls", new=AsyncMock(return_value=polls)):
            await handler(cb)
        cb.message.edit_text.assert_awaited_once()
        args, kwargs = cb.message.edit_text.await_args
        assert "Любимый цвет?" in args[0]
        assert "reply_markup" in kwargs

    async def test_vote_success(self, gate, nav, db):
        router = create_membership_router(gate=gate, nav=nav, db=db)
        handler = _find(router, "callback_query", "vote")
        cb = _make_callback("mem:vote:1:0")
        results = [{"option": 0, "votes": 5}, {"option": 1, "votes": 3}]
        with patch("src.membership.service.vote_poll", new=AsyncMock(return_value=True)), \
             patch("src.membership.service.get_poll_results", new=AsyncMock(return_value=results)):
            await handler(cb)
        cb.message.edit_text.assert_awaited_once()
        args, _ = cb.message.edit_text.await_args
        assert "Результаты:" in args[0]
        assert "Вариант 0: 5" in args[0]
        cb.answer.assert_awaited_with("Голос учтён!")

    async def test_vote_already_voted(self, gate, nav, db):
        router = create_membership_router(gate=gate, nav=nav, db=db)
        handler = _find(router, "callback_query", "vote")
        cb = _make_callback("mem:vote:1:0")
        with patch("src.membership.service.vote_poll", new=AsyncMock(return_value=False)):
            await handler(cb)
        cb.answer.assert_awaited_with("Вы уже голосовали.", show_alert=True)


class TestAdminHandlers:

    async def test_admin_entry_is_admin(self, nav, db):
        gate = AdminGate(password="secret", admin_ids=[456])
        router = create_admin_router(gate=gate, nav=nav, db=db)
        handler = _find(router, "message", "admin_entry")
        msg = _make_message(uid=456)
        await handler(msg, MagicMock())
        msg.answer.assert_awaited_once()
        _, kwargs = msg.answer.await_args
        assert "reply_markup" in kwargs

    async def test_admin_entry_not_admin(self, gate, nav, db, fsm):
        router = create_admin_router(gate=gate, nav=nav, db=db)
        handler = _find(router, "message", "admin_entry")
        msg = _make_message(uid=456)
        await handler(msg, fsm)
        assert await fsm.get_state() == "AdminStates:waiting_password"
        msg.answer.assert_awaited_with("Введите пароль администратора:")

    async def test_check_password_correct(self, nav, db, fsm):
        gate = AdminGate(password="secret", admin_ids=[999])
        router = create_admin_router(gate=gate, nav=nav, db=db)
        handler = _find(router, "message", "check_password")
        msg = _make_message(uid=456, text="secret")
        await handler(msg, fsm)
        assert await fsm.get_state() is None
        msg.answer.assert_awaited_once()
        _, kwargs = msg.answer.await_args
        assert "reply_markup" in kwargs

    async def test_check_password_incorrect(self, gate, nav, db, fsm):
        router = create_admin_router(gate=gate, nav=nav, db=db)
        handler = _find(router, "message", "check_password")
        msg = _make_message(uid=456, text="wrong")
        await handler(msg, fsm)
        msg.answer.assert_awaited_with("❌ Неверный пароль.")

    async def test_admin_list_plans(self, nav, db):
        gate = AdminGate(password="secret", admin_ids=[456])
        router = create_admin_router(gate=gate, nav=nav, db=db)
        handlers = _admin_callbacks(router)
        cb = _make_callback("adm:plans", uid=456)
        plans = [{"id": 1, "name": "Basic", "price": 100, "period_days": 30}]
        with patch("src.membership.service.get_active_plans", new=AsyncMock(return_value=plans)):
            await handlers["list_plans"](cb)
        cb.message.edit_text.assert_awaited_once()
        args, _ = cb.message.edit_text.await_args
        assert "Тарифы:" in args[0]
        assert "Basic" in args[0]

    async def test_admin_list_plans_empty(self, nav, db):
        gate = AdminGate(password="secret", admin_ids=[456])
        router = create_admin_router(gate=gate, nav=nav, db=db)
        handlers = _admin_callbacks(router)
        cb = _make_callback("adm:plans", uid=456)
        with patch("src.membership.service.get_active_plans", new=AsyncMock(return_value=[])):
            await handlers["list_plans"](cb)
        cb.message.edit_text.assert_awaited_with("Тарифов пока нет.")

    async def test_admin_list_members(self, nav, db):
        gate = AdminGate(password="secret", admin_ids=[456])
        router = create_admin_router(gate=gate, nav=nav, db=db)
        handlers = _admin_callbacks(router)
        cb = _make_callback("adm:members", uid=456)
        members = [
            {"name": "Ann", "plan_name": "Premium", "end_at": "2026-12-31 23:59:59"}
        ]
        with patch("src.membership.service.get_active_subscribers", new=AsyncMock(return_value=members)):
            await handlers["list_members"](cb)
        cb.message.edit_text.assert_awaited_once()
        args, _ = cb.message.edit_text.await_args
        assert "Участники:" in args[0]
        assert "Ann" in args[0]

    async def test_admin_list_members_empty(self, nav, db):
        gate = AdminGate(password="secret", admin_ids=[456])
        router = create_admin_router(gate=gate, nav=nav, db=db)
        handlers = _admin_callbacks(router)
        cb = _make_callback("adm:members", uid=456)
        with patch("src.membership.service.get_active_subscribers", new=AsyncMock(return_value=[])):
            await handlers["list_members"](cb)
        cb.message.edit_text.assert_awaited_with("Нет активных участников.")


class TestRequireAdmin:

    @staticmethod
    def _real_message(uid: int) -> Message:
        return Message(
            message_id=1,
            date=datetime.now(UTC),
            chat=Chat(id=1, type="private"),
            from_user=_user(uid),
            text="x",
        )

    def test_require_admin_marks_func(self):
        gate = AdminGate(password="x")

        async def handler_base(a, b):
            return "ok"

        require_admin(gate)(handler_base)
        assert getattr(handler_base, ADMIN_GATE_ATTR, False) is True

    async def test_require_admin_grants_admin(self):
        gate = AdminGate(password="x", admin_ids=[456])

        @require_admin(gate)
        async def handler(msg):
            return "ok"

        result = await handler(self._real_message(456))
        assert result == "ok"

    async def test_require_admin_denies_message(self):
        gate = AdminGate(password="x", admin_ids=[999])

        @require_admin(gate)
        async def handler(msg):
            return "ok"

        with patch.object(Message, "answer", new=AsyncMock()):
            result = await handler(self._real_message(456))
            assert result is None
            Message.answer.assert_awaited_with("⛔ Доступ запрещён.")

    async def test_require_admin_ignores_non_message(self):
        gate = AdminGate(password="x")

        @require_admin(gate)
        async def handler(event):
            return "ok"

        meta = MagicMock()
        meta.from_user = _user(456)
        result = await handler(meta)
        assert result is None


class TestAdminGate:

    def test_deauthorize(self):
        gate = AdminGate(password="secret")
        assert gate.authorize(456, "secret") is True
        assert gate.is_admin(456) is True
        gate.deauthorize(456)
        assert gate.is_admin(456) is False

    def test_throttle_after_max_attempts(self):
        gate = AdminGate(password="secret")
        for _ in range(4):
            assert gate.authorize(456, "bad") is False
        assert gate.is_throttled(456) is False
        assert gate.authorize(456, "bad") is False
        assert gate.is_throttled(456) is True

    def test_authorize_wrong_then_correct_resets(self):
        gate = AdminGate(password="secret")
        assert gate.authorize(456, "bad") is False
        gate.authorize(456, "wrong")
        gate.authorize(456, "wrong")
        assert gate.authorize(456, "secret") is True
        assert gate.is_admin(456) is True
        assert gate.is_throttled(456) is False

    def test_authorize_correct_clears_attempts(self):
        gate = AdminGate(password="secret")
        for _ in range(6):
            assert gate.authorize(456, "bad") is False
        assert gate.is_throttled(456) is True
        assert gate.authorize(456, "secret") is True
        assert gate.is_throttled(456) is False

    def test_mark_admin_router(self):
        router = Router(name="test")
        mark_admin_router(router)
        assert getattr(router, "_requires_admin", False) is True

    def test_password_bindings(self):
        gate = AdminGate(password="secret")
        assert gate.is_admin(1) is False
        gate.deauthorize(1)
        assert gate.is_admin(1) is False