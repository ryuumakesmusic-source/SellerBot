from __future__ import annotations

import asyncio
from collections.abc import Iterable
from datetime import datetime, timezone
from typing import Any

import gspread
from google.oauth2.service_account import Credentials

from sellerbot.models import Order, OrderStatus, Product
from sellerbot.repository import StoreRepository

USERS_HEADERS = ["id", "telegram_user_id", "username", "display_name", "status", "created_at", "updated_at"]
PRODUCT_HEADERS = ["id", "name", "price_mmk", "status", "created_at", "updated_at"]
STOCK_HEADERS = ["id", "product_id", "stock_data", "status", "created_at", "updated_at"]
ORDER_HEADERS = ["id", "user_id", "username", "product_id", "amount_mmk", "transaction_no", "status", "created_at", "updated_at"]
ORDER_ITEMS_HEADERS = [
    "id",
    "order_id",
    "product_id",
    "stock_item_id",
    "delivered_data",
    "status",
    "created_at",
    "updated_at",
]
STATUS_LOOKUP_HEADERS = ["entity", "status", "description"]
REPORT_HEADERS = ["metric", "value", "updated_at"]
MIN_WORKSHEET_COLS = 9
AVAILABLE_STOCK_STATUS = "available"


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
        self._ensure_sheet_headers(spreadsheet, "Users", USERS_HEADERS)
        self._ensure_sheet_headers(spreadsheet, "Products", PRODUCT_HEADERS)
        self._ensure_sheet_headers(spreadsheet, "StockItems", STOCK_HEADERS)
        self._ensure_sheet_headers(spreadsheet, "Orders", ORDER_HEADERS)
        self._ensure_sheet_headers(spreadsheet, "OrderItems", ORDER_ITEMS_HEADERS)
        self._ensure_sheet_headers(spreadsheet, "StatusLookup", STATUS_LOOKUP_HEADERS)
        self._ensure_sheet_headers(spreadsheet, "Reports", REPORT_HEADERS)
        self._ensure_status_lookup_rows(spreadsheet)

    def _ensure_sheet_headers(self, spreadsheet, title: str, headers: Iterable[str]) -> None:
        try:
            ws = spreadsheet.worksheet(title)
        except gspread.WorksheetNotFound:
            ws = spreadsheet.add_worksheet(title=title, rows=1000, cols=max(MIN_WORKSHEET_COLS, len(tuple(headers))))
        first_row = ws.row_values(1)
        if not any(cell.strip() for cell in first_row):
            ws.update("A1", [list(headers)])

    def _ensure_status_lookup_rows(self, spreadsheet) -> None:
        ws = spreadsheet.worksheet("StatusLookup")
        values = ws.get_all_values()
        if len(values) > 1:
            return
        ws.append_rows(
            [
                ["orders", OrderStatus.AWAITING_REVIEW.value, "Order submitted and awaiting admin review"],
                ["orders", OrderStatus.APPROVED.value, "Order approved by admin"],
                ["orders", OrderStatus.REJECTED.value, "Order rejected by admin"],
                ["products", "active", "Product can be listed and purchased"],
                ["products", "inactive", "Product is hidden or unavailable for purchase"],
                ["users", "active", "User can place new orders"],
                ["users", "blocked", "User is blocked from ordering"],
                ["stock_items", AVAILABLE_STOCK_STATUS, "Stock item can be delivered"],
                ["stock_items", "consumed", "Stock item already delivered or removed"],
                ["order_items", "delivered", "Delivered stock item for approved order"],
            ],
            value_input_option="USER_ENTERED",
        )

    async def _sheet(self, *names: str):
        book = await self._open()
        for name in names:
            try:
                return await asyncio.to_thread(book.worksheet, name)
            except gspread.WorksheetNotFound:
                continue
        raise gspread.WorksheetNotFound(f"No worksheet found for names: {', '.join(names)}")

    async def get_products(self) -> list[Product]:
        ws = await self._sheet("Products")
        records = await asyncio.to_thread(ws.get_all_records)
        products: list[Product] = []
        for row in records:
            product_id = self._clean_text(self._row_value(row, "id", "ProductID"))
            if not product_id:
                continue
            status = self._clean_text(self._row_value(row, "status", "Status")).lower()
            if status and status != "active":
                continue
            price = self._parse_int_field(self._row_value(row, "price_mmk", "PriceMMK"), default=-1)
            if price < 0:
                continue
            products.append(
                Product(
                    product_id=product_id,
                    name=self._clean_text(self._row_value(row, "name", "ProductName")) or "Unknown",
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
        ws = await self._sheet("StockItems", "Stock")
        records = await asyncio.to_thread(ws.get_all_records)
        count = 0
        for row in records:
            if self._clean_text(self._row_value(row, "product_id", "ProductID")) != product_id:
                continue
            stock_data = self._clean_text(self._row_value(row, "stock_data", "StockData"))
            if not stock_data:
                continue
            status = self._clean_text(self._row_value(row, "status", "Status")).lower()
            if status and status != AVAILABLE_STOCK_STATUS:
                continue
            count += 1
        return count

    async def create_order(self, order: Order) -> None:
        await self._upsert_user(order.user_id, order.username)
        ws = await self._sheet("Orders")
        headers = await asyncio.to_thread(ws.row_values, 1)
        if "OrderID" in headers:
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
        else:
            created_at = order.date.astimezone(timezone.utc).isoformat()
            row = [
                order.order_id,
                str(order.user_id),
                order.username,
                order.product_id,
                str(order.amount),
                order.transaction_no,
                order.status.value,
                created_at,
                created_at,
            ]
        await asyncio.to_thread(ws.append_row, row, value_input_option="USER_ENTERED")

    async def get_order(self, order_id: str) -> Order | None:
        ws = await self._sheet("Orders")
        records = await asyncio.to_thread(ws.get_all_records)
        for row in records:
            row_order_id = self._clean_text(self._row_value(row, "id", "OrderID"))
            if row_order_id != order_id:
                continue
            return self._order_from_row(row)
        return None

    async def update_order_status(self, order_id: str, status: OrderStatus) -> None:
        ws = await self._sheet("Orders")
        values = await asyncio.to_thread(ws.get_all_values)
        if not values:
            return
        headers = values[0]
        order_id_col = self._column_index(headers, "id", "OrderID")
        order_status_col = self._column_index(headers, "status", "Status")
        if order_id_col is None or order_status_col is None:
            return
        updated_at_col = self._column_index(headers, "updated_at")
        now_iso = datetime.now(timezone.utc).isoformat()
        for idx, row in enumerate(values[1:], start=2):
            raw_order_id = self._cell_value(row, order_id_col)
            if raw_order_id == order_id:
                await asyncio.to_thread(ws.update_cell, idx, order_status_col, status.value)
                if updated_at_col is not None:
                    await asyncio.to_thread(ws.update_cell, idx, updated_at_col, now_iso)
                break

    async def pop_first_stock_item(self, product_id: str) -> str | None:
        ws = await self._sheet("StockItems", "Stock")
        values = await asyncio.to_thread(ws.get_all_values)
        if not values:
            return None
        headers = values[0]
        product_col = self._column_index(headers, "product_id", "ProductID")
        stock_data_col = self._column_index(headers, "stock_data", "StockData")
        status_col = self._column_index(headers, "status", "Status")
        if product_col is None or stock_data_col is None:
            return None
        for idx, row in enumerate(values[1:], start=2):
            if self._cell_value(row, product_col) != product_id:
                continue
            stock_data = self._cell_value(row, stock_data_col)
            if not stock_data:
                continue
            status = self._cell_value(row, status_col).lower() if status_col is not None else AVAILABLE_STOCK_STATUS
            if status and status != AVAILABLE_STOCK_STATUS:
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
            if self._clean_text(self._row_value(row, "user_id", "UserID")) == str(user_id)
        ]
        orders.sort(key=lambda item: item.date, reverse=True)
        return orders

    async def get_user_ids(self) -> list[int]:
        ws = await self._sheet("Orders")
        records = await asyncio.to_thread(ws.get_all_records)
        user_ids: set[int] = set()
        for row in records:
            raw = self._clean_text(self._row_value(row, "user_id", "UserID"))
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
            status = self._clean_text(self._row_value(row, "status", "Status"))
            if status in stats:
                stats[status] += 1
        return stats

    def _order_from_row(self, row: dict[str, Any]) -> Order:
        date_raw = self._clean_text(self._row_value(row, "created_at", "Date"))
        try:
            created = datetime.fromisoformat(date_raw) if date_raw else datetime.now(timezone.utc)
        except ValueError:
            created = datetime.now(timezone.utc)
        status_raw = self._clean_text(self._row_value(row, "status", "Status", default=OrderStatus.AWAITING_REVIEW.value))
        try:
            status = OrderStatus(status_raw)
        except ValueError:
            status = OrderStatus.AWAITING_REVIEW

        return Order(
            order_id=self._clean_text(self._row_value(row, "id", "OrderID")),
            user_id=self._parse_int_field(self._row_value(row, "user_id", "UserID"), default=0),
            username=self._clean_text(self._row_value(row, "username", "Username")),
            product_id=self._clean_text(self._row_value(row, "product_id", "ProductID")),
            amount=self._parse_int_field(self._row_value(row, "amount_mmk", "Amount"), default=0),
            status=status,
            date=created,
            transaction_no=self._clean_text(self._row_value(row, "transaction_no", "TransactionNo")),
        )

    async def _upsert_user(self, user_id: int, username: str) -> None:
        ws = await self._sheet("Users")
        values = await asyncio.to_thread(ws.get_all_values)
        if not values:
            return
        headers = values[0]
        id_col = self._column_index(headers, "id")
        telegram_user_id_col = self._column_index(headers, "telegram_user_id")
        username_col = self._column_index(headers, "username")
        display_name_col = self._column_index(headers, "display_name")
        status_col = self._column_index(headers, "status")
        created_at_col = self._column_index(headers, "created_at")
        updated_at_col = self._column_index(headers, "updated_at")
        if id_col is None or telegram_user_id_col is None:
            return

        now_iso = datetime.now(timezone.utc).isoformat()
        user_id_text = str(user_id)
        username_text = username.strip() if username else "unknown"

        for row_index, row in enumerate(values[1:], start=2):
            if self._cell_value(row, telegram_user_id_col) != user_id_text:
                continue
            if username_col is not None:
                await asyncio.to_thread(ws.update_cell, row_index, username_col, username_text)
            if display_name_col is not None:
                await asyncio.to_thread(ws.update_cell, row_index, display_name_col, username_text)
            if updated_at_col is not None:
                await asyncio.to_thread(ws.update_cell, row_index, updated_at_col, now_iso)
            return

        row_values = []
        for index in range(1, len(headers) + 1):
            if index == id_col:
                row_values.append(user_id_text)
            elif index == telegram_user_id_col:
                row_values.append(user_id_text)
            elif index in (username_col, display_name_col):
                row_values.append(username_text)
            elif index == status_col:
                row_values.append("active")
            elif index in (created_at_col, updated_at_col):
                row_values.append(now_iso)
            else:
                row_values.append("")
        await asyncio.to_thread(ws.append_row, row_values, value_input_option="USER_ENTERED")

    @staticmethod
    def _row_value(row: dict[str, Any], *keys: str, default: Any = "") -> Any:
        for key in keys:
            if key in row and row.get(key) not in (None, ""):
                return row.get(key)
        for key in keys:
            if key in row:
                return row.get(key)
        return default

    @staticmethod
    def _clean_text(value: Any) -> str:
        return str(value).strip() if value is not None else ""

    @staticmethod
    def _column_index(headers: list[str], *candidate_names: str) -> int | None:
        normalized = [header.strip() for header in headers]
        for candidate in candidate_names:
            for index, header in enumerate(normalized, start=1):
                if header == candidate:
                    return index
        return None

    @staticmethod
    def _cell_value(row: list[str], col_index: int | None) -> str:
        if col_index is None or len(row) < col_index:
            return ""
        return row[col_index - 1].strip()

    @staticmethod
    def _parse_int_field(value: Any, default: int = 0) -> int:
        try:
            return int(str(value).strip())
        except (TypeError, ValueError):
            return default
