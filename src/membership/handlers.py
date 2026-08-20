import json

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from src.core.auth import AdminGate, mark_admin_router
from src.core.database import Database
from src.core.navigation import NavRegistry, compose_message

from . import service
from .nav import NAV_SECTION


class ContentStates(StatesGroup):
    waiting_text = State()


def create_router(
    *, gate: AdminGate, nav: NavRegistry, db: Database, trial_days: int = 3
) -> Router:
    nav.register(NAV_SECTION)
    public = Router(name="membership")
    admin = mark_admin_router(Router(name="membership_admin"))

    @public.message(Command("start"))
    async def start(message: Message) -> None:
        from src.membership.service import ensure_subscriber

        await ensure_subscriber(
            db,
            message.from_user.id,  # type: ignore
            message.from_user.first_name or "",  # type: ignore
            message.from_user.username,  # type: ignore
        )
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="⭐ Тарифы", callback_data="mem:plans")],
                [InlineKeyboardButton(text="📚 Контент", callback_data="mem:content")],
                [InlineKeyboardButton(text="📊 Опросы", callback_data="mem:polls")],
                [InlineKeyboardButton(text="👤 Моя подписка", callback_data="mem:my")],
            ]
        )
        await message.answer(
            compose_message(["Клуб"], "Добро пожаловать! Выберите действие:"),
            reply_markup=kb,
        )

    @public.callback_query(F.data == "mem:plans")
    async def list_plans(callback: CallbackQuery) -> None:
        plans = await service.get_active_plans(db)
        if not plans:
            await callback.answer("Тарифов пока нет.", show_alert=True)
            return
        buttons = [
            [
                InlineKeyboardButton(
                    text=f"{p['name']} — {p['price']}₽ / {p['period_days']} дн.",
                    callback_data=f"mem:plan:{p['id']}",
                )
            ]
            for p in plans
        ]
        kb = InlineKeyboardMarkup(inline_keyboard=buttons)
        await callback.message.edit_text("Выберите тариф:", reply_markup=kb)  # type: ignore
        await callback.answer()

    @public.callback_query(F.data.startswith("mem:plan:"))
    async def select_plan(callback: CallbackQuery) -> None:
        if not callback.data:
            return
        plan_id = int(callback.data.split(":")[2])
        plan = await service.get_plan(db, plan_id)
        if not plan:
            await callback.answer("Тариф не найден.", show_alert=True)
            return
        text = (
            f"📦 {plan['name']}\n"
            f"💰 {plan['price']}₽ / {plan['period_days']} дней\n\n"
            f"Оформить подписку?"
        )
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="✅ Оформить", callback_data=f"mem:subscribe:{plan_id}")],
                [InlineKeyboardButton(text="🔙 Назад", callback_data="mem:plans")],
            ]
        )
        await callback.message.edit_text(text, reply_markup=kb)  # type: ignore
        await callback.answer()

    @public.callback_query(F.data.startswith("mem:subscribe:"))
    async def subscribe(callback: CallbackQuery) -> None:
        if not callback.data:
            return
        plan_id = int(callback.data.split(":")[2])
        plan = await service.get_plan(db, plan_id)
        if not plan:
            await callback.answer("Тариф не найден.", show_alert=True)
            return

        sub_id = await service.activate_subscription(
            db, callback.from_user.id, plan_id, int(str(plan["period_days"]))
        )
        if sub_id:
            await callback.answer("Подписка оформлена!", show_alert=True)
        else:
            await callback.answer("Ошибка оформления.", show_alert=True)

    @public.callback_query(F.data == "mem:content")
    async def list_content(callback: CallbackQuery) -> None:
        if not await service.is_subscriber(db, callback.from_user.id):
            await callback.message.edit_text(  # type: ignore
                "🔒 Это для участников клуба.\nОформите подписку в разделе ⭐ Тарифы.",
                reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=[
                        [InlineKeyboardButton(text="⭐ Тарифы", callback_data="mem:plans")]
                    ]
                ),
            )
            await callback.answer()
            return

        sections = await service.get_content_sections(db)
        if not sections:
            await callback.message.edit_text("Контента пока нет.")  # type: ignore
            await callback.answer()
            return
        buttons = [
            [
                InlineKeyboardButton(
                    text=str(s["title"]),
                    callback_data=f"mem:section:{s['id']}",
                )
            ]
            for s in sections
        ]
        kb = InlineKeyboardMarkup(inline_keyboard=buttons)
        await callback.message.edit_text("📚 Разделы:", reply_markup=kb)  # type: ignore
        await callback.answer()

    @public.callback_query(F.data.startswith("mem:section:"))
    async def view_section(callback: CallbackQuery) -> None:
        if not callback.data:
            return
        section_id = int(callback.data.split(":")[2])
        items = await service.get_content_items(db, section_id)
        if not items:
            await callback.message.edit_text("В разделе пока нет контента.")  # type: ignore
            await callback.answer()
            return
        text = "\n\n".join(f"📄 {item['type']}: {item['payload']}" for item in items)
        await callback.message.edit_text(text)  # type: ignore
        await callback.answer()

    @public.callback_query(F.data == "mem:my")
    async def my_subscription(callback: CallbackQuery) -> None:
        sub = await service.get_subscription(db, callback.from_user.id)
        if not sub:
            kb_empty = InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="⭐ Оформить подписку", callback_data="mem:plans")]
                ]
            )
            await callback.message.edit_text("У вас нет активной подписки.", reply_markup=kb_empty)  # type: ignore
            await callback.answer()
            return

        text = (
            f"👤 Подписка: {sub['plan_name']}\n"
            f"📅 До: {str(sub['end_at'])[:10]}\n"
            f"🔄 Автопродление: {'да' if sub['auto_renew'] else 'нет'}"
        )
        buttons: list[list[InlineKeyboardButton]] = []
        if sub["auto_renew"]:
            buttons.append(
                [InlineKeyboardButton(text="❌ Отменить автопродление", callback_data="mem:cancel")]
            )
        kb: InlineKeyboardMarkup | None = InlineKeyboardMarkup(inline_keyboard=buttons) if buttons else None
        await callback.message.edit_text(text, reply_markup=kb)  # type: ignore
        await callback.answer()

    @public.callback_query(F.data == "mem:cancel")
    async def cancel_sub(callback: CallbackQuery) -> None:
        ok = await service.cancel_subscription(db, callback.from_user.id)
        if ok:
            await callback.answer("Автопродление отменено.", show_alert=True)
        else:
            await callback.answer("Не удалось отменить.", show_alert=True)

    @public.callback_query(F.data == "mem:polls")
    async def list_polls(callback: CallbackQuery) -> None:
        polls = await service.get_active_polls(db)
        if not polls:
            await callback.message.edit_text("Опросов пока нет.")  # type: ignore
            await callback.answer()
            return
        buttons = [
            [
                InlineKeyboardButton(
                    text=f"📊 {str(p['question'])[:30]}",
                    callback_data=f"mem:poll:{p['id']}",
                )
            ]
            for p in polls
        ]
        kb = InlineKeyboardMarkup(inline_keyboard=buttons)
        await callback.message.edit_text("Активные опросы:", reply_markup=kb)  # type: ignore
        await callback.answer()

    @public.callback_query(F.data.startswith("mem:poll:"))
    async def view_poll(callback: CallbackQuery) -> None:
        if not callback.data:
            return
        poll_id = int(callback.data.split(":")[2])
        polls = await service.get_active_polls(db)
        poll = next((p for p in polls if p["id"] == poll_id), None)
        if not poll:
            await callback.answer("Опрос не найден.", show_alert=True)
            return
        options = json.loads(str(poll["options"]))
        buttons = [
            [InlineKeyboardButton(text=str(opt), callback_data=f"mem:vote:{poll_id}:{i}")]
            for i, opt in enumerate(options)
        ]
        kb = InlineKeyboardMarkup(inline_keyboard=buttons)
        await callback.message.edit_text(f"📊 {str(poll['question'])}", reply_markup=kb)  # type: ignore
        await callback.answer()

    @public.callback_query(F.data.startswith("mem:vote:"))
    async def vote(callback: CallbackQuery) -> None:
        if not callback.data:
            return
        parts = callback.data.split(":")
        poll_id = int(parts[2])
        option = int(parts[3])
        ok = await service.vote_poll(db, poll_id, callback.from_user.id, option)
        if ok:
            results = await service.get_poll_results(db, poll_id)
            text = "Результаты:\n" + "\n".join(f"  Вариант {r['option']}: {r['votes']}" for r in results)
            await callback.message.edit_text(text)  # type: ignore
            await callback.answer("Голос учтён!")
        else:
            await callback.answer("Вы уже голосовали.", show_alert=True)

    public.include_router(admin)
    return public
