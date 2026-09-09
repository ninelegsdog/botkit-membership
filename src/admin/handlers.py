from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from src.core.auth import AdminGate, mark_admin_router, require_admin
from src.core.database import Database
from src.core.fsm import text_not_command


class AdminStates(StatesGroup):
    waiting_password = State()
    waiting_broadcast_text = State()


ADMIN_MENU_TEXT = "🔐 Админ-панель клуба"


def create_router(*, gate: AdminGate, nav: object, db: Database) -> Router:
    admin = mark_admin_router(Router(name="admin"))

    @admin.message(Command("admin"))
    async def admin_entry(message: Message, state: FSMContext) -> None:
        uid = message.from_user.id  # type: ignore
        if gate.is_admin(uid):
            await _show_admin_menu(message)
            return
        await state.set_state(AdminStates.waiting_password)
        await message.answer("Введите пароль администратора:")

    @admin.message(AdminStates.waiting_password, text_not_command)
    async def check_password(message: Message, state: FSMContext) -> None:
        uid = message.from_user.id  # type: ignore
        if gate.authorize(uid, message.text or ""):
            await state.clear()
            await _show_admin_menu(message)
        else:
            await message.answer("❌ Неверный пароль.")

    async def _show_admin_menu(message: Message) -> None:
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="💳 Тарифы", callback_data="adm:plans")],
                [InlineKeyboardButton(text="📚 Контент", callback_data="adm:content")],
                [InlineKeyboardButton(text="👥 Участники", callback_data="adm:members")],
                [InlineKeyboardButton(text="📊 Опросы", callback_data="adm:polls")],
                [InlineKeyboardButton(text="📣 Рассылка", callback_data="adm:broadcast")],
            ]
        )
        await message.answer(ADMIN_MENU_TEXT, reply_markup=kb)

    @admin.callback_query(F.data == "adm:plans")
    @require_admin(gate)
    async def list_plans(callback: CallbackQuery) -> None:
        from src.membership.service import get_active_plans

        plans = await get_active_plans(db)
        if plans:
            text = "Тарифы:\n" + "\n".join(
                f"• {p['name']} — {p['price']}₽ / {p['period_days']} дн." for p in plans
            )
        else:
            text = "Тарифов пока нет."
        await callback.message.edit_text(text)  # type: ignore
        await callback.answer()

    @admin.callback_query(F.data == "adm:members")
    @require_admin(gate)
    async def list_members(callback: CallbackQuery) -> None:
        from src.membership.service import get_active_subscribers

        members = await get_active_subscribers(db)
        if members:
            text = "Участники:\n" + "\n".join(
                f"• {m['name']} — {m['plan_name']} до {str(m['end_at'])[:10]}" for m in members
            )
        else:
            text = "Нет активных участников."
        await callback.message.edit_text(text)  # type: ignore
        await callback.answer()

    @admin.callback_query(F.data == "adm:content")
    @require_admin(gate)
    async def admin_content(callback: CallbackQuery) -> None:
        from src.membership.service import get_content_items, get_content_sections

        sections = await get_content_sections(db)
        if not sections:
            text = "Контент-разделов пока нет."
        else:
            lines: list[str] = []
            for s in sections:
                items = await get_content_items(db, int(s['id']))
                lines.append(f"• {s['title']} — {len(items)} шт.")
            text = "📚 Разделы контента:\n" + "\n".join(lines)
        await callback.message.edit_text(text)
        await callback.answer()

    @admin.callback_query(F.data == "adm:polls")
    @require_admin(gate)
    async def admin_polls(callback: CallbackQuery) -> None:
        from src.membership.service import get_active_polls, get_poll_results

        polls = await get_active_polls(db)
        if not polls:
            text = "Активных опросов нет."
        else:
            lines: list[str] = []
            for p in polls:
                results = await get_poll_results(db, int(p['id']))
                summary = ", ".join(f"{r['option']}: {r['votes']}" for r in results)
                lines.append(f"• {p['question']} ({summary or 'нет голосов'})")
            text = "📊 Опросы:\n" + "\n".join(lines)
        await callback.message.edit_text(text)
        await callback.answer()

    @admin.callback_query(F.data == "adm:broadcast")
    @require_admin(gate)
    async def broadcast_start(callback: CallbackQuery, state: FSMContext) -> None:
        await state.set_state(AdminStates.waiting_broadcast_text)
        await callback.message.edit_text("📣 Введите текст рассылки (одно сообщение):")
        await callback.answer()

    @admin.message(AdminStates.waiting_broadcast_text, text_not_command)
    @require_admin(gate)
    async def broadcast_send(message: Message, state: FSMContext) -> None:
        from src.membership.service import get_active_subscribers

        text = (message.text or "").strip()
        if not text:
            await message.answer("Пустое сообщение — отменено.")
            await state.clear()
            return
        subscribers = await get_active_subscribers(db)
        ok = 0
        failed = 0
        for s in subscribers:
            try:
                await message.bot.send_message(int(s['user_id']), f"📣 {text}")
                ok += 1
            except Exception:
                failed += 1
        await message.answer(f"📣 Рассылка отправлена: {ok} доставлено, {failed} ошибок.")
        await state.clear()

    return admin
