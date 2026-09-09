"""Tests for new admin panels: content, polls, broadcast (coverage of src/admin/handlers.py)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.admin.handlers import create_router as create_admin_router
from src.core.auth import AdminGate
from src.core.navigation import NavRegistry
from tests.test_membership_handlers import _make_callback, _make_message, _unwrap


@pytest.fixture
def gate() -> AdminGate:
    return AdminGate(password="secret", admin_ids=[999])


@pytest.fixture
def nav() -> NavRegistry:
    return NavRegistry()


@pytest.fixture
def db() -> MagicMock:
    return MagicMock()


def _router(gate, nav, db):
    return create_admin_router(gate=gate, nav=nav, db=db)


def _handlers(router, attr: str) -> dict[str, object]:
    return {
        _unwrap(h.callback).__name__: _unwrap(h.callback)
        for h in getattr(router, attr).handlers
    }


class TestAdminContent:

    async def test_empty(self, gate, nav, db):
        handler = _handlers(_router(gate, nav, db), "callback_query")["admin_content"]
        cb = _make_callback("adm:content", uid=999)
        with patch("src.membership.service.get_content_sections", new=AsyncMock(return_value=[])):
            await handler(cb)
        cb.message.edit_text.assert_awaited_once_with("Контент-разделов пока нет.")
        cb.answer.assert_awaited_once()

    async def test_with_sections(self, gate, nav, db):
        handler = _handlers(_router(gate, nav, db), "callback_query")["admin_content"]
        cb = _make_callback("adm:content", uid=999)
        sections = [{"id": 1, "title": "Медитации", "position": 1}]
        items = [{"id": 1, "type": "text", "payload": "x"}, {"id": 2, "type": "pdf", "payload": "y"}]
        with patch(
            "src.membership.service.get_content_sections", new=AsyncMock(return_value=sections)
        ), patch("src.membership.service.get_content_items", new=AsyncMock(return_value=items)):
            await handler(cb)
        text = cb.message.edit_text.await_args.args[0]
        assert "📚 Разделы контента:" in text
        assert "Медитации — 2 шт." in text


class TestAdminPolls:

    async def test_empty(self, gate, nav, db):
        handler = _handlers(_router(gate, nav, db), "callback_query")["admin_polls"]
        cb = _make_callback("adm:polls", uid=999)
        with patch("src.membership.service.get_active_polls", new=AsyncMock(return_value=[])):
            await handler(cb)
        cb.message.edit_text.assert_awaited_once_with("Активных опросов нет.")
        cb.answer.assert_awaited_once()

    async def test_with_polls(self, gate, nav, db):
        handler = _handlers(_router(gate, nav, db), "callback_query")["admin_polls"]
        cb = _make_callback("adm:polls", uid=999)
        polls = [{"id": 1, "question": "Как дела?", "options": "[1,2]", "anonymous": 1}]
        results = [{"option": 0, "votes": 2}, {"option": 1, "votes": 1}]
        with patch(
            "src.membership.service.get_active_polls", new=AsyncMock(return_value=polls)
        ), patch("src.membership.service.get_poll_results", new=AsyncMock(return_value=results)):
            await handler(cb)
        text = cb.message.edit_text.await_args.args[0]
        assert "📊 Опросы:" in text
        assert "Как дела?" in text
        assert "0: 2" in text


class TestAdminBroadcast:

    async def test_start_sets_state(self, gate, nav, db):
        handler = _handlers(_router(gate, nav, db), "callback_query")["broadcast_start"]
        cb = _make_callback("adm:broadcast", uid=999)

        class _State:
            _s: str | None = None

            async def set_state(self, s):
                self._s = s

        state = _State()
        await handler(cb, state)  # type: ignore[arg-type]
        assert state._s == "AdminStates:waiting_broadcast_text"
        cb.message.edit_text.assert_awaited_once()
        cb.answer.assert_awaited_once()

    async def test_send_empty_cancels(self, gate, nav, db):
        handler = _handlers(_router(gate, nav, db), "message")["broadcast_send"]
        msg = _make_message(uid=999, text="   ")

        class _State:
            async def clear(self):
                self._cleared = True

        state = _State()
        await handler(msg, state)  # type: ignore[arg-type]
        msg.answer.assert_awaited_once_with("Пустое сообщение — отменено.")
        assert state._cleared is True

    async def test_send_delivers(self, gate, nav, db):
        handler = _handlers(_router(gate, nav, db), "message")["broadcast_send"]
        msg = _make_message(uid=999, text="Привет всем!")
        msg.bot.send_message = AsyncMock()
        subscribers = [{"user_id": 111}, {"user_id": 222}]
        state = MagicMock()
        state.clear = AsyncMock()
        with patch(
            "src.membership.service.get_active_subscribers", new=AsyncMock(return_value=subscribers)
        ):
            await handler(msg, state)
        state.clear.assert_awaited_once()
        assert msg.bot.send_message.await_count == 2
        msg.answer.assert_awaited_once_with("📣 Рассылка отправлена: 2 доставлено, 0 ошибок.")

    async def test_send_partial_failure(self, gate, nav, db):
        handler = _handlers(_router(gate, nav, db), "message")["broadcast_send"]
        msg = _make_message(uid=999, text="x")

        async def boom(user_id: int, text: str) -> None:
            if user_id == 111:
                raise RuntimeError("blocked")

        msg.bot.send_message = AsyncMock(side_effect=boom)
        subscribers = [{"user_id": 111}, {"user_id": 222}]
        with patch(
            "src.membership.service.get_active_subscribers", new=AsyncMock(return_value=subscribers)
        ):
            state = MagicMock()
            state.clear = AsyncMock()
            await handler(msg, state)  # type: ignore[arg-type]
        msg.answer.assert_awaited_once_with("📣 Рассылка отправлена: 1 доставлено, 1 ошибок.")