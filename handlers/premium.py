"""Premium и пожертвования: оплата Telegram Stars + VIP whitelist."""

from __future__ import annotations

import logging
from datetime import datetime

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    LabeledPrice,
    Message,
    PreCheckoutQuery,
)
from sqlalchemy import select

from config import (
    DONATE_DESCRIPTION,
    DONATE_MAX_STARS,
    DONATE_MIN_STARS,
    DONATE_PAYLOAD_PREFIX,
    DONATE_TITLE,
    PREMIUM_DESCRIPTION,
    PREMIUM_PAYLOAD,
    PREMIUM_STARS_PRICE,
    PREMIUM_TITLE,
    VIP_USER_IDS,
)
from database import async_session
from game.premium import has_premium
from game.state import GameState

logger = logging.getLogger(__name__)
router = Router()


def premium_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"⭐ Открыть Premium · {PREMIUM_STARS_PRICE} Stars",
                    callback_data="buy_premium",
                )
            ]
        ]
    )


def parse_donate_payload(payload: str) -> int | None:
    """Вернуть сумму Stars из payload donate или None."""
    if not payload or not payload.startswith(DONATE_PAYLOAD_PREFIX):
        return None
    raw = payload[len(DONATE_PAYLOAD_PREFIX) :]
    try:
        amount = int(raw)
    except ValueError:
        return None
    if amount < DONATE_MIN_STARS or amount > DONATE_MAX_STARS:
        return None
    return amount


def donate_payload(amount: int) -> str:
    return f"{DONATE_PAYLOAD_PREFIX}{int(amount)}"


async def _get_gs(tid: int) -> GameState:
    async with async_session() as session:
        res = await session.execute(select(GameState).where(GameState.telegram_id == tid))
        gs = res.scalar_one_or_none()
        if gs is None:
            gs = GameState(telegram_id=tid, name="Охотник-" + str(abs(tid))[-4:])
            session.add(gs)
            await session.commit()
            await session.refresh(gs)
        return gs


async def grant_premium(tid: int, charge_id: str = "") -> bool:
    """Выдать Premium конкретному telegram_id. True если только что выдали."""
    tid = int(tid)
    if tid <= 0:
        logger.error("grant_premium: bad tid=%s", tid)
        return False
    async with async_session() as session:
        res = await session.execute(select(GameState).where(GameState.telegram_id == tid))
        gs = res.scalar_one_or_none()
        if gs is None:
            gs = GameState(telegram_id=tid, name="Охотник-" + str(abs(tid))[-4:])
            session.add(gs)
            await session.flush()
        if bool(gs.premium):
            if charge_id and not (gs.premium_charge_id or ""):
                gs.premium_charge_id = charge_id[:120]
            await session.commit()
            logger.info("grant_premium: already premium tid=%s", tid)
            return False
        gs.premium = True
        gs.premium_charge_id = (charge_id or "")[:120]
        gs.premium_at = datetime.utcnow()
        await session.commit()
        logger.info(
            "grant_premium: GRANTED tid=%s charge=%s",
            tid,
            (charge_id or "")[:40],
        )
        return True


async def record_donation(tid: int, amount: int, charge_id: str = "") -> int:
    """Учесть пожертвование. Возвращает суммарные donated_stars."""
    async with async_session() as session:
        res = await session.execute(select(GameState).where(GameState.telegram_id == tid))
        gs = res.scalar_one_or_none()
        if gs is None:
            gs = GameState(telegram_id=tid, name="Охотник-" + str(abs(tid))[-4:])
            session.add(gs)
        gs.donated_stars = int(getattr(gs, "donated_stars", 0) or 0) + int(amount)
        _ = charge_id
        await session.commit()
        return int(gs.donated_stars)


@router.message(Command("premium"))
async def cmd_premium(message: Message) -> None:
    tid = message.from_user.id if message.from_user else 0
    gs = await _get_gs(tid)
    if tid in VIP_USER_IDS:
        await message.answer(
            "⭐ У тебя <b>полный доступ</b> (VIP) — все локации открыты без оплаты."
        )
        return
    if has_premium(gs):
        await message.answer("⭐ Premium уже активен — все локации открыты. Спасибо!")
        return
    await message.answer(
        f"<b>{PREMIUM_TITLE}</b>\n\n"
        f"{PREMIUM_DESCRIPTION}\n\n"
        f"Цена: <b>{PREMIUM_STARS_PRICE} ⭐</b> (разово).",
        reply_markup=premium_keyboard(),
    )


