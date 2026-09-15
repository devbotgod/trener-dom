"""Умные напоминания «You vs You» — в выбранное пользователем время (МСК)."""

from __future__ import annotations

import asyncio
import logging
import random
from datetime import date

from aiogram import Bot
from sqlalchemy import select

from database import async_session
from game.state import GameState
from utils.timezone import now_msk, today_msk

logger = logging.getLogger(__name__)

# Обычные напоминания — без активной серии
ADV_MSGS = [
    "🐺 Эй! Монстры заждались. 5 минут — и ты герой дня.",
    "⚔️ Твой герой скучает без тебя. Заглянешь во Врата?",
    "😼 Диван подождёт. Монстры — нет. Погнали!",
    "🎯 Ежедневные задания обновились. Опыт сам себя не заберёт.",
    "🗡️ Врата открыты. Один подход — и день уже не зря.",
    "🔥 Камера готова. Ты — нет. Исправляем?",
    "🐉 Боссы шепчут твоё имя. Не разочаруй их… и себя.",
    "🗺️ Карта ждёт. Сегодня можно пройти ещё один уровень.",
    "💪 Сила качается подходами, а не обещаниями. Заходи!",
    "🎮 Короткий рейд на 5–10 минут. Справишься?",
    "🛡️ Герой без тренировки — просто скин. Прокачаемся?",
    "⚡ XP не фармится сам. Быстрый бой — и ты в плюсе.",
]
SIMPLE_MSGS = [
    "🌸 Не забудь про себя сегодня! Пара упражнений — и ты молодец.",
    "✨ Тело скажет спасибо. Заглянешь на тренировку дня?",
    "💗 5 минут для себя — это уже победа. Погнали?",
    "🌷 Маленький шаг сегодня — большой результат потом.",
    "🧘 Лёгкая тренировка — и день ощущается совсем иначе.",
    "🌿 Без давления: просто зайди и сделай своё.",
    "☀️ Вечер идеален для короткой сессии. Готов?",
    "🫶 Ты обещал себе заниматься. Сегодня — хороший момент.",
    "💫 Пресс, спина, ноги — выбери удобное и начни.",
    "🏃 Движение лечит лень. 5 минут хватит, чтобы стартануть.",
    "🎯 Тренировка дня уже собрана под тебя. Осталось нажать.",
    "😌 Без героизма — просто привычка. Заглянешь?",
]

ADV_STREAK = [
    "🔥 Серия {n} {d} в опасности! Не дай ей сгореть — заходи, боец.",
    "🔥 {n} {d} подряд. Монстры уже считают, сдашься ли ты сегодня.",
    "⚔️ Серия {n} — это уважение. Один подход, и она жива.",
    "🛡️ Не отдавай серию {n} дивану. Быстрый бой — и спокойной ночи.",
    "🗡️ {n} {d} стрика. Жалко терять такую полоску, правда?",
    "🐺 Серия {n} смотрит на тебя. Сохрани её за 5 минут.",
]
SIMPLE_STREAK = [
    "🔥 {n} {d} подряд — жалко терять! Сделай подход и сохрани серию 🌸",
    "🔥 Серия {n} ещё жива. Короткой тренировки хватит, чтобы её удержать.",
    "💗 {n} {d} заботы о себе. Не обрывай сегодня — ты так близко.",
    "✨ Серия {n} — это уже привычка. Поддержи её маленьким шагом.",
    "🌷 Не дай серии {n} сгореть из‑за одного вечера на диване.",
    "🫶 {n} {d} подряд. Гордись — и сохрани одним заходом.",
]

ADV_LAST = [
    "⏰ Последний шанс сегодня! Серия {n} 🔥 vs твоя лень. Кто победит?",
    "⏰ Почти конец дня. Серия {n} ещё спасаема — заходи!",
    "🌙 Финальный нудж: 5 минут боя, и серия {n} переживёт ночь.",
    "⚔️ День закрывается. Успеешь ударить по вратам за серию {n}?",
    "🔥 Серия {n} на грани. Последний подход — и спи спокойно.",
    "🗡️ Это уже не «потом». Сейчас или серия {n} горит.",
]
SIMPLE_LAST = [
    "⏰ День почти кончился! Пара минут — и серия {n} 🔥 в безопасности.",
    "🌙 Последний мягкий пинг: сохрани серию {n} короткой тренировкой.",
    "💗 Ещё не поздно. Серия {n} ждёт один маленький заход.",
    "✨ Перед сном — 5 минут для себя, и серия {n} жива.",
    "🌷 День уходит. Успеешь удержать серию {n}?",
    "🫶 Финал дня: зайди, сделай своё — серия {n} скажет спасибо.",
]

