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
Create one spreadsheet with these sheets and headers:

### `Products`
`ProductID | ProductName | PriceMMK`

### `Stock`
`ProductID | StockData`

### `Orders`
`OrderID | UserID | Username | ProductID | Amount | Status | Date | TransactionNo`

> Admin can add stock by pasting new rows in `Stock`. Bot reads live data so stock count updates automatically.

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
