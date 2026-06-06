from __future__ import annotations

import asyncio
from collections.abc import Iterable
from datetime import datetime, timezone
from typing import Any

import gspread
from google.oauth2.service_account import Credentials

from sellerbot.models import Order, OrderStatus, Product
from sellerbot.repository import StoreRepository

PRODUCT_HEADERS = ["ProductID", "ProductName", "PriceMMK"]
STOCK_HEADERS = ["ProductID", "StockData"]
ORDER_HEADERS = [
    "OrderID",
    "UserID",
    "Username",
    "ProductID",
    "Amount",
    "Status",
    "Date",
    "TransactionNo",
]
MIN_WORKSHEET_COLS = 8
# Google Sheets API uses 1-indexed column coordinates, where F == 6.
ORDER_STATUS_COLUMN = 6


class GoogleSheetsRepository:
    def __init__(self, sheet_id: str, service_account_file: str | None, service_account_info: dict | None):
        self._sheet_id = sheet_id
        self._service_account_file = service_account_file
        self._service_account_info = service_account_info
        self._spreadsheet = None

    async def _open(self):
        if self._spreadsheet is not None:
            return self._spreadsheet

        def _sync_open():
            scopes = ["https://www.googleapis.com/auth/spreadsheets"]
            if self._service_account_info:
                creds = Credentials.from_service_account_info(self._service_account_info, scopes=scopes)
            elif self._service_account_file:
                creds = Credentials.from_service_account_file(self._service_account_file, scopes=scopes)
            else:
                raise ValueError("GOOGLE_SERVICE_ACCOUNT_FILE or GOOGLE_SERVICE_ACCOUNT_JSON is required")

            client = gspread.authorize(creds)
            spreadsheet = client.open_by_key(self._sheet_id)
            self._ensure_headers(spreadsheet)
            return spreadsheet

        self._spreadsheet = await asyncio.to_thread(_sync_open)
        return self._spreadsheet

    def _ensure_headers(self, spreadsheet) -> None:
        self._ensure_sheet_headers(spreadsheet, "Products", PRODUCT_HEADERS)
        self._ensure_sheet_headers(spreadsheet, "Stock", STOCK_HEADERS)
        self._ensure_sheet_headers(spreadsheet, "Orders", ORDER_HEADERS)

    def _ensure_sheet_headers(self, spreadsheet, title: str, headers: Iterable[str]) -> None:
        try:
            ws = spreadsheet.worksheet(title)
        except gspread.WorksheetNotFound:
            ws = spreadsheet.add_worksheet(title=title, rows=1000, cols=max(MIN_WORKSHEET_COLS, len(tuple(headers))))
        first_row = ws.row_values(1)
        if first_row != list(headers):
            ws.update("A1", [list(headers)])

    async def _sheet(self, name: str):
        book = await self._open()
        return await asyncio.to_thread(book.worksheet, name)

    async def get_products(self) -> list[Product]:
        ws = await self._sheet("Products")
        records = await asyncio.to_thread(ws.get_all_records)
        products: list[Product] = []
        for row in records:
            if not row.get("ProductID"):
                continue
            price = self._parse_int_field(row.get("PriceMMK"), default=-1)
            if price < 0:
                continue
            products.append(
                Product(
                    product_id=str(row["ProductID"]).strip(),
                    name=str(row.get("ProductName", "Unknown")).strip(),
                    price_mmk=price,
                )
            )
        return products

    async def get_product(self, product_id: str) -> Product | None:
        products = await self.get_products()
        for product in products:
            if product.product_id == product_id:
                return product
        return None

    async def count_stock(self, product_id: str) -> int:
        ws = await self._sheet("Stock")
        records = await asyncio.to_thread(ws.get_all_records)
        return sum(1 for row in records if str(row.get("ProductID", "")).strip() == product_id and row.get("StockData"))

    async def create_order(self, order: Order) -> None:
        ws = await self._sheet("Orders")
        row = [
            order.order_id,
            str(order.user_id),
            order.username,
            order.product_id,
            str(order.amount),
            order.status.value,
            order.date.astimezone(timezone.utc).isoformat(),
            order.transaction_no,
        ]
        await asyncio.to_thread(ws.append_row, row, value_input_option="USER_ENTERED")

    async def get_order(self, order_id: str) -> Order | None:
        ws = await self._sheet("Orders")
        records = await asyncio.to_thread(ws.get_all_records)
        for row in records:
            if str(row.get("OrderID", "")).strip() != order_id:
                continue
            return self._order_from_row(row)
        return None

    async def update_order_status(self, order_id: str, status: OrderStatus) -> None:
        ws = await self._sheet("Orders")
        values = await asyncio.to_thread(ws.get_all_values)
        for idx, row in enumerate(values[1:], start=2):
            if len(row) > 0 and row[0].strip() == order_id:
                await asyncio.to_thread(ws.update_cell, idx, ORDER_STATUS_COLUMN, status.value)
                break

    async def pop_first_stock_item(self, product_id: str) -> str | None:
        ws = await self._sheet("Stock")
        values = await asyncio.to_thread(ws.get_all_values)
        for idx, row in enumerate(values[1:], start=2):
            if len(row) < 2:
                continue
            if row[0].strip() != product_id:
                continue
            stock_data = row[1].strip()
            if not stock_data:
                continue
            await asyncio.to_thread(ws.delete_rows, idx)
            return stock_data
        return None

    async def get_orders_for_user(self, user_id: int) -> list[Order]:
        ws = await self._sheet("Orders")
        records = await asyncio.to_thread(ws.get_all_records)
        orders = [
            self._order_from_row(row)
            for row in records
            if str(row.get("UserID", "")).strip() == str(user_id)
        ]
        orders.sort(key=lambda item: item.date, reverse=True)
        return orders

    async def get_user_ids(self) -> list[int]:
        ws = await self._sheet("Orders")
        records = await asyncio.to_thread(ws.get_all_records)
        user_ids: set[int] = set()
        for row in records:
            raw = str(row.get("UserID", "")).strip()
            if raw.isdigit():
                user_ids.add(int(raw))
        return sorted(user_ids)

    async def get_statistics(self) -> dict[str, int]:
        ws = await self._sheet("Orders")
        records = await asyncio.to_thread(ws.get_all_records)
        stats = {
            "total": len(records),
            "awaiting_review": 0,
            "approved": 0,
            "rejected": 0,
        }
        for row in records:
            status = str(row.get("Status", "")).strip()
            if status in stats:
                stats[status] += 1
        return stats

    def _order_from_row(self, row: dict[str, Any]) -> Order:
        date_raw = str(row.get("Date", "")).strip()
        try:
            created = datetime.fromisoformat(date_raw) if date_raw else datetime.now(timezone.utc)
        except ValueError:
            created = datetime.now(timezone.utc)
        status_raw = str(row.get("Status", OrderStatus.AWAITING_REVIEW.value)).strip()
        try:
            status = OrderStatus(status_raw)
        except ValueError:
            status = OrderStatus.AWAITING_REVIEW

        return Order(
            order_id=str(row.get("OrderID", "")).strip(),
            user_id=self._parse_int_field(row.get("UserID"), default=0),
            username=str(row.get("Username", "")).strip(),
            product_id=str(row.get("ProductID", "")).strip(),
            amount=self._parse_int_field(row.get("Amount"), default=0),
            status=status,
            date=created,
            transaction_no=str(row.get("TransactionNo", "")).strip(),
        )

    @staticmethod
    def _parse_int_field(value: Any, default: int = 0) -> int:
        try:
            return int(str(value).strip())
        except (TypeError, ValueError):
            return default