ADV_LAST_PLAIN = [
    "⏰ День почти ушёл. Короткий бой — и ты не пропустил тренировку.",
    "🌙 Последний шанс зайти во Врата сегодня. 5 минут хватит.",
    "⚔️ Ещё не поздно стать героем дня. Быстрый подход?",
    "🗡️ Вечерний рейд: зайди, ударь, закрой день красиво.",
    "🔥 Календарь завтра обнулится. Успеешь отметиться сегодня?",
    "🐺 Монстры не спят. Ты тоже можешь не сдаваться до конца дня.",
]
SIMPLE_LAST_PLAIN = [
    "⏰ День почти кончился. Пара упражнений — и ты молодец.",
    "🌙 Мягкий финальный пинг: зайди на тренировку дня.",
    "💗 Ещё не поздно сделать что‑то для себя сегодня.",
    "✨ 5 минут до конца дня — лучше, чем ноль.",
    "🌷 Закрой день маленькой победой. Заглянешь?",
    "🫶 Последний шанс сегодня. Без давления — просто зайди.",
]


def _plural_days(n: int) -> str:
    n = abs(n) % 100
    if 11 <= n <= 14:
        return "дней"
    u = n % 10
    if u == 1:
        return "день"
    if u in (2, 3, 4):
        return "дня"
    return "дней"


def _pick(pool: list[str], idx: int) -> str:
    if not pool:
        return ""
    return pool[(idx + random.randint(0, len(pool) - 1)) % len(pool)]


def _live_streak(streak: int, streak_date, freezes: int, today: date) -> int:
    if not streak or streak_date is None:
        return 0
    gap = (today - streak_date).days
    if gap <= 1:
        return streak
    missed = gap - 1
    if 0 < missed <= (freezes or 0):
        return streak
    return 0


def _message(mode: str, streak: int, last_call: bool, idx: int) -> str:
    simple = mode == "simple"
    if last_call:
        if streak >= 1:
            tmpl = _pick(SIMPLE_LAST if simple else ADV_LAST, idx)
            return tmpl.format(n=streak)
        return _pick(SIMPLE_LAST_PLAIN if simple else ADV_LAST_PLAIN, idx)
    if streak >= 1:
        tmpl = _pick(SIMPLE_STREAK if simple else ADV_STREAK, idx)
        return tmpl.format(n=streak, d=_plural_days(streak))
    return _pick(SIMPLE_MSGS if simple else ADV_MSGS, idx)


def _slot_times(hour: int, minute: int) -> tuple[tuple[int, int], tuple[int, int]]:
    """Основной слот и «последний шанс» (+2 часа)."""
    h = int(hour if hour is not None else 19) % 24
    m = max(0, min(59, int(minute or 0)))
    last_h = (h + 2) % 24
    return (h, m), (last_h, m)


def _due_now(now_h: int, now_m: int, target_h: int, target_m: int, window: int = 2) -> bool:
    """Попадаем в окно около целевого времени (минуты). Poll раз в ~60 сек."""
    now_total = now_h * 60 + now_m
    target_total = target_h * 60 + target_m
    return 0 <= (now_total - target_total) < window


async def reminder_loop(bot: Bot) -> None:
    idx = 0
    while True:
        try:
            now = now_msk()
            today = now.date()
            async with async_session() as session:
                res = await session.execute(select(GameState))
                rows = list(res.scalars().all())
                dirty = False
                for gs in rows:
                    if gs.reminders_on is False:
                        continue
                    if gs.daily_date == today and (gs.daily_reps or 0) > 0:
                        continue

                    main_hm, last_hm = _slot_times(
                        getattr(gs, "reminder_hour", 19),
                        getattr(gs, "reminder_minute", 0),
                    )
                    last_slot = gs.last_reminder_slot or ""
                    key_main = f"{today.isoformat()}:main"
                    key_last = f"{today.isoformat()}:last"

                    send_kind = None
                    if _due_now(now.hour, now.minute, *main_hm):
                        if last_slot not in (key_main, key_last):
                            send_kind = "main"
                    elif _due_now(now.hour, now.minute, *last_hm):
                        if last_slot != key_last:
                            send_kind = "last"

                    if not send_kind:
                        continue

                    live = _live_streak(
                        gs.streak_count or 0, gs.streak_date, gs.freezes or 0, today
                    )
                    idx += 1
                    text = _message(gs.mode or "adventure", live, send_kind == "last", idx)
                    try:
                        await bot.send_message(gs.telegram_id, text)
                        gs.last_reminder_slot = key_main if send_kind == "main" else key_last
                        dirty = True
                    except Exception as e:
                        logger.warning("reminder to %s failed: %s", gs.telegram_id, e)
                if dirty:
                    await session.commit()
        except Exception as e:
            logger.warning("reminder loop error: %s", e)
        await asyncio.sleep(60)
