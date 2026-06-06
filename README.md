# SellerBot

Telegram Digital Product Store Bot (Python + Aiogram) with manual MMK payment flow and Google Sheets as database.

## Features

### Customer
- `/start` menu
- View products, prices, and live stock count
- Buy product via manual MMK payment
- Submit transaction number + amount as payment proof
- View order history

### Admin
- Receive payment approval requests with inline buttons
- Approve/Reject orders
- Automatic stock delivery on approval
- Used stock row is deleted from Google Sheets (single-use stock)
- View order statistics
- Broadcast messages to all customers

## Google Sheets Setup
Create one spreadsheet with one tab per table. Keep row 1 as headers, one row per record, no merged cells, and no blank header names.

### `Users`
`id | telegram_user_id | username | display_name | status | created_at | updated_at`

### `Products`
`id | name | price_mmk | status | created_at | updated_at`

### `StockItems`
`id | product_id | stock_data | status | created_at | updated_at`

### `Orders`
`id | user_id | username | product_id | amount_mmk | transaction_no | status | created_at | updated_at`

### `OrderItems`
`id | order_id | product_id | stock_item_id | delivered_data | status | created_at | updated_at`

### `StatusLookup`
`entity | status | description`

### `Reports` (optional query/read tab)
`metric | value | updated_at`

Recommended status values:
- `Users.status`: `active`, `blocked`
- `Products.status`: `active`, `inactive`
- `StockItems.status`: `available`, `consumed`
- `Orders.status`: `awaiting_review`, `approved`, `rejected`
- `OrderItems.status`: `delivered`

Use Google Sheets dropdown validation for all `status` columns and point them to values in `StatusLookup` to keep enums consistent.

> Admin can add stock by pasting new rows in `StockItems`. Bot reads live data so stock count updates automatically.

## Installation Guide

1. **Clone and enter project**
   ```bash
   git clone <repo-url>
   cd SellerBot
   ```
2. **Create virtual environment**
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # Windows: .venv\Scripts\activate
   ```
3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```
4. **Prepare Google service account**
   - Enable Google Sheets API in Google Cloud
   - Create Service Account JSON key
   - Share your spreadsheet with the service account email
5. **Configure environment variables**
   ```bash
   cp .env.example .env
   # edit .env with your real values
   ```
6. **Run bot**
   ```bash
   python -m sellerbot.main
   ```

## Environment Variables

- `BOT_TOKEN`: Telegram bot token
- `GOOGLE_SHEET_ID`: Google Spreadsheet ID
- `GOOGLE_SERVICE_ACCOUNT_FILE`: Absolute path to service account JSON file
- `GOOGLE_SERVICE_ACCOUNT_JSON`: JSON string alternative to file path
- `ADMIN_IDS`: Comma-separated Telegram user IDs with admin access
- `MMK_PAYMENT_INSTRUCTIONS`: Payment instructions shown during checkout

## Architecture

- `sellerbot/main.py`: app bootstrap
- `sellerbot/config.py`: env config loader
- `sellerbot/sheets.py`: async Google Sheets repository
- `sellerbot/services/order_service.py`: order approval/rejection and anti-double-delivery lock
- `sellerbot/handlers/customer.py`: customer flow
- `sellerbot/handlers/admin.py`: admin panel flow
- `sellerbot/keyboards.py`: inline keyboards

## Run Tests

```bash
python -m unittest discover -s tests -q
```
