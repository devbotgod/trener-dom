"""Общие middleware и фильтры доступа."""

from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, TelegramObject

from utils.menu import MAIN_MENU_BUTTONS

router = Router()


class AccessMiddleware(BaseMiddleware):
    """Открытый доступ: любой пользователь может пользоваться ботом (свои данные по id)."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        return await handler(event, data)


class ClearStateOnMenuMiddleware(BaseMiddleware):
    """Сбрасывает FSM при нажатии кнопок меню."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        if isinstance(event, Message) and event.text in MAIN_MENU_BUTTONS:
            state: FSMContext | None = data.get("state")
            if state:
                await state.clear()
        return await handler(event, data)
