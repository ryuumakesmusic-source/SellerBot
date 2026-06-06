from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from sellerbot.keyboards import admin_order_keyboard, main_menu_keyboard, products_keyboard
from sellerbot.repository import StoreRepository
from sellerbot.services.order_service import OrderService

MIN_TRANSACTION_NO_LENGTH = 3
MAX_DISPLAYED_ORDERS = 20
ORDER_ID_DISPLAY_LENGTH = 8


class CheckoutStates(StatesGroup):
    waiting_transaction_no = State()
    waiting_amount = State()


def build_customer_router(repository: StoreRepository, order_service: OrderService, admin_ids: set[int], payment_text: str) -> Router:
    router = Router(name="customer")

    @router.message(CommandStart())
    async def start(message: Message):
        await message.answer(
            "👋 Welcome to *SellerBot*\n"
            "Buy digital products securely with MMK manual payment.",
            parse_mode="Markdown",
            reply_markup=main_menu_keyboard(),
        )

    @router.callback_query(F.data == "menu:home")
    async def home(callback: CallbackQuery):
        await callback.message.edit_text(
            "🏠 *Main Menu*\nChoose an option:",
            parse_mode="Markdown",
            reply_markup=main_menu_keyboard(),
        )
        await callback.answer()

    @router.callback_query(F.data == "menu:products")
    async def show_products(callback: CallbackQuery):
        products = await repository.get_products()
        if not products:
            await callback.message.edit_text("😕 No products available right now.")
            await callback.answer()
            return

        lines = ["🛒 *Available Products*"]
        for product in products:
            stock = await repository.count_stock(product.product_id)
            lines.append(f"• *{product.name}* — `{product.price_mmk} MMK` (Stock: {stock})")

        await callback.message.edit_text(
            "\n".join(lines),
            parse_mode="Markdown",
            reply_markup=products_keyboard(products),
        )
        await callback.answer()

    @router.callback_query(F.data == "menu:history")
    async def order_history(callback: CallbackQuery):
        user_id = callback.from_user.id
        orders = await repository.get_orders_for_user(user_id)
        if not orders:
            await callback.message.edit_text("📦 You have no order history yet.", reply_markup=main_menu_keyboard())
            await callback.answer()
            return

        text = "📦 *Your Orders*\n" + "\n".join(
            f"`{o.order_id[:ORDER_ID_DISPLAY_LENGTH]}` • Product `{o.product_id}` • `{o.amount} MMK` • *{o.status.value}*"
            for o in orders[:MAX_DISPLAYED_ORDERS]
        )
        await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=main_menu_keyboard())
        await callback.answer()

    @router.callback_query(F.data.startswith("buy:"))
    async def begin_checkout(callback: CallbackQuery, state: FSMContext):
        product_id = callback.data.split(":", 1)[1]
        product = await repository.get_product(product_id)
        if product is None:
            await callback.answer("Product not found", show_alert=True)
            return

        stock = await repository.count_stock(product_id)
        if stock <= 0:
            await callback.answer("Out of stock", show_alert=True)
            return

        await state.set_state(CheckoutStates.waiting_transaction_no)
        await state.update_data(product_id=product_id, expected_amount=product.price_mmk)
        await callback.message.answer(
            f"💳 *MMK Payment Instructions*\n{payment_text}\n\n"
            f"Product: *{product.name}*\n"
            f"Amount: *{product.price_mmk} MMK*\n\n"
            "Send your transaction number now:",
            parse_mode="Markdown",
        )
        await callback.answer()

    @router.message(CheckoutStates.waiting_transaction_no)
    async def receive_tx(message: Message, state: FSMContext):
        tx_no = (message.text or "").strip()
        if len(tx_no) < MIN_TRANSACTION_NO_LENGTH:
            await message.answer("⚠️ Please enter a valid transaction number.")
            return
        await state.update_data(transaction_no=tx_no)
        await state.set_state(CheckoutStates.waiting_amount)
        await message.answer("💰 Enter paid amount in MMK (numbers only):")

    @router.message(CheckoutStates.waiting_amount)
    async def receive_amount(message: Message, state: FSMContext):
        raw = (message.text or "").strip().replace(",", "")
        if not raw.isdigit():
            await message.answer("⚠️ Amount must be a number.")
            return

        amount = int(raw)
        data = await state.get_data()
        expected = int(data["expected_amount"])
        if amount != expected:
            await message.answer(f"⚠️ Amount mismatch. Required: {expected} MMK")
            return

        order = await order_service.create_order(
            user_id=message.from_user.id,
            username=message.from_user.username or message.from_user.full_name,
            product_id=data["product_id"],
            amount=amount,
            transaction_no=data["transaction_no"],
        )

        await state.clear()
        await message.answer(
            "✅ Payment proof submitted successfully.\n"
            "Your order is pending admin review.",
            reply_markup=main_menu_keyboard(),
        )

        for admin_id in admin_ids:
            try:
                await message.bot.send_message(
                    admin_id,
                    "🧾 *New Payment Request*\n"
                    f"Order: `{order.order_id}`\n"
                    f"User: `{order.user_id}` (@{message.from_user.username or 'n/a'})\n"
                    f"Product: `{order.product_id}`\n"
                    f"Amount: `{order.amount} MMK`\n"
                    f"Txn No: `{order.transaction_no}`",
                    parse_mode="Markdown",
                    reply_markup=admin_order_keyboard(order.order_id),
                )
            except Exception:
                continue

    return router
