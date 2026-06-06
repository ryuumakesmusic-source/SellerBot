from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from sellerbot.keyboards import admin_panel_keyboard
from sellerbot.repository import StoreRepository
from sellerbot.services.order_service import OrderNotAwaitingReviewError, OrderService, OutOfStockError


class BroadcastStates(StatesGroup):
    waiting_message = State()


def build_admin_router(repository: StoreRepository, order_service: OrderService, admin_ids: set[int]) -> Router:
    router = Router(name="admin")

    def is_admin(user_id: int) -> bool:
        return user_id in admin_ids

    @router.message(Command("admin"))
    async def admin_panel(message: Message):
        if not is_admin(message.from_user.id):
            return
        await message.answer("🛠️ *Admin Panel*", parse_mode="Markdown", reply_markup=admin_panel_keyboard())

    @router.callback_query(F.data == "admin:stats")
    async def stats(callback: CallbackQuery):
        if not is_admin(callback.from_user.id):
            await callback.answer("Unauthorized", show_alert=True)
            return
        stats_data = await repository.get_statistics()
        await callback.message.answer(
            "📊 *Store Statistics*\n"
            f"Total Orders: `{stats_data['total']}`\n"
            f"Pending: `{stats_data['awaiting_review']}`\n"
            f"Approved: `{stats_data['approved']}`\n"
            f"Rejected: `{stats_data['rejected']}`",
            parse_mode="Markdown",
        )
        await callback.answer()

    @router.callback_query(F.data == "admin:broadcast")
    async def prompt_broadcast(callback: CallbackQuery, state: FSMContext):
        if not is_admin(callback.from_user.id):
            await callback.answer("Unauthorized", show_alert=True)
            return
        await state.set_state(BroadcastStates.waiting_message)
        await callback.message.answer("📣 Send the message to broadcast to all customers:")
        await callback.answer()

    @router.message(BroadcastStates.waiting_message)
    async def do_broadcast(message: Message, state: FSMContext):
        if not is_admin(message.from_user.id):
            return
        text = message.text or ""
        if not text.strip():
            await message.answer("⚠️ Broadcast message cannot be empty.")
            return
        user_ids = await repository.get_user_ids()
        sent = 0
        for user_id in user_ids:
            try:
                await message.bot.send_message(user_id, f"📣 {text}")
                sent += 1
            except Exception:
                continue
        await state.clear()
        await message.answer(f"✅ Broadcast sent to {sent} user(s).")

    @router.callback_query(F.data.startswith("admin:approve:"))
    async def approve(callback: CallbackQuery):
        if not is_admin(callback.from_user.id):
            await callback.answer("Unauthorized", show_alert=True)
            return
        order_id = callback.data.split(":", 2)[2]
        try:
            order, stock_item = await order_service.approve_order(order_id)
        except OutOfStockError:
            await callback.message.answer("⚠️ Cannot approve: product is out of stock.")
        except OrderNotAwaitingReviewError:
            await callback.message.answer("ℹ️ Order already processed.")
        except ValueError:
            await callback.message.answer("❌ Order not found.")
        else:
            await callback.message.answer(f"✅ Order `{order.order_id}` approved. Stock delivered.", parse_mode="Markdown")
            await callback.bot.send_message(
                order.user_id,
                "🎉 *Payment Approved!*\n"
                "Your digital product is below:\n\n"
                f"`{stock_item}`",
                parse_mode="Markdown",
            )
        await callback.answer()

    @router.callback_query(F.data.startswith("admin:reject:"))
    async def reject(callback: CallbackQuery):
        if not is_admin(callback.from_user.id):
            await callback.answer("Unauthorized", show_alert=True)
            return
        order_id = callback.data.split(":", 2)[2]
        try:
            order = await order_service.reject_order(order_id)
        except OrderNotAwaitingReviewError:
            await callback.message.answer("ℹ️ Order already processed.")
        except ValueError:
            await callback.message.answer("❌ Order not found.")
        else:
            await callback.message.answer(f"❌ Order `{order.order_id}` rejected.", parse_mode="Markdown")
            await callback.bot.send_message(order.user_id, "❌ Your order was rejected. Contact support if needed.")
        await callback.answer()

    return router
