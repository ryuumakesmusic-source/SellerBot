from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from sellerbot.config import load_config
from sellerbot.handlers.admin import build_admin_router
from sellerbot.handlers.customer import build_customer_router
from sellerbot.services.order_service import OrderService
from sellerbot.sheets import GoogleSheetsRepository


async def run_bot() -> None:
    config = load_config()
    repository = GoogleSheetsRepository(
        sheet_id=config.google_sheet_id,
        service_account_file=config.google_service_account_file,
        service_account_info=config.google_service_account_json,
    )
    order_service = OrderService(repository)

    dp = Dispatcher()
    dp.include_router(
        build_customer_router(
            repository=repository,
            order_service=order_service,
            admin_ids=config.admin_ids,
            payment_text=config.mmk_payment_instructions,
        )
    )
    dp.include_router(
        build_admin_router(
            repository=repository,
            order_service=order_service,
            admin_ids=config.admin_ids,
        )
    )

    bot = Bot(token=config.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    await dp.start_polling(bot)


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_bot())


if __name__ == "__main__":
    main()
