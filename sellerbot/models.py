from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class OrderStatus(StrEnum):
    AWAITING_REVIEW = "awaiting_review"
    APPROVED = "approved"
    REJECTED = "rejected"


@dataclass(slots=True)
class Product:
    product_id: str
    name: str
    price_mmk: int


@dataclass(slots=True)
class Order:
    order_id: str
    user_id: int
    username: str
    product_id: str
    amount: int
    status: OrderStatus
    date: datetime
    transaction_no: str
