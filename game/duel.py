"""PvP дуэли 1 на 1 — случайный соперник или вызов друга.

Правила: одно упражнение, 60 секунд, побеждает у кого больше повторов
(для hold — секунд). Оба онлайн; статус тянется поллингом.
"""

from __future__ import annotations

import random
import secrets
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import BigInteger, Boolean, DateTime, Integer, String, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from game import content as C
from game import engine
from game.state import GameState
from models import Base

# --- константы ----------------------------------------------------------------

DUEL_DURATION_SEC = 60
QUEUE_TTL_SEC = 180
INVITE_TTL_SEC = 600
MATCHED_TTL_SEC = 180
COUNTDOWN_SEC = 3

# античит: максимум повторов в секунду (с запасом на камеру)
MAX_REPS_PER_SEC = 4.0
MAX_REPS_BURST = 10

WIN_XP = 45
LOSE_XP = 18
DRAW_XP = 28

# Честный пул для арены (камера + ручной счёт ок)
DUEL_EXERCISE_KEYS = (
    "pushup",
    "squat",
    "situp",
    "crunch",
    "highknees",
    "mountainclimber",
    "burpee",
    "lunge",
    "glutebridge",
    "plank",
    "jumpsquat",
    "legraise",
)


def duel_exercises() -> list[dict]:
    out = []
    for k in DUEL_EXERCISE_KEYS:
        ex = C.EXERCISES.get(k)
        if not ex:
            continue
        out.append({
            "key": k,
            "name": ex["name"],
            "icon": ex["icon"],
            "type": ex["type"],
            "mode": ex.get("mode", "reps"),
            "detector": ex["detector"],
            "how": ex.get("how", ""),
            "tip": ex.get("tip", ""),
        })
    return out


def _pick_exercise(key: str | None) -> str:
    if key and key in C.EXERCISES and key in DUEL_EXERCISE_KEYS:
        return key
    return random.choice(list(DUEL_EXERCISE_KEYS))


def _now() -> datetime:
    return datetime.utcnow()


class Duel(Base):
    __tablename__ = "duels"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(16), unique=True, nullable=False)

    mode: Mapped[str] = mapped_column(String(16), default="random")  # random|friend
    status: Mapped[str] = mapped_column(String(16), default="waiting")
    # waiting | matched | active | finished | cancelled | expired

    exercise: Mapped[str] = mapped_column(String(32), default="pushup")
    duration_sec: Mapped[int] = mapped_column(Integer, default=DUEL_DURATION_SEC)

    p1_tid: Mapped[int] = mapped_column(BigInteger, nullable=False)
    p2_tid: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)

    p1_reps: Mapped[int] = mapped_column(Integer, default=0)
    p2_reps: Mapped[int] = mapped_column(Integer, default=0)
    p1_ready: Mapped[bool] = mapped_column(Boolean, default=False)
    p2_ready: Mapped[bool] = mapped_column(Boolean, default=False)
    p1_finished: Mapped[bool] = mapped_column(Boolean, default=False)
    p2_finished: Mapped[bool] = mapped_column(Boolean, default=False)

    # None=не завершён, 0=ничья, иначе telegram_id победителя
    winner_tid: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    p1_xp: Mapped[int] = mapped_column(Integer, default=0)
    p2_xp: Mapped[int] = mapped_column(Integer, default=0)
    rewarded: Mapped[bool] = mapped_column(Boolean, default=False)

    starts_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    ends_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


def _new_code() -> str:
    return secrets.token_hex(4)


def _nick(gs: GameState | None, tid: int) -> str:
    if gs and (gs.name or "").strip():
        return (gs.name or "").strip()[:20]
    return "Охотник-" + str(abs(int(tid)))[-4:]


async def _gs(session: AsyncSession, tid: int) -> GameState | None:
    res = await session.execute(select(GameState).where(GameState.telegram_id == tid))
    return res.scalar_one_or_none()


