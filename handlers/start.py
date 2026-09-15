"""Старт — You vs You."""

from aiogram import F, Router
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
    WebAppInfo,
)

from sqlalchemy import select

from database import async_session
from game import engine
from game.login_token import webapp_url_for
from game.state import GameState

router = Router()


async def _remember_user(u, friend_from: int | None = None) -> None:
    """Запомнить Telegram-профиль и опционально подружиться по инвайту."""
    try:
        async with async_session() as session:
            res = await session.execute(select(GameState).where(GameState.telegram_id == u.id))
            gs = res.scalar_one_or_none()
            if gs is None:
                gs = GameState(telegram_id=u.id, name="Охотник-" + str(abs(u.id))[-4:])
                session.add(gs)
            gs.real_name = (" ".join(x for x in [u.first_name, u.last_name] if x))[:60]
            gs.real_username = (u.username or "")[:40]

            if friend_from and friend_from != u.id:
                engine.add_friend(gs, friend_from)
                res2 = await session.execute(
                    select(GameState).where(GameState.telegram_id == friend_from)
                )
                other = res2.scalar_one_or_none()
                if other is not None:
                    engine.add_friend(other, u.id)

            await session.commit()
    except Exception:
        pass


def main_keyboard(tid: int) -> ReplyKeyboardMarkup:
    url = webapp_url_for(tid)
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="💪 You vs You", web_app=WebAppInfo(url=url))],
        ],
        resize_keyboard=True,
    )


def inline_play(tid: int, duel_id: int | None = None) -> InlineKeyboardMarkup:
    url = webapp_url_for(tid, duel=duel_id) if duel_id else webapp_url_for(tid)
    label = "⚔️ Принять бой" if duel_id else "⚔️ Войти в игру"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=label, web_app=WebAppInfo(url=url))]
        ]
    )


WELCOME = (
    "Ты vs ты. Без зала. Без отмазок.\n\n"
    "<b>YOU vs YOU</b> — камера сама считает повторы, пока ты проходишь уровни, "
    "валишь боссов и качаешь героя. Или просто делаешь спокойную тренировку дня.\n\n"
    "🔥 Дома, за пару минут: отжимания, присед, пресс, планка\n"
    "🗺️ Сразу открыты первые локации — заходи и играй\n"
    "⚔️ Новое: арена 1 на 1 с друзьями и рандомами\n\n"
    "Хватит планировать. Открой и сделай первый подход 👇"
)

WELCOME_FRIEND = (
    "Вас позвали посоревноваться в <b>YOU vs YOU</b> 🏆\n\n"
    "Теперь вы в рейтинге друзей. Открой игру и покажи, кто сильнее 👇"
)

WELCOME_DUEL = (
    "⚔️ Тебя вызвали на бой 1 на 1!\n\n"
    "60 секунд, одно упражнение — кто сделает больше повторов.\n"
    "Открой арену и прими вызов 👇"
)


def _parse_friend_arg(args: str | None) -> int | None:
    if not args:
        return None
    raw = args.strip()
    if raw.startswith("fr_"):
        raw = raw[3:]
    else:
        return None
    try:
        tid = int(raw)
    except ValueError:
        return None
    return tid if tid > 0 else None


def _parse_duel_arg(args: str | None) -> int | None:
    if not args:
        return None
    raw = args.strip()
    if raw.startswith("du_"):
        raw = raw[3:]
    elif raw.startswith("duel_"):
        raw = raw[5:]
    else:
        return None
    try:
        did = int(raw)
    except ValueError:
        return None
    return did if did > 0 else None


@router.message(CommandStart())
async def cmd_start(message: Message, command: CommandObject) -> None:
    args = command.args if command else None
    friend_from = _parse_friend_arg(args)
    duel_id = _parse_duel_arg(args)
    tid = message.from_user.id if message.from_user else 0
    if message.from_user:
        await _remember_user(message.from_user, friend_from)
    if duel_id:
        text = WELCOME_DUEL
    elif friend_from:
        text = WELCOME_FRIEND
    else:
        text = WELCOME
    await message.answer(text, reply_markup=main_keyboard(tid))
    await message.answer(
        "Жми — и погнали:" if not duel_id else "Открой бой:",
        reply_markup=inline_play(tid, duel_id),
    )


@router.message(Command("battle"))
@router.message(Command("arena"))
@router.message(Command("help"))
@router.message(F.text == "💪 You vs You")
async def cmd_battle(message: Message) -> None:
    tid = message.from_user.id if message.from_user else 0
    if message.from_user:
        await _remember_user(message.from_user)
    await message.answer(WELCOME, reply_markup=main_keyboard(tid))
    await message.answer("Жми — и погнали:", reply_markup=inline_play(tid))
