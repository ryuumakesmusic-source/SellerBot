from __future__ import annotations

from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from sellerbot.models import Product


def main_menu_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="🛍️ View Products", callback_data="menu:products")
    kb.button(text="📦 Order History", callback_data="menu:history")
    kb.adjust(1)
    return kb.as_markup()


def products_keyboard(products: list[Product]) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for product in products:
        kb.button(text=f"🧾 {product.name}", callback_data=f"buy:{product.product_id}")
    kb.button(text="⬅️ Back", callback_data="menu:home")
    kb.adjust(1)
    return kb.as_markup()


def admin_order_keyboard(order_id: str) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Approve", callback_data=f"admin:approve:{order_id}")
    kb.button(text="❌ Reject", callback_data=f"admin:reject:{order_id}")
    kb.adjust(2)
    return kb.as_markup()


def admin_panel_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="📊 View Statistics", callback_data="admin:stats")
    kb.button(text="📣 Broadcast Message", callback_data="admin:broadcast")
    kb.adjust(1)
    return kb.as_markup()