def exercise_view(key: str) -> dict:
    if not key or key == "any" or key not in C.EXERCISES:
        return {
            "key": "any",
            "name": "Случайное",
            "icon": "🎲",
            "type": "reps",
            "mode": "reps",
            "detector": {"kind": "manual"},
            "how": "Упражнение выберется при матче",
            "tip": "",
        }
    ex = C.EXERCISES[key]
    return {
        "key": key,
        "name": ex["name"],
        "icon": ex["icon"],
        "type": ex["type"],
        "mode": ex.get("mode", "reps"),
        "detector": ex["detector"],
        "how": ex.get("how", ""),
        "tip": ex.get("tip", ""),
    }


def public_duel(d: Duel, me: int, p1: GameState | None = None, p2: GameState | None = None) -> dict:
    """Сериализовать дуэль для клиента."""
    now = _now()
    server_now = int(now.timestamp())
    starts = int(d.starts_at.timestamp()) if d.starts_at else None
    ends = int(d.ends_at.timestamp()) if d.ends_at else None

    i_am_p1 = d.p1_tid == me
    my_reps = d.p1_reps if i_am_p1 else d.p2_reps
    opp_reps = d.p2_reps if i_am_p1 else d.p1_reps
    my_ready = d.p1_ready if i_am_p1 else d.p2_ready
    opp_ready = d.p2_ready if i_am_p1 else d.p1_ready
    my_finished = d.p1_finished if i_am_p1 else d.p2_finished
    my_xp = d.p1_xp if i_am_p1 else d.p2_xp

    opp_tid = d.p2_tid if i_am_p1 else d.p1_tid
    opp_gs = (p2 if i_am_p1 else p1) if opp_tid else None
    me_gs = p1 if i_am_p1 else p2

    result = None
    if d.status == "finished":
        if d.winner_tid == 0:
            result = "draw"
        elif d.winner_tid == me:
            result = "win"
        else:
            result = "lose"

    return {
        "id": d.id,
        "code": d.code,
        "mode": d.mode,
        "status": d.status,
        "exercise": exercise_view(d.exercise),
        "duration_sec": d.duration_sec,
        "server_now": server_now,
        "starts_at": starts,
        "ends_at": ends,
        "countdown_sec": COUNTDOWN_SEC,
        "me": {
            "tid": me,
            "name": _nick(me_gs, me),
            "reps": my_reps,
            "ready": bool(my_ready),
            "finished": bool(my_finished),
            "xp": my_xp,
            "avatar": (me_gs.avatar_emoji if me_gs else "🧑") or "🧑",
        },
        "opponent": (
            {
                "tid": opp_tid,
                "name": _nick(opp_gs, opp_tid),
                "reps": opp_reps,
                "ready": bool(opp_ready),
                "finished": bool(d.p2_finished if i_am_p1 else d.p1_finished),
                "avatar": (opp_gs.avatar_emoji if opp_gs else "🧑") or "🧑",
            }
            if opp_tid
            else None
        ),
        "winner_tid": d.winner_tid,
        "result": result,
        "i_am_p1": i_am_p1,
        "invite_link": None,  # заполняет API при friend
    }


async def expire_stale(session: AsyncSession) -> None:
    """Пометить протухшие waiting/matched как expired."""
    now = _now()
    res = await session.execute(
        select(Duel).where(Duel.status.in_(("waiting", "matched")))
    )
    for d in res.scalars().all():
        age = (now - (d.created_at or now)).total_seconds()
        if d.status == "matched":
            # matched: считаем от updated_at (момент матча/инвайта accept)
            age = (now - (d.updated_at or d.created_at or now)).total_seconds()
            ttl = MATCHED_TTL_SEC
        elif d.mode == "random":
            ttl = QUEUE_TTL_SEC
        else:
            ttl = INVITE_TTL_SEC
        if age > ttl:
            d.status = "expired"
            d.updated_at = now


async def find_active_for(session: AsyncSession, tid: int) -> Duel | None:
    """Активная / ожидающая дуэль игрока."""
    await expire_stale(session)
    res = await session.execute(
        select(Duel)
        .where(
            Duel.status.in_(("waiting", "matched", "active")),
            (Duel.p1_tid == tid) | (Duel.p2_tid == tid),
        )
        .order_by(Duel.id.desc())
    )
    return res.scalars().first()


async def get_duel(session: AsyncSession, duel_id: int) -> Duel | None:
    res = await session.execute(select(Duel).where(Duel.id == int(duel_id)))
    return res.scalar_one_or_none()


