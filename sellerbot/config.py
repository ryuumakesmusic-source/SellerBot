from __future__ import annotations

import json
import os
from dataclasses import dataclass

from dotenv import load_dotenv


@dataclass(slots=True)
class Config:
    bot_token: str
    google_sheet_id: str
    admin_ids: set[int]
    mmk_payment_instructions: str
    google_service_account_file: str | None
    google_service_account_json: dict | None


def load_config() -> Config:
    load_dotenv()
    bot_token = os.getenv("BOT_TOKEN", "").strip()
    sheet_id = os.getenv("GOOGLE_SHEET_ID", "").strip()
    admin_ids_raw = os.getenv("ADMIN_IDS", "")
    payment_text = os.getenv(
        "MMK_PAYMENT_INSTRUCTIONS",
        "KBZPay/WavePay: Please pay and send transaction number with amount.",
    )
    service_file = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE")
    service_json_raw = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")

    if not bot_token:
        raise ValueError("BOT_TOKEN is required")
    if not sheet_id:
        raise ValueError("GOOGLE_SHEET_ID is required")

    admin_ids = {
        int(item.strip())
        for item in admin_ids_raw.split(",")
        if item.strip().isdigit()
    }
    if not admin_ids:
        raise ValueError("ADMIN_IDS must include at least one Telegram user id")

    service_json = None
    if service_json_raw:
        service_json = json.loads(service_json_raw)

    return Config(
        bot_token=bot_token,
        google_sheet_id=sheet_id,
        admin_ids=admin_ids,
        mmk_payment_instructions=payment_text,
        google_service_account_file=service_file,
        google_service_account_json=service_json,
    )
