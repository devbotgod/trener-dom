"""You vs You — Telegram-бот + Mini App (aiogram 3.x)."""

import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from config import BOT_TOKEN
from database import init_db
import game.state  # noqa: F401  — регистрирует таблицу game_state в metadata
from handlers import setup_routers
from handlers.common import AccessMiddleware, ClearStateOnMenuMiddleware
from webapp_api import start_api
from game_reminder import reminder_loop

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)


async def main() -> None:
    await init_db()
    logger.info("БД инициализирована")

    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher()
    dp.message.middleware(AccessMiddleware())
    dp.message.middleware(ClearStateOnMenuMiddleware())
    dp.callback_query.middleware(AccessMiddleware())
    dp.include_router(setup_routers())

    api_runner = await start_api(bot)
    asyncio.create_task(reminder_loop(bot))
    logger.info("You vs You запущен")
    try:
        await dp.start_polling(bot)
    finally:
        await api_runner.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