async def maybe_finish(session: AsyncSession, d: Duel) -> bool:
    """Если время вышло или оба закончили — завершить и выдать XP. True если только что завершили."""
    if d.status != "active":
        return False
    now = _now()
    time_up = bool(d.ends_at and now >= d.ends_at)
    both_done = bool(d.p1_finished and d.p2_finished)
    if not time_up and not both_done:
        return False
    await _settle(session, d)
    return True


async def _settle(session: AsyncSession, d: Duel, force_winner: int | None = None) -> None:
    if d.status == "finished" and d.rewarded:
        return
    now = _now()
    d.status = "finished"
    d.updated_at = now
    if force_winner is not None:
        # 0 = ничья, иначе tid победителя (сдача)
        d.winner_tid = int(force_winner)
    elif d.p1_reps > d.p2_reps:
        d.winner_tid = d.p1_tid
    elif d.p2_reps > d.p1_reps:
        d.winner_tid = d.p2_tid
    else:
        d.winner_tid = 0

    if d.rewarded:
        return
    d.rewarded = True

    p1 = await _gs(session, d.p1_tid)
    p2 = await _gs(session, d.p2_tid) if d.p2_tid else None

    def _reward(gs: GameState | None, reps: int, outcome: str) -> int:
        if gs is None:
            return 0
        if outcome == "win":
            xp = WIN_XP
            gs.duel_wins = int(getattr(gs, "duel_wins", 0) or 0) + 1
        elif outcome == "lose":
            xp = LOSE_XP
            gs.duel_losses = int(getattr(gs, "duel_losses", 0) or 0) + 1
        else:
            xp = DRAW_XP
            gs.duel_draws = int(getattr(gs, "duel_draws", 0) or 0) + 1
        # повторы в общий прогресс + стрик/квесты
        effective = max(0, int(reps))
        if effective > 0:
            gs.total_reps += effective
            events: list[dict] = []
            engine._bump_daily(gs, events, reps=effective)  # noqa: SLF001
        events2: list[dict] = []
        engine._gain_xp(gs, xp, events2)  # noqa: SLF001
        gs.updated_at = now
        return xp

    if d.winner_tid == 0:
        d.p1_xp = _reward(p1, d.p1_reps, "draw")
        d.p2_xp = _reward(p2, d.p2_reps, "draw")
    elif d.winner_tid == d.p1_tid:
        d.p1_xp = _reward(p1, d.p1_reps, "win")
        d.p2_xp = _reward(p2, d.p2_reps, "lose")
    else:
        d.p1_xp = _reward(p1, d.p1_reps, "lose")
        d.p2_xp = _reward(p2, d.p2_reps, "win")


async def queue_random(session: AsyncSession, tid: int, exercise: str | None) -> tuple[Duel, bool]:
    """Встать в очередь / сматчиться. Возвращает (duel, newly_matched)."""
    existing = await find_active_for(session, tid)
    if existing:
        await maybe_finish(session, existing)
        if existing.status in ("waiting", "matched", "active"):
            return existing, False

    await expire_stale(session)
    want = (exercise or "").strip() or "any"
    if want != "any" and want not in DUEL_EXERCISE_KEYS:
        want = "any"

    # Ищем waiting random без нас
    res = await session.execute(
        select(Duel)
        .where(
            Duel.status == "waiting",
            Duel.mode == "random",
            Duel.p2_tid.is_(None),
            Duel.p1_tid != tid,
        )
        .order_by(Duel.id.asc())
    )
    candidates = list(res.scalars().all())
    match = None
    for c in candidates:
        age = (_now() - (c.created_at or _now())).total_seconds()
        if age > QUEUE_TTL_SEC:
            c.status = "expired"
            continue
        c_ex = c.exercise or "any"
        if want != "any" and c_ex != "any" and want != c_ex:
            continue
        match = c
        break

    if match:
        # зафиксировать упражнение
        if match.exercise in ("", "any") or match.exercise not in DUEL_EXERCISE_KEYS:
            match.exercise = _pick_exercise(None if want == "any" else want)
        elif want != "any" and match.exercise == "any":
            match.exercise = want
        match.p2_tid = tid
        match.status = "matched"
        match.p1_ready = False
        match.p2_ready = False
        match.updated_at = _now()
        return match, True

    d = Duel(
        code=_new_code(),
        mode="random",
        status="waiting",
        exercise="any" if want == "any" else want,
        duration_sec=DUEL_DURATION_SEC,
        p1_tid=tid,
        created_at=_now(),
        updated_at=_now(),
    )
    session.add(d)
    await session.flush()
    return d, False


