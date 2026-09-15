"""Античит: сервер не доверяет клиентским reps без лимитов."""

from __future__ import annotations

import time
from collections import defaultdict, deque

# Жёсткий потолок на один запрос (один враг ≈ до ~30 HP даже на pro)
MAX_REPS_PER_REQUEST = 40

# Физический потолок: даже «высокие колени» редко > 2.5 повт/сек долго
MAX_REPS_PER_MINUTE = 100
MAX_REPS_PER_10S = 25

# Мин. интервал на повтор (мс) — совпадает с клиентским MIN_MS≈380, чуть мягче
MIN_MS_PER_REP = 280

# Скользящее окно по tid: timestamps каждого засчитанного повтора
_rep_events: dict[int, deque[float]] = defaultdict(deque)
_last_attack_at: dict[int, float] = {}


def _prune(tid: int, now: float) -> deque[float]:
    q = _rep_events[tid]
    while q and now - q[0] > 60.0:
        q.popleft()
    return q


def allowed_reps(tid: int, requested: int, *, enemy_hp: float | None = None) -> tuple[int, str | None]:
    """Сколько reps реально принять. (n, reason|None)."""
    try:
        req = int(requested)
    except (TypeError, ValueError):
        return 0, "bad_reps"
    if req <= 0:
        return 0, None

    # потолок на запрос: не больше HP текущего врага + небольшой запас
    cap = MAX_REPS_PER_REQUEST
    if enemy_hp is not None and enemy_hp > 0:
        cap = min(cap, max(8, int(enemy_hp) + 3))
    req = min(req, cap)

    now = time.time()
    q = _prune(tid, now)

    # лимит по минутной / 10-секундной частоте
    in_10 = sum(1 for t in q if now - t <= 10.0)
    room_10 = max(0, MAX_REPS_PER_10S - in_10)
    room_60 = max(0, MAX_REPS_PER_MINUTE - len(q))
    room = min(room_10, room_60)
    if room <= 0:
        return 0, "rate_limited"

    # учёт времени с прошлого пакета
    last = _last_attack_at.get(tid)
    if last is not None:
        dt_ms = (now - last) * 1000.0
        by_time = max(1, int(dt_ms / MIN_MS_PER_REP) + 2)  # +2 допуск на сеть
        req = min(req, by_time)

    req = min(req, room)
    if req <= 0:
        return 0, "rate_limited"

    for _ in range(req):
        q.append(now)
    _last_attack_at[tid] = now
    return req, None


def note_gate_enter(tid: int) -> None:
    """Сброс жёсткого интервала при входе во врата (не минутного окна)."""
    _last_attack_at.pop(tid, None)
