from __future__ import annotations

import asyncio
import unittest
from datetime import datetime, timezone

from sellerbot.models import Order, OrderStatus, Product
from sellerbot.services.order_service import OrderNotAwaitingReviewError, OrderService, OutOfStockError


class FakeRepo:
    def __init__(self):
        self.products = {"p1": Product("p1", "VIP Key", 1000)}
        self.stock = {"p1": ["KEY-1"]}
        self.orders: dict[str, Order] = {}

    async def get_products(self):
        return list(self.products.values())

    async def get_product(self, product_id: str):
        return self.products.get(product_id)

    async def count_stock(self, product_id: str):
        return len(self.stock.get(product_id, []))

    async def create_order(self, order: Order):
        self.orders[order.order_id] = order

    async def get_order(self, order_id: str):
        return self.orders.get(order_id)

    async def update_order_status(self, order_id: str, status: OrderStatus):
        self.orders[order_id].status = status

    async def pop_first_stock_item(self, product_id: str):
        items = self.stock.get(product_id, [])
        if not items:
            return None
        return items.pop(0)

    async def get_orders_for_user(self, user_id: int):
        return [o for o in self.orders.values() if o.user_id == user_id]

    async def get_user_ids(self):
        return sorted({o.user_id for o in self.orders.values()})

    async def get_statistics(self):
        return {"total": len(self.orders), "awaiting_review": 0, "approved": 0, "rejected": 0}


class TestOrderService(unittest.IsolatedAsyncioTestCase):
    async def test_approve_order_delivers_once(self):
        repo = FakeRepo()
        service = OrderService(repo)

        order = Order(
            order_id="o1",
            user_id=1,
            username="alice",
            product_id="p1",
            amount=1000,
            status=OrderStatus.AWAITING_REVIEW,
            date=datetime.now(timezone.utc),
            transaction_no="txn-1",
        )
        await repo.create_order(order)

        approved_order, item = await service.approve_order("o1")
        self.assertEqual(approved_order.status, OrderStatus.APPROVED)
        self.assertEqual(item, "KEY-1")

        with self.assertRaises(OrderNotAwaitingReviewError):
            await service.approve_order("o1")

    async def test_concurrent_approval_prevents_double_delivery(self):
        repo = FakeRepo()
        repo.stock["p1"] = ["KEY-1", "KEY-2"]
        service = OrderService(repo)

        order = Order(
            order_id="o2",
            user_id=2,
            username="bob",
            product_id="p1",
            amount=1000,
            status=OrderStatus.AWAITING_REVIEW,
            date=datetime.now(timezone.utc),
            transaction_no="txn-2",
        )
        await repo.create_order(order)

        async def attempt():
            try:
                return await service.approve_order("o2")
            except Exception as exc:
                return exc

        results = await asyncio.gather(attempt(), attempt())
        successes = [r for r in results if not isinstance(r, Exception)]
        failures = [r for r in results if isinstance(r, Exception)]

        self.assertEqual(len(successes), 1)
        self.assertEqual(len(failures), 1)
        self.assertIsInstance(failures[0], OrderNotAwaitingReviewError)
        self.assertEqual(successes[0][0].order_id, "o2")
        self.assertEqual(successes[0][1], "KEY-1")
        self.assertEqual(repo.stock["p1"], ["KEY-2"])

    async def test_approve_fails_when_no_stock(self):
        repo = FakeRepo()
        repo.stock["p1"] = []
        service = OrderService(repo)
        order = Order(
            order_id="o3",
            user_id=3,
            username="eve",
            product_id="p1",
            amount=1000,
            status=OrderStatus.AWAITING_REVIEW,
            date=datetime.now(timezone.utc),
            transaction_no="txn-3",
        )
        await repo.create_order(order)

        with self.assertRaises(OutOfStockError):
            await service.approve_order("o3")


if __name__ == "__main__":
    unittest.main()