async def cancel_queue(session: AsyncSession, tid: int) -> bool:
    d = await find_active_for(session, tid)
    if not d:
        return False
    if d.status == "waiting" and d.p1_tid == tid and d.p2_tid is None:
        d.status = "cancelled"
        d.updated_at = _now()
        return True
    if d.status in ("waiting", "matched") and (d.p1_tid == tid or d.p2_tid == tid):
        d.status = "cancelled"
        d.updated_at = _now()
        return True
    return False


async def challenge_friend(
    session: AsyncSession, tid: int, friend_tid: int, exercise: str | None
) -> Duel:
    if friend_tid == tid:
        raise ValueError("self")
    me = await _gs(session, tid)
    if me is None:
        raise ValueError("no_state")
    friends = engine.friend_id_set(me)
    if friend_tid not in friends:
        # разрешаем вызов и без дружбы — потом подружим при accept? лучше требовать друзей
        raise ValueError("not_friend")

    existing = await find_active_for(session, tid)
    if existing and existing.status in ("waiting", "matched", "active"):
        raise ValueError("busy")

    other_busy = await find_active_for(session, friend_tid)
    if other_busy and other_busy.status in ("matched", "active"):
        raise ValueError("opponent_busy")

    ex = _pick_exercise(exercise)
    d = Duel(
        code=_new_code(),
        mode="friend",
        status="waiting",
        exercise=ex,
        duration_sec=DUEL_DURATION_SEC,
        p1_tid=tid,
        p2_tid=friend_tid,
        created_at=_now(),
        updated_at=_now(),
    )
    session.add(d)
    await session.flush()
    return d


async def accept_duel(session: AsyncSession, tid: int, duel_id: int) -> Duel:
    d = await get_duel(session, duel_id)
    if not d:
        raise ValueError("not_found")
    if d.status == "expired" or (
        d.mode == "friend"
        and (_now() - (d.created_at or _now())).total_seconds() > INVITE_TTL_SEC
    ):
        d.status = "expired"
        raise ValueError("expired")
    if d.status != "waiting":
        raise ValueError("bad_status")
    if d.p2_tid != tid:
        raise ValueError("not_invitee")

    # снять ВСЕ другие очереди/матчи приглашённого
    res_o = await session.execute(
        select(Duel).where(
            Duel.status.in_(("waiting", "matched")),
            (Duel.p1_tid == tid) | (Duel.p2_tid == tid),
            Duel.id != d.id,
        )
    )
    for other in res_o.scalars().all():
        other.status = "cancelled"
        other.updated_at = _now()

    d.status = "matched"
    d.updated_at = _now()
    return d


async def decline_duel(session: AsyncSession, tid: int, duel_id: int) -> Duel:
    d = await get_duel(session, duel_id)
    if not d:
        raise ValueError("not_found")
    if d.p2_tid != tid and d.p1_tid != tid:
        raise ValueError("forbidden")
    if d.status not in ("waiting", "matched"):
        raise ValueError("bad_status")
    d.status = "cancelled"
    d.updated_at = _now()
    return d


async def set_ready(session: AsyncSession, tid: int, duel_id: int) -> Duel:
    d = await get_duel(session, duel_id)
    if not d:
        raise ValueError("not_found")
    if d.status not in ("matched", "active"):
        raise ValueError("bad_status")
    if tid == d.p1_tid:
        d.p1_ready = True
    elif tid == d.p2_tid:
        d.p2_ready = True
    else:
        raise ValueError("forbidden")

    if d.status == "matched" and d.p1_ready and d.p2_ready and d.p2_tid:
        now = _now()
        d.status = "active"
        d.starts_at = now + timedelta(seconds=COUNTDOWN_SEC)
        d.ends_at = d.starts_at + timedelta(seconds=d.duration_sec)
    d.updated_at = _now()
    return d


