"""HTTP API для Telegram Mini App «You vs You».

Отдаёт игровое состояние и обрабатывает подходы (reps). Аутентификация —
через Telegram WebApp initData (HMAC по токену бота). По умолчанию слушает
127.0.0.1:8090; снаружи обычно проксируется nginx на ваш домен (WEBAPP_URL).
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import time
from urllib.parse import parse_qsl

import aiohttp
from aiohttp import web
from sqlalchemy import select

from config import (
    BOT_TOKEN,
    DONATE_DESCRIPTION,
    DONATE_MAX_STARS,
    DONATE_MIN_STARS,
    DONATE_TITLE,
    OWNER_TELEGRAM_ID,
    PREMIUM_DESCRIPTION,
    PREMIUM_PAYLOAD,
    PREMIUM_STARS_PRICE,
    PREMIUM_TITLE,
)
from database import async_session
from game import engine
from game import anticheat
from game.login_token import verify_login_token
from game.premium import has_premium
from game.state import GameState
from utils.timezone import today_msk

logger = logging.getLogger(__name__)

API_HOST = "127.0.0.1"
API_PORT = 8090


def _bot_deep_link(start_arg: str) -> str:
    """Deep-link в бота; пустая строка, если BOT_USERNAME не задан."""
    from config import BOT_USERNAME

    if not BOT_USERNAME:
        return ""
    return f"https://t.me/{BOT_USERNAME}?start={start_arg}"


# Секрет для локального тестирования без Telegram (?dev=...).
# В проде ВЫКЛЮЧЕН: без ALLOW_DEV_AUTH=1 нельзя зайти «под владельца».
# Раньше дефолт был "1" + клиент всем подставлял ?dev= → все логинились как владелец.
DEV_SECRET = os.environ.get("YVY_DEV_SECRET", "yvy-dev-disabled-rotate-me")
ALLOW_DEV_AUTH = os.environ.get("ALLOW_DEV_AUTH", "0") == "1"

# initData старше этого срока отклоняем (replay protection)
INIT_DATA_MAX_AGE_SEC = 86400


# --- аутентификация -----------------------------------------------------------

def _verify_init_data(init_data: str) -> int | None:
    """Проверить подпись initData и вернуть telegram_id, либо None."""
    if not init_data:
        return None
    try:
        pairs = dict(parse_qsl(init_data, keep_blank_values=True))
    except Exception:
        return None
    received_hash = pairs.pop("hash", None)
    if not received_hash:
        return None
    data_check_string = "\n".join(
        f"{k}={pairs[k]}" for k in sorted(pairs.keys())
    )
    secret_key = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
    calc_hash = hmac.new(
        secret_key, data_check_string.encode(), hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(calc_hash, received_hash):
        return None
    try:
        auth_date = int(pairs.get("auth_date", "0"))
    except (TypeError, ValueError):
        return None
    now = int(time.time())
    if auth_date <= 0 or now - auth_date > INIT_DATA_MAX_AGE_SEC or auth_date > now + 300:
        return None
    try:
        user = json.loads(pairs.get("user", "{}"))
        return int(user["id"])
    except Exception:
        return None


def _default_nick(tid: int) -> str:
    return "Охотник-" + str(abs(int(tid)))[-4:]


# Ники, которые нельзя показывать / ставить
_BANNED_NICK_PARTS = (
    "fuck", "fucker", "fucka", "shit", "bitch", "cunt", "nigg", "pidor", "пидор",
    "хуй", "хуе", "хуё", "бля", "еба", "ёба", "сука", "мудил", "долбо",
)


def _nick_banned(nick: str) -> bool:
    s = (nick or "").strip().lower().replace("@", "")
    if not s:
        return False
    # убрать простые обходы: f.u.c.k / f*uck / пробелы
    compact = "".join(ch for ch in s if ch.isalnum())
    for bad in _BANNED_NICK_PARTS:
        if bad in s or bad in compact:
            return True
    return False


def _safe_nick(nick: str | None, tid: int) -> str:
    n = (nick or "").strip()
    if not n or _nick_banned(n):
        return _default_nick(tid)
    return n[:20]


def _init_user(init_data: str) -> dict:
    """Реальный профиль Telegram из initData (для приватного просмотра владельцем)."""
    try:
        pairs = dict(parse_qsl(init_data, keep_blank_values=True))
        return json.loads(pairs.get("user", "{}")) or {}
    except Exception:
        return {}


def _auth(request: web.Request) -> int | None:
    """Вернуть telegram_id аутентифицированного пользователя.

    Приоритет:
    1) Telegram WebApp initData (подпись)
    2) персональный login-токен ?s= / X-YVY-Login (выдаётся кнопкой именно этому юзеру)
    3) опциональный DEV (только если явно включён) — никогда общий для всех
    """
    init_data = request.headers.get("X-Telegram-Init-Data", "") or ""
    if not init_data:
        auth = request.headers.get("Authorization", "") or ""
        if auth.lower().startswith("tma "):
            init_data = auth[4:].strip()
    if not init_data:
        init_data = request.query.get("initData", "") or ""

    tid = _verify_init_data(init_data)
    if tid is not None:
        return tid

    login = (
        request.headers.get("X-YVY-Login", "")
        or request.query.get("s", "")
        or ""
    ).strip()
    if login:
        tid = verify_login_token(login)
        if tid is not None:
            return tid

    # DEV только вручную через env — и только для локальной отладки.
    # В проде ALLOW_DEV_AUTH=0 → даже верный секрет НЕ пускает.
    # Нужен OWNER_TELEGRAM_ID > 0 в окружении.
    dev = request.query.get("dev")
    if dev:
        if (
            ALLOW_DEV_AUTH
            and OWNER_TELEGRAM_ID > 0
            and hmac.compare_digest(str(dev), DEV_SECRET)
        ):
            logger.warning("DEV auth used from %s", request.remote)
            return OWNER_TELEGRAM_ID
        logger.warning("Rejected DEV auth attempt (disabled) from %s", request.remote)

    return None


# --- работа с состоянием ------------------------------------------------------

async def _get_or_create(session, tid: int) -> GameState:
    res = await session.execute(select(GameState).where(GameState.telegram_id == tid))
    gs = res.scalar_one_or_none()
    if gs is None:
        gs = GameState(telegram_id=tid, name=_default_nick(tid))
        session.add(gs)
        await session.flush()
    elif not gs.name or _nick_banned(gs.name):
        gs.name = _default_nick(tid)
    return gs


def _json(data: dict, status: int = 200) -> web.Response:
    return web.json_response(data, status=status, dumps=lambda o: json.dumps(o, ensure_ascii=False))


# --- эндпоинты ----------------------------------------------------------------

async def handle_state(request: web.Request) -> web.Response:
    tid = _auth(request)
    if tid is None:
        return _json({"error": "unauthorized"}, 401)
    async with async_session() as session:
        gs = await _get_or_create(session, tid)
        snap = engine.snapshot(gs)
        await session.commit()
    return _json(snap)


FEEDBACK_DAILY_LIMIT = 3


async def handle_feedback(request: web.Request) -> web.Response:
    tid = _auth(request)
    if tid is None:
        return _json({"error": "unauthorized"}, 401)
    try:
        body = await request.json()
    except Exception:
        body = {}
    text = str(body.get("text", "")).strip()
    if len(text) < 3:
        return _json({"error": "too short"}, 400)
    text = text[:800]
    today = today_msk()
    async with async_session() as session:
        gs = await _get_or_create(session, tid)
        if gs.feedback_date != today:
            gs.feedback_date = today
            gs.feedback_count = 0
        if gs.feedback_count >= FEEDBACK_DAILY_LIMIT:
            await session.commit()
            return _json({"error": "limit", "message": "Лимит отзывов на сегодня. Спасибо!"}, 429)
        gs.feedback_count += 1
        nick = gs.name or _default_nick(tid)
        real_stored = gs.real_name or ""
        uname_stored = gs.real_username or ""
        left = FEEDBACK_DAILY_LIMIT - gs.feedback_count
        await session.commit()
    # реальный профиль: сохранённый при /start → подпись initData → тело запроса
    u = _init_user(request.headers.get("X-Telegram-Init-Data", ""))
    real = real_stored or " ".join(x for x in [u.get("first_name"), u.get("last_name")] if x).strip() \
        or str(body.get("tg_name", "")).strip()[:60]
    uname = uname_stored or u.get("username") or str(body.get("tg_username", "")).strip()[:40]
    who = real or "(имя не получено)"
    if uname:
        who += f" @{uname}"
    # отправить владельцу бота (если OWNER_TELEGRAM_ID задан)
    if OWNER_TELEGRAM_ID > 0:
        msg = (
            f"💬 Новый отзыв\n"
            f"👤 {who}\n"
            f"🆔 id {tid}\n"
            f"🏷 ник в игре: {nick}\n"
            f"━━━━━━━━━━\n{text}"
        )
        try:
            async with aiohttp.ClientSession() as cs:
                await cs.post(
                    f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                    json={"chat_id": OWNER_TELEGRAM_ID, "text": msg},
                    timeout=aiohttp.ClientTimeout(total=10),
                )
        except Exception as e:
            logger.warning("feedback send failed: %s", e)
    return _json({"ok": True, "left": left})


async def handle_reminders(request: web.Request) -> web.Response:
    tid = _auth(request)
    if tid is None:
        return _json({"error": "unauthorized"}, 401)
    try:
        body = await request.json()
    except Exception:
        body = {}
    on = bool(body.get("on", True))
    hour_raw = body.get("hour", None)
    minute_raw = body.get("minute", None)
    async with async_session() as session:
        gs = await _get_or_create(session, tid)
        gs.reminders_on = on
        if hour_raw is not None or minute_raw is not None:
            try:
                h = int(hour_raw if hour_raw is not None else getattr(gs, "reminder_hour", 19) or 19)
            except (TypeError, ValueError):
                h = 19
            try:
                m = int(minute_raw if minute_raw is not None else getattr(gs, "reminder_minute", 0) or 0)
            except (TypeError, ValueError):
                m = 0
            h, m = engine.clamp_reminder_time(h, m)
            gs.reminder_hour = h
            gs.reminder_minute = m
        snap = engine.snapshot(gs)
        await session.commit()
    return _json(snap)


async def handle_nickname(request: web.Request) -> web.Response:
    tid = _auth(request)
    if tid is None:
        return _json({"error": "unauthorized"}, 401)
    try:
        body = await request.json()
    except Exception:
        body = {}
    nick = str(body.get("nickname", "")).strip()[:20]
    if nick and _nick_banned(nick):
        return _json({"error": "bad_nickname", "message": "Такой ник нельзя"}, 400)
    async with async_session() as session:
        gs = await _get_or_create(session, tid)
        if nick:
            gs.name = nick
        snap = engine.snapshot(gs)
        await session.commit()
    return _json(snap)


async def handle_leaderboard(request: web.Request) -> web.Response:
    tid = _auth(request)
    if tid is None:
        return _json({"error": "unauthorized"}, 401)
    period = (request.rel_url.query.get("period") or "week").strip().lower()
    if period not in ("week", "season", "friends"):
        period = "week"

    async with async_session() as session:
        res = await session.execute(select(GameState))
        rows = list(res.scalars().all())
        dirty = False
        for g in rows:
            safe = _safe_nick(g.name, g.telegram_id)
            if (g.name or "") != safe:
                g.name = safe
                dirty = True
        me_gs = next((g for g in rows if g.telegram_id == tid), None)
        if dirty:
            await session.commit()

        friend_ids = engine.friend_id_set(me_gs) if me_gs else set()
        if period == "friends":
            allowed = set(friend_ids)
            allowed.add(tid)
            rows = [g for g in rows if g.telegram_id in allowed]

        def score(g):
            return engine.season_reps(g) if period == "season" else engine.weekly_reps(g)

        ranked = sorted(
            ({
                "tid": g.telegram_id,
                "name": _safe_nick(g.name, g.telegram_id),
                "reps": score(g),
                "level": g.level,
                "streak": engine.live_streak(g),
            } for g in rows),
            key=lambda x: x["reps"], reverse=True,
        )

    top = []
    my_rank = None
    for i, r in enumerate(ranked):
        r2 = {
            "rank": i + 1,
            "name": r["name"],
            "reps": r["reps"],
            "level": r["level"],
            "streak": r["streak"],
            "me": r["tid"] == tid,
        }
        if i < 20:
            top.append(r2)
        if r["tid"] == tid:
            my_rank = r2

    today = engine._today()
    season = engine.season_label(today)
    return _json({
        "period": period,
        "season": season,
        "top": top,
        "me": my_rank,
        "total": len(ranked),
        "friends_count": len(friend_ids),
        "invite_link": _bot_deep_link(f"fr_{tid}"),
    })


async def handle_attack(request: web.Request) -> web.Response:
    tid = _auth(request)
    if tid is None:
        return _json({"error": "unauthorized"}, 401)
    try:
        body = await request.json()
    except Exception:
        body = {}
    try:
        reps = int(body.get("reps", 0))
    except (TypeError, ValueError):
        return _json({"error": "bad reps"}, 400)
    if reps < 0 or reps > 500:
        return _json({"error": "bad reps"}, 400)

    async with async_session() as session:
        gs = await _get_or_create(session, tid)
        enemy_hp = None
        try:
            # ориентир — текущий враг (сколько повторов реально нужно)
            from game import content as C
            gate = C.GATES_BY_ID.get(gs.current_gate, C.GATES[0])
            if gs.enemy_index < len(gate["enemies"]):
                en = gate["enemies"][gs.enemy_index]
                enemy_hp = float(gs.enemy_hp) if gs.enemy_hp > 0 else float(
                    max(1, round(en["hp"] * (
                        C.PROGRAMS.get(gs.program, {}).get("mult", 1.0)
                    )))
                )
        except Exception:
            enemy_hp = None

        accepted, reason = anticheat.allowed_reps(tid, reps, enemy_hp=enemy_hp)
        if accepted <= 0 and reps > 0:
            snap = engine.snapshot(gs)
            snap["events"] = [{"type": "rate_limited", "reason": reason or "rate_limited"}]
            snap["error"] = reason or "rate_limited"
            await session.commit()
            return _json(snap, 429)
        snap = engine.attack(gs, accepted)
        if accepted < reps:
            snap.setdefault("events", []).append({
                "type": "reps_capped",
                "asked": reps,
                "accepted": accepted,
            })
        await session.commit()
    return _json(snap)


async def handle_gate(request: web.Request) -> web.Response:
    tid = _auth(request)
    if tid is None:
        return _json({"error": "unauthorized"}, 401)
    try:
        body = await request.json()
    except Exception:
        body = {}
    gate_id = str(body.get("gate_id", ""))
    async with async_session() as session:
        gs = await _get_or_create(session, tid)
        try:
            snap = engine.select_gate(gs, gate_id)
        except PermissionError as e:
            code = str(e) or "gate locked"
            if code == "premium_required":
                return _json({"error": "premium_required", "stars_price": PREMIUM_STARS_PRICE}, 402)
            return _json({"error": "gate locked"}, 403)
        except ValueError:
            return _json({"error": "unknown gate"}, 404)
        anticheat.note_gate_enter(tid)
        await session.commit()
    return _json(snap)


async def handle_train(request: web.Request) -> web.Response:
    tid = _auth(request)
    if tid is None:
        return _json({"error": "unauthorized"}, 401)
    try:
        body = await request.json()
    except Exception:
        body = {}
    try:
        reps = int(body.get("reps", 0))
    except (TypeError, ValueError):
        return _json({"error": "bad reps"}, 400)
    if reps < 0 or reps > 500:
        return _json({"error": "bad reps"}, 400)
    accepted, reason = anticheat.allowed_reps(tid, reps, enemy_hp=None)
    if accepted <= 0 and reps > 0:
        async with async_session() as session:
            gs = await _get_or_create(session, tid)
            snap = engine.snapshot(gs)
            snap["events"] = [{"type": "rate_limited", "reason": reason or "rate_limited"}]
            snap["error"] = reason or "rate_limited"
            await session.commit()
        return _json(snap, 429)
    async with async_session() as session:
        gs = await _get_or_create(session, tid)
        snap = engine.train(gs, accepted)
        if accepted < reps:
            snap.setdefault("events", []).append({
                "type": "reps_capped", "asked": reps, "accepted": accepted,
            })
        await session.commit()
    return _json(snap)


async def handle_customize(request: web.Request) -> web.Response:
    tid = _auth(request)
    if tid is None:
        return _json({"error": "unauthorized"}, 401)
    try:
        body = await request.json()
    except Exception:
        body = {}
    title = body.get("title")
    avatar = body.get("avatar")
    async with async_session() as session:
        gs = await _get_or_create(session, tid)
        snap = engine.customize(gs, title=title, avatar=avatar)
        await session.commit()
    return _json(snap)


async def handle_workout_done(request: web.Request) -> web.Response:
    tid = _auth(request)
    if tid is None:
        return _json({"error": "unauthorized"}, 401)
    try:
        body = await request.json()
    except Exception:
        body = {}
    key = str(body.get("exercise", ""))
    async with async_session() as session:
        gs = await _get_or_create(session, tid)
        if key not in engine.workout_day_keys(gs):
            return _json({"error": "not in today's workout"}, 400)
        snap = engine.complete_exercise(gs, key)
        await session.commit()
    return _json(snap)


async def handle_setup(request: web.Request) -> web.Response:
    tid = _auth(request)
    if tid is None:
        return _json({"error": "unauthorized"}, 401)
    try:
        body = await request.json()
    except Exception:
        body = {}
    gender = body.get("gender")
    mode = body.get("mode")
    goals = body.get("goals")
    async with async_session() as session:
        gs = await _get_or_create(session, tid)
        snap = engine.setup(gs, gender=gender, mode=mode, goals=goals)
        await session.commit()
    return _json(snap)


async def handle_program(request: web.Request) -> web.Response:
    tid = _auth(request)
    if tid is None:
        return _json({"error": "unauthorized"}, 401)
    try:
        body = await request.json()
    except Exception:
        body = {}
    program = str(body.get("program", ""))
    async with async_session() as session:
        gs = await _get_or_create(session, tid)
        snap = engine.set_program(gs, program)
        await session.commit()
    return _json(snap)


async def handle_reset(request: web.Request) -> web.Response:
    tid = _auth(request)
    if tid is None:
        return _json({"error": "unauthorized"}, 401)
    async with async_session() as session:
        gs = await _get_or_create(session, tid)
        snap = engine.reset(gs)
        await session.commit()
    return _json(snap)


async def handle_premium_invoice(request: web.Request) -> web.Response:
    """Создать invoice link (Stars) для оплаты из Mini App."""
    tid = _auth(request)
    if tid is None:
        return _json({"error": "unauthorized"}, 401)
    try:
        body = await request.json()
    except Exception:
        body = {}
    send_to_chat = bool(body.get("send_to_chat"))

    async with async_session() as session:
        gs = await _get_or_create(session, tid)
        if has_premium(gs):
            snap = engine.snapshot(gs)
            await session.commit()
            return _json({"already": True, **snap})
        await session.commit()

    bot = request.app.get("bot")
    if bot is None:
        return _json({"error": "bot unavailable"}, 503)

    from aiogram.types import LabeledPrice

    try:
        if send_to_chat:
            await bot.send_invoice(
                chat_id=tid,
                title=PREMIUM_TITLE,
                description=PREMIUM_DESCRIPTION,
                payload=PREMIUM_PAYLOAD,
                currency="XTR",
                prices=[LabeledPrice(label="Premium", amount=PREMIUM_STARS_PRICE)],
                provider_token="",
            )
            return _json({
                "sent": True,
                "stars_price": PREMIUM_STARS_PRICE,
                "title": PREMIUM_TITLE,
            })

        link = await bot.create_invoice_link(
            title=PREMIUM_TITLE,
            description=PREMIUM_DESCRIPTION,
            payload=PREMIUM_PAYLOAD,
            currency="XTR",
            prices=[LabeledPrice(label="Premium", amount=PREMIUM_STARS_PRICE)],
            provider_token="",
        )
    except Exception as e:
        logger.exception("premium invoice failed")
        return _json({"error": "invoice_failed", "detail": str(e)[:200]}, 502)

    return _json({
        "invoice_url": link,
        "stars_price": PREMIUM_STARS_PRICE,
        "title": PREMIUM_TITLE,
    })


async def handle_premium_confirm(request: web.Request) -> web.Response:
    """После openInvoice(status=paid) — обновить state (бот тоже пишет в БД)."""
    tid = _auth(request)
    if tid is None:
        return _json({"error": "unauthorized"}, 401)
    # SuccessfulPayment приходит боту; здесь просто отдаём свежий state.
    # Если бот уже выдал premium — увидим сразу. Иначе фронт может повторить.
    async with async_session() as session:
        gs = await _get_or_create(session, tid)
        snap = engine.snapshot(gs)
        await session.commit()
    return _json(snap)


async def handle_donate_invoice(request: web.Request) -> web.Response:
    """Создать invoice link (Stars) на произвольную сумму пожертвования."""
    tid = _auth(request)
    if tid is None:
        return _json({"error": "unauthorized"}, 401)

    try:
        body = await request.json()
    except Exception:
        body = {}
    try:
        amount = int(body.get("amount") or 0)
    except (TypeError, ValueError):
        amount = 0
    if amount < DONATE_MIN_STARS or amount > DONATE_MAX_STARS:
        return _json({
            "error": "bad_amount",
            "min": DONATE_MIN_STARS,
            "max": DONATE_MAX_STARS,
        }, 400)

    bot = request.app.get("bot")
    if bot is None:
        return _json({"error": "bot unavailable"}, 503)

    from aiogram.types import LabeledPrice
    from handlers.premium import donate_payload

    payload = donate_payload(amount)
    send_to_chat = bool(body.get("send_to_chat"))

    try:
        if send_to_chat:
            await bot.send_invoice(
                chat_id=tid,
                title=DONATE_TITLE,
                description=DONATE_DESCRIPTION,
                payload=payload,
                currency="XTR",
                prices=[LabeledPrice(label="Пожертвование", amount=amount)],
                provider_token="",
            )
            return _json({
                "sent": True,
                "amount": amount,
                "title": DONATE_TITLE,
            })

        link = await bot.create_invoice_link(
            title=DONATE_TITLE,
            description=DONATE_DESCRIPTION,
            payload=payload,
            currency="XTR",
            prices=[LabeledPrice(label="Пожертвование", amount=amount)],
            provider_token="",
        )
    except Exception as e:
        logger.exception("donate invoice failed")
        return _json({"error": "invoice_failed", "detail": str(e)[:200]}, 502)

    return _json({
        "invoice_url": link,
        "amount": amount,
        "title": DONATE_TITLE,
        "min": DONATE_MIN_STARS,
        "max": DONATE_MAX_STARS,
    })


# --- PvP арена ----------------------------------------------------------------

async def _notify_duel_invite(bot, challenger_tid: int, opponent_tid: int, duel_id: int, ex_name: str) -> None:
    if bot is None:
        return
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
    from game.login_token import webapp_url_for

    nick = f"Игрок {str(challenger_tid)[-4:]}"
    try:
        async with async_session() as session:
            gs = await _get_or_create(session, challenger_tid)
            nick = _safe_nick(gs.name, challenger_tid)
            await session.commit()
    except Exception:
        pass

    url = webapp_url_for(opponent_tid, duel=duel_id)
    deep = _bot_deep_link(f"du_{duel_id}")
    rows = [[InlineKeyboardButton(text="⚔️ Принять бой", web_app=WebAppInfo(url=url))]]
    if deep:
        rows.append([InlineKeyboardButton(text="Открыть в боте", url=deep)])
    kb = InlineKeyboardMarkup(inline_keyboard=rows)
    text = (
        f"⚔️ <b>{nick}</b> вызывает тебя на бой!\n\n"
        f"Упражнение: <b>{ex_name}</b>\n"
        f"60 секунд — кто сделает больше повторов.\n\n"
        f"Жми «Принять бой» 👇"
    )
    try:
        await bot.send_message(opponent_tid, text, reply_markup=kb)
    except Exception:
        logger.exception("duel invite notify failed to=%s", opponent_tid)


async def _notify_duel_matched(bot, tid: int, duel_id: int, opp_name: str, ex_name: str) -> None:
    if bot is None:
        return
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
    from game.login_token import webapp_url_for

    url = webapp_url_for(tid, duel=duel_id)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⚔️ В бой!", web_app=WebAppInfo(url=url))],
    ])
    text = (
        f"🎲 Соперник найден: <b>{opp_name}</b>\n"
        f"Упражнение: <b>{ex_name}</b>\n\n"
        f"Жми «В бой!» — откроется лобби, там кнопка <b>Готов!</b>"
    )
    try:
        await bot.send_message(tid, text, reply_markup=kb)
    except Exception:
        logger.exception("duel matched notify failed to=%s", tid)


async def handle_duel_meta(request: web.Request) -> web.Response:
    tid = _auth(request)
    if tid is None:
        return _json({"error": "unauthorized"}, 401)
    from game import duel as D

    async with async_session() as session:
        friends = await D.friends_list(session, tid)
        invites_raw = await D.incoming_invites(session, tid)
        invites = []
        for d in invites_raw:
            invites.append(await D.enrich(session, d, tid))
        active = await D.find_active_for(session, tid)
        active_view = await D.enrich(session, active, tid) if active else None
        gs = await _get_or_create(session, tid)
        await session.commit()
    return _json({
        "exercises": D.duel_exercises(),
        "friends": friends,
        "invites": invites,
        "active": active_view,
        "stats": {
            "wins": int(getattr(gs, "duel_wins", 0) or 0),
            "losses": int(getattr(gs, "duel_losses", 0) or 0),
            "draws": int(getattr(gs, "duel_draws", 0) or 0),
        },
        "invite_friend_link": _bot_deep_link(f"fr_{tid}"),
        "duration_sec": D.DUEL_DURATION_SEC,
    })


async def handle_duel_queue(request: web.Request) -> web.Response:
    tid = _auth(request)
    if tid is None:
        return _json({"error": "unauthorized"}, 401)
    try:
        body = await request.json()
    except Exception:
        body = {}
    exercise = body.get("exercise")
    from game import duel as D

    async with async_session() as session:
        d, newly = await D.queue_random(session, tid, exercise)
        view = await D.enrich(session, d, tid)
        await session.commit()

    bot = request.app.get("bot")
    if newly and d.p2_tid:
        ex_name = view["exercise"]["name"]
        opp = view.get("opponent") or {}
        await _notify_duel_matched(bot, tid, d.id, opp.get("name") or "Соперник", ex_name)
        other = d.p1_tid if d.p2_tid == tid else d.p2_tid
        if other:
            await _notify_duel_matched(bot, other, d.id, view["me"]["name"], ex_name)

    return _json(view)


async def handle_duel_cancel_queue(request: web.Request) -> web.Response:
    tid = _auth(request)
    if tid is None:
        return _json({"error": "unauthorized"}, 401)
    from game import duel as D
    async with async_session() as session:
        ok = await D.cancel_queue(session, tid)
        await session.commit()
    return _json({"ok": ok})


async def handle_duel_challenge(request: web.Request) -> web.Response:
    tid = _auth(request)
    if tid is None:
        return _json({"error": "unauthorized"}, 401)
    try:
        body = await request.json()
    except Exception:
        body = {}
    try:
        friend_tid = int(body.get("friend_tid") or 0)
    except (TypeError, ValueError):
        return _json({"error": "bad_friend"}, 400)
    exercise = body.get("exercise")
    from game import duel as D

    async with async_session() as session:
        try:
            d = await D.challenge_friend(session, tid, friend_tid, exercise)
        except ValueError as e:
            code = str(e)
            status = 403 if code == "not_friend" else 400
            return _json({"error": code}, status)
        view = await D.enrich(session, d, tid)
        await session.commit()

    view["invite_link"] = _bot_deep_link(f"du_{d.id}")
    await _notify_duel_invite(
        request.app.get("bot"), tid, friend_tid, d.id, view["exercise"]["name"]
    )
    return _json(view)


async def handle_duel_get(request: web.Request) -> web.Response:
    tid = _auth(request)
    if tid is None:
        return _json({"error": "unauthorized"}, 401)
    try:
        duel_id = int(request.match_info["duel_id"])
    except (TypeError, ValueError):
        return _json({"error": "bad_id"}, 400)
    from game import duel as D
    async with async_session() as session:
        d = await D.get_duel(session, duel_id)
        if not d:
            return _json({"error": "not_found"}, 404)
        if tid not in (d.p1_tid, d.p2_tid):
            return _json({"error": "forbidden"}, 403)
        view = await D.enrich(session, d, tid)
        await session.commit()
    return _json(view)


async def handle_duel_accept(request: web.Request) -> web.Response:
    tid = _auth(request)
    if tid is None:
        return _json({"error": "unauthorized"}, 401)
    try:
        duel_id = int(request.match_info["duel_id"])
    except (TypeError, ValueError):
        return _json({"error": "bad_id"}, 400)
    from game import duel as D
    async with async_session() as session:
        try:
            d = await D.accept_duel(session, tid, duel_id)
        except ValueError as e:
            return _json({"error": str(e)}, 400)
        view = await D.enrich(session, d, tid)
        await session.commit()

    bot = request.app.get("bot")
    await _notify_duel_matched(bot, d.p1_tid, d.id, view["me"]["name"], view["exercise"]["name"])
    return _json(view)


async def handle_duel_decline(request: web.Request) -> web.Response:
    tid = _auth(request)
    if tid is None:
        return _json({"error": "unauthorized"}, 401)
    try:
        duel_id = int(request.match_info["duel_id"])
    except (TypeError, ValueError):
        return _json({"error": "bad_id"}, 400)
    from game import duel as D
    async with async_session() as session:
        try:
            d = await D.decline_duel(session, tid, duel_id)
        except ValueError as e:
            return _json({"error": str(e)}, 400)
        view = await D.enrich(session, d, tid)
        await session.commit()
    return _json(view)


async def handle_duel_ready(request: web.Request) -> web.Response:
    tid = _auth(request)
    if tid is None:
        return _json({"error": "unauthorized"}, 401)
    try:
        duel_id = int(request.match_info["duel_id"])
    except (TypeError, ValueError):
        return _json({"error": "bad_id"}, 400)
    from game import duel as D
    async with async_session() as session:
        try:
            d = await D.set_ready(session, tid, duel_id)
        except ValueError as e:
            return _json({"error": str(e)}, 400)
        view = await D.enrich(session, d, tid)
        await session.commit()
    return _json(view)


async def handle_duel_reps(request: web.Request) -> web.Response:
    tid = _auth(request)
    if tid is None:
        return _json({"error": "unauthorized"}, 401)
    try:
        duel_id = int(request.match_info["duel_id"])
    except (TypeError, ValueError):
        return _json({"error": "bad_id"}, 400)
    try:
        body = await request.json()
    except Exception:
        body = {}
    try:
        reps = int(body.get("reps", 0))
    except (TypeError, ValueError):
        return _json({"error": "bad reps"}, 400)
    from game import duel as D
    async with async_session() as session:
        try:
            d = await D.set_reps(session, tid, duel_id, reps)
        except ValueError as e:
            return _json({"error": str(e)}, 400)
        view = await D.enrich(session, d, tid)
        await session.commit()
    return _json(view)


async def handle_duel_finish(request: web.Request) -> web.Response:
    tid = _auth(request)
    if tid is None:
        return _json({"error": "unauthorized"}, 401)
    try:
        duel_id = int(request.match_info["duel_id"])
    except (TypeError, ValueError):
        return _json({"error": "bad_id"}, 400)
    try:
        body = await request.json()
    except Exception:
        body = {}
    try:
        reps = int(body.get("reps", 0))
    except (TypeError, ValueError):
        reps = 0
    from game import duel as D
    async with async_session() as session:
        try:
            if reps > 0:
                await D.set_reps(session, tid, duel_id, reps)
            d = await D.finish_early(session, tid, duel_id)
        except ValueError as e:
            return _json({"error": str(e)}, 400)
        view = await D.enrich(session, d, tid)
        await session.commit()
    return _json(view)


async def handle_duel_forfeit(request: web.Request) -> web.Response:
    tid = _auth(request)
    if tid is None:
        return _json({"error": "unauthorized"}, 401)
    try:
        duel_id = int(request.match_info["duel_id"])
    except (TypeError, ValueError):
        return _json({"error": "bad_id"}, 400)
    from game import duel as D
    async with async_session() as session:
        try:
            d = await D.forfeit(session, tid, duel_id)
        except ValueError as e:
            return _json({"error": str(e)}, 400)
        view = await D.enrich(session, d, tid)
        await session.commit()
    return _json(view)


async def handle_health(request: web.Request) -> web.Response:
    return web.Response(text="ok")


def build_app() -> web.Application:
    app = web.Application()
    app.router.add_get("/api/health", handle_health)
    app.router.add_get("/api/state", handle_state)
    app.router.add_get("/api/leaderboard", handle_leaderboard)
    app.router.add_post("/api/attack", handle_attack)
    app.router.add_post("/api/train", handle_train)
    app.router.add_post("/api/gate", handle_gate)
    app.router.add_post("/api/customize", handle_customize)
    app.router.add_post("/api/nickname", handle_nickname)
    app.router.add_post("/api/reminders", handle_reminders)
    app.router.add_post("/api/feedback", handle_feedback)
    app.router.add_post("/api/setup", handle_setup)
    app.router.add_post("/api/workout_done", handle_workout_done)
    app.router.add_post("/api/program", handle_program)
    app.router.add_post("/api/reset", handle_reset)
    app.router.add_post("/api/premium/invoice", handle_premium_invoice)
    app.router.add_post("/api/premium/confirm", handle_premium_confirm)
    app.router.add_post("/api/donate/invoice", handle_donate_invoice)
    app.router.add_get("/api/duel/meta", handle_duel_meta)
    app.router.add_post("/api/duel/queue", handle_duel_queue)
    app.router.add_post("/api/duel/cancel", handle_duel_cancel_queue)
    app.router.add_post("/api/duel/challenge", handle_duel_challenge)
    app.router.add_get(r"/api/duel/{duel_id:\d+}", handle_duel_get)
    app.router.add_post(r"/api/duel/{duel_id:\d+}/accept", handle_duel_accept)
    app.router.add_post(r"/api/duel/{duel_id:\d+}/decline", handle_duel_decline)
    app.router.add_post(r"/api/duel/{duel_id:\d+}/ready", handle_duel_ready)
    app.router.add_post(r"/api/duel/{duel_id:\d+}/reps", handle_duel_reps)
    app.router.add_post(r"/api/duel/{duel_id:\d+}/finish", handle_duel_finish)
    app.router.add_post(r"/api/duel/{duel_id:\d+}/forfeit", handle_duel_forfeit)
    return app


async def start_api(bot=None) -> web.AppRunner:
    app = build_app()
    if bot is not None:
        app["bot"] = bot
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, API_HOST, API_PORT)
    await site.start()
    logger.info("You vs You API запущен на http://%s:%s", API_HOST, API_PORT)
    return runner