@router.callback_query(F.data == "buy_premium")
async def cb_buy_premium(callback: CallbackQuery) -> None:
    tid = callback.from_user.id if callback.from_user else 0
    gs = await _get_gs(tid)
    if has_premium(gs):
        await callback.answer("Premium уже активен", show_alert=True)
        return
    await callback.answer()
    await callback.message.answer_invoice(
        title=PREMIUM_TITLE,
        description=PREMIUM_DESCRIPTION,
        payload=PREMIUM_PAYLOAD,
        currency="XTR",
        prices=[LabeledPrice(label="Premium", amount=PREMIUM_STARS_PRICE)],
        provider_token="",
    )


@router.pre_checkout_query()
async def on_pre_checkout(query: PreCheckoutQuery) -> None:
    payload = query.invoice_payload or ""
    currency = (query.currency or "").upper()
    total = int(query.total_amount or 0)
    tid = query.from_user.id if query.from_user else 0

    donate_amount = parse_donate_payload(payload)
    if donate_amount is not None:
        if currency != "XTR" or total != donate_amount:
            await query.answer(ok=False, error_message="Сумма пожертвования не совпадает")
            return
        await query.answer(ok=True)
        return

    if payload != PREMIUM_PAYLOAD:
        logger.warning("pre_checkout unknown payload tid=%s payload=%r", tid, payload)
        await query.answer(ok=False, error_message="Неизвестный платёж")
        return
    if currency != "XTR" or total != int(PREMIUM_STARS_PRICE):
        logger.warning(
            "pre_checkout bad amount tid=%s currency=%s total=%s",
            tid, currency, total,
        )
        await query.answer(ok=False, error_message="Неверная сумма Premium")
        return

    gs = await _get_gs(tid)
    if has_premium(gs):
        await query.answer(ok=False, error_message="Premium уже активен")
        return
    await query.answer(ok=True)
    logger.info("pre_checkout OK premium tid=%s", tid)


@router.message(F.successful_payment)
async def on_successful_payment(message: Message) -> None:
    sp = message.successful_payment
    if not sp:
        return
    payload = sp.invoice_payload or ""
    tid = message.from_user.id if message.from_user else 0
    charge = sp.telegram_payment_charge_id or ""
    currency = (sp.currency or "").upper()
    total = int(sp.total_amount or 0)

    logger.info(
        "successful_payment tid=%s payload=%r currency=%s total=%s charge=%s",
        tid, payload, currency, total, charge[:40],
    )

    donate_amount = parse_donate_payload(payload)
    if donate_amount is not None:
        if currency == "XTR" and total == donate_amount:
            await record_donation(tid, donate_amount, charge)
        else:
            logger.error(
                "donate amount mismatch tid=%s total=%s expected=%s",
                tid, total, donate_amount,
            )
        await message.answer(
            "🙏 <b>Спасибо, что помогаете развиваться проекту!</b>\n\n"
            "Мы это очень ценим — благодаря такой поддержке "
            "YOU vs YOU становится лучше. ✨"
        )
        return

    if payload != PREMIUM_PAYLOAD:
        logger.warning("successful_payment ignored payload tid=%s payload=%r", tid, payload)
        return

    if currency != "XTR" or total != int(PREMIUM_STARS_PRICE):
        logger.error(
            "premium payment amount mismatch tid=%s currency=%s total=%s expected=%s — выдаём по payload",
            tid, currency, total, PREMIUM_STARS_PRICE,
        )

    try:
        granted = await grant_premium(tid, charge)
    except Exception:
        logger.exception("grant_premium FAILED tid=%s — повторю", tid)
        granted = await grant_premium(tid, charge)

    gs = await _get_gs(tid)
    ok = bool(gs.premium) or (tid in VIP_USER_IDS)
    if not ok:
        logger.error("premium NOT active after grant tid=%s — retry", tid)
        await grant_premium(tid, charge)
        gs = await _get_gs(tid)
        ok = bool(gs.premium)

    if ok:
        await message.answer(
            "🎉 <b>Premium активирован!</b>\n"
            "Все локации открыты — возвращайся в игру и продолжай поход. ⚔️"
            + ("" if granted else "")
        )
    else:
        logger.critical("premium grant failed permanently tid=%s charge=%s", tid, charge)
        await message.answer(
            "Оплата прошла, но активация задержалась. Напиши в поддержку — "
            "мы включим Premium вручную по этому платежу."
        )
