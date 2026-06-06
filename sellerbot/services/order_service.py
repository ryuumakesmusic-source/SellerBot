from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from uuid import uuid4

from sellerbot.models import Order, OrderStatus
from sellerbot.repository import StoreRepository


class OutOfStockError(Exception):
    """Raised when there is no stock left for a requested product."""


class OrderNotAwaitingReviewError(Exception):
    """Raised when admin tries to process an order already handled."""


class OrderService:
    def __init__(self, repository: StoreRepository):
        self._repository = repository
        self._order_locks: dict[str, asyncio.Lock] = {}
        self._product_locks: dict[str, asyncio.Lock] = {}
        self._global_lock = asyncio.Lock()

    async def create_order(self, user_id: int, username: str, product_id: str, amount: int, transaction_no: str) -> Order:
        order = Order(
            order_id=uuid4().hex,
            user_id=user_id,
            username=username or "unknown",
            product_id=product_id,
            amount=amount,
            status=OrderStatus.AWAITING_REVIEW,
            date=datetime.now(timezone.utc),
            transaction_no=transaction_no,
        )
        await self._repository.create_order(order)
        return order

    async def approve_order(self, order_id: str) -> tuple[Order, str]:
        order_lock = await self._get_order_lock(order_id)
        async with order_lock:
            order = await self._repository.get_order(order_id)
            if order is None:
                raise ValueError("Order not found")
            if order.status != OrderStatus.AWAITING_REVIEW:
                raise OrderNotAwaitingReviewError("Order already processed")

            product_lock = await self._get_product_lock(order.product_id)
            async with product_lock:
                stock = await self._repository.pop_first_stock_item(order.product_id)
                if not stock:
                    raise OutOfStockError("No stock available")

            await self._repository.update_order_status(order_id, OrderStatus.APPROVED)
            order.status = OrderStatus.APPROVED
            return order, stock

    async def reject_order(self, order_id: str) -> Order:
        order_lock = await self._get_order_lock(order_id)
        async with order_lock:
            order = await self._repository.get_order(order_id)
            if order is None:
                raise ValueError("Order not found")
            if order.status != OrderStatus.AWAITING_REVIEW:
                raise OrderNotAwaitingReviewError("Order already processed")
            await self._repository.update_order_status(order_id, OrderStatus.REJECTED)
            order.status = OrderStatus.REJECTED
            return order

    async def _get_order_lock(self, order_id: str) -> asyncio.Lock:
        async with self._global_lock:
            if order_id not in self._order_locks:
                self._order_locks[order_id] = asyncio.Lock()
            return self._order_locks[order_id]

    async def _get_product_lock(self, product_id: str) -> asyncio.Lock:
        async with self._global_lock:
            if product_id not in self._product_locks:
                self._product_locks[product_id] = asyncio.Lock()
            return self._product_locks[product_id]
