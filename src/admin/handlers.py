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

    return admin