async def set_reps(session: AsyncSession, tid: int, duel_id: int, reps: int) -> Duel:
    d = await get_duel(session, duel_id)
    if not d:
        raise ValueError("not_found")
    await maybe_finish(session, d)
    if d.status != "active":
        return d
    now = _now()
    if d.starts_at and now < d.starts_at:
        return d  # ещё отсчёт — не принимаем
    if d.ends_at and now >= d.ends_at:
        await maybe_finish(session, d)
        return d

    reps = max(0, min(int(reps), 800))
    # античит: не больше, чем физически успеть с начала боя
    if d.starts_at:
        elapsed = max(0.0, (now - d.starts_at).total_seconds())
        cap = int(elapsed * MAX_REPS_PER_SEC) + MAX_REPS_BURST
        reps = min(reps, cap)

    if tid == d.p1_tid:
        if d.p1_finished:
            return d
        if reps >= d.p1_reps:
            d.p1_reps = reps
    elif tid == d.p2_tid:
        if d.p2_finished:
            return d
        if reps >= d.p2_reps:
            d.p2_reps = reps
    else:
        raise ValueError("forbidden")
    d.updated_at = now
    await maybe_finish(session, d)
    return d


async def finish_early(session: AsyncSession, tid: int, duel_id: int) -> Duel:
    """Игрок закончил раньше (или сдался по таймеру клиента)."""
    d = await get_duel(session, duel_id)
    if not d:
        raise ValueError("not_found")
    if d.status != "active":
        await maybe_finish(session, d)
        return d
    if tid == d.p1_tid:
        d.p1_finished = True
    elif tid == d.p2_tid:
        d.p2_finished = True
    else:
        raise ValueError("forbidden")
    d.updated_at = _now()
    await maybe_finish(session, d)
    return d


async def forfeit(session: AsyncSession, tid: int, duel_id: int) -> Duel:
    d = await get_duel(session, duel_id)
    if not d:
        raise ValueError("not_found")
    if tid not in (d.p1_tid, d.p2_tid):
        raise ValueError("forbidden")
    if d.status in ("finished", "cancelled", "expired"):
        return d

    now = _now()
    # до старта / в лобби — просто отмена, без поражения в статистике
    if d.status in ("waiting", "matched") or (
        d.status == "active" and d.starts_at and now < d.starts_at
    ):
        d.status = "cancelled"
        d.updated_at = now
        return d

    if d.status == "active":
        # сдача: соперник побеждает (даже при 0:0)
        opp = d.p2_tid if tid == d.p1_tid else d.p1_tid
        d.p1_finished = True
        d.p2_finished = True
        d.updated_at = now
        await _settle(session, d, force_winner=(opp or 0))
        return d

    d.status = "cancelled"
    d.updated_at = now
    return d


async def enrich(session: AsyncSession, d: Duel, me: int) -> dict:
    await maybe_finish(session, d)
    p1 = await _gs(session, d.p1_tid)
    p2 = await _gs(session, d.p2_tid) if d.p2_tid else None
    return public_duel(d, me, p1, p2)


async def friends_list(session: AsyncSession, tid: int) -> list[dict]:
    me = await _gs(session, tid)
    if not me:
        return []
    ids = sorted(engine.friend_id_set(me))
    if not ids:
        return []
    res = await session.execute(select(GameState).where(GameState.telegram_id.in_(ids)))
    rows = {g.telegram_id: g for g in res.scalars().all()}
    out = []
    for fid in ids:
        g = rows.get(fid)
        busy = await find_active_for(session, fid)
        out.append({
            "tid": fid,
            "name": _nick(g, fid),
            "avatar": (g.avatar_emoji if g else "🧑") or "🧑",
            "level": g.level if g else 1,
            "busy": bool(busy and busy.status in ("matched", "active")),
        })
    return out


async def incoming_invites(session: AsyncSession, tid: int) -> list[Duel]:
    await expire_stale(session)
    res = await session.execute(
        select(Duel)
        .where(
            Duel.mode == "friend",
            Duel.status == "waiting",
            Duel.p2_tid == tid,
        )
        .order_by(Duel.id.desc())
    )
    return list(res.scalars().all())
