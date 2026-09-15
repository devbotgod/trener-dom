"""Игровая логика «You vs You»: бой, урон, прогрессия."""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta

from game import content as C
from game.premium import (
    can_enter_gate,
    gate_requires_premium,
    has_premium,
    premium_info,
)
from game.state import GameState
from utils.timezone import today_msk


# --- дни / стрик / ежедневные задания -----------------------------------------

def _today() -> date:
    """Игровой день всегда по МСК (VPS может быть в UTC)."""
    return today_msk()


def live_streak(gs: GameState, today: date | None = None) -> int:
    """Актуальная серия с учётом пропусков и заморозок (не ждёт следующей тренировки)."""
    today = today or _today()
    streak = gs.streak_count or 0
    streak_date = gs.streak_date
    if not streak or streak_date is None:
        return 0
    gap = (today - streak_date).days
    if gap <= 1:
        return streak
    missed = gap - 1
    if 0 < missed <= (gs.freezes or 0):
        return streak
    return 0


def _roll_day(gs: GameState) -> None:
    """Сброс дневных счётчиков и заданий при наступлении нового дня."""
    today = _today()
    if gs.daily_date != today:
        # сохранить прошедший день в историю
        if gs.daily_date is not None and gs.daily_reps > 0:
            try:
                hist = json.loads(gs.history or "[]")
            except Exception:
                hist = []
            hist.append([str(gs.daily_date), gs.daily_reps])
            gs.history = json.dumps(hist[-30:])
        gs.daily_date = today
        gs.daily_reps = 0
        gs.daily_kills = 0
        gs.daily_gates = 0
        gs.quests_claimed = ""
        gs.workout_done = ""


def weekly_reps(gs: GameState) -> int:
    """Повторы за последние 7 дней (из истории + сегодня) — для лидерборда."""
    today = _today()
    total = 0
    try:
        for d, reps in json.loads(gs.history or "[]"):
            try:
                dd = date.fromisoformat(d)
                if (today - dd).days < 7:
                    total += int(reps)
            except Exception:
                pass
    except Exception:
        pass
    if gs.daily_date == today:
        total += gs.daily_reps
    return total


def season_reps(gs: GameState) -> int:
    """Повторы за текущий календарный месяц (сезон)."""
    today = _today()
    total = 0
    try:
        for d, reps in json.loads(gs.history or "[]"):
            try:
                dd = date.fromisoformat(d)
                if dd.year == today.year and dd.month == today.month:
                    total += int(reps)
            except Exception:
                pass
    except Exception:
        pass
    if gs.daily_date == today:
        total += gs.daily_reps
    return total


def season_label(d: date | None = None) -> str:
    """Человекочитаемое имя сезона (месяц)."""
    months = (
        "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
        "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь",
    )
    dd = d or _today()
    return f"{months[dd.month - 1]} {dd.year}"


def friend_id_set(gs: GameState) -> set[int]:
    out: set[int] = set()
    for part in (gs.friends or "").split(","):
        part = part.strip()
        if not part:
            continue
        try:
            out.add(int(part))
        except ValueError:
            pass
    return out


def add_friend(gs: GameState, friend_tid: int) -> bool:
    """Добавить друга. True если список изменился."""
    if not friend_tid or friend_tid == gs.telegram_id:
        return False
    ids = friend_id_set(gs)
    if friend_tid in ids:
        return False
    ids.add(int(friend_tid))
    gs.friends = ",".join(str(x) for x in sorted(ids))
    return True


def clamp_reminder_time(hour: int, minute: int = 0) -> tuple[int, int]:
    h = max(0, min(23, int(hour)))
    m = max(0, min(59, int(minute)))
    return h, m


def _title_stats(gs: GameState) -> dict:
    return {
        "level": gs.level,
        "gates": len(_cleared_set(gs)),
        "streak": live_streak(gs),
        "kills": gs.total_kills,
        "reps": gs.total_reps,
    }


def _title_unlocked(t: dict, stats: dict) -> bool:
    if t["need"] is None:
        return True
    return stats.get(t["need"], 0) >= t["val"]


def _history_view(gs: GameState) -> list[dict]:
    """Последние 7 календарных дней подряд (без дыр)."""
    today = _today()
    by_date: dict[str, int] = {}
    try:
        for d, reps in json.loads(gs.history or "[]"):
            by_date[str(d)] = int(reps)
    except Exception:
        pass
    if gs.daily_date == today:
        by_date[str(today)] = gs.daily_reps
    out = []
    for i in range(6, -1, -1):
        dd = today - timedelta(days=i)
        key = str(dd)
        out.append({"label": key[5:], "reps": by_date.get(key, 0)})
    return out


def _workout_done_count(gs: GameState) -> int:
    return len([x for x in (gs.workout_done or "").split(",") if x])


def _quest_counters(gs: GameState) -> dict:
    return {"reps": gs.daily_reps, "kills": gs.daily_kills, "gates": gs.daily_gates,
            "workout": _workout_done_count(gs)}


def _grant_quests(gs: GameState, events: list[dict]) -> None:
    """Начислить награду за выполненные задания (общая для боя и простого режима)."""
    claimed = {x for x in (gs.quests_claimed or "").split(",") if x}
    counters = _quest_counters(gs)
    for q in C.daily_quests(_today().toordinal(), gs.mode or "adventure"):
        if q["id"] not in claimed and counters.get(q["metric"], 0) >= q["target"]:
            claimed.add(q["id"])
            _gain_xp(gs, q["reward"], events)
            events.append({"type": "quest_done", "text": q["text"], "reward": q["reward"]})
    gs.quests_claimed = ",".join(sorted(claimed))


def _daily_quests_view(gs: GameState) -> list[dict]:
    ordinal = _today().toordinal()
    claimed = {x for x in (gs.quests_claimed or "").split(",") if x}
    counters = _quest_counters(gs)
    out = []
    for q in C.daily_quests(ordinal, gs.mode or "adventure"):
        prog = min(counters.get(q["metric"], 0), q["target"])
        out.append({
            "id": q["id"], "icon": q["icon"], "text": q["text"],
            "progress": prog, "target": q["target"], "reward": q["reward"],
            "done": q["id"] in claimed or prog >= q["target"],
        })
    return out


def _pick_daily_exercises(gs: GameState) -> list[str]:
    """5 уникальных упражнений дня: предпочтение целям, без дублей."""
    goals = C.expand_goals(_goals_list(gs))
    keys = list(C.EXERCISES.keys())
    primary = [k for k in keys if set(C.EXERCISES[k]["groups"]) & goals] or keys
    ordinal = _today().toordinal()
    pick: list[str] = []

    def _take(pool: list[str], need: int, step: int) -> None:
        if not pool or need <= 0:
            return
        for i in range(len(pool) * 2):
            if len(pick) >= 5 or need <= 0:
                return
            k = pool[(ordinal + i * step) % len(pool)]
            if k not in pick:
                pick.append(k)
                need -= 1

    _take(primary, 4, 3)
    _take(keys, 5 - len(pick), 7)
    for k in keys:
        if len(pick) >= 5:
            break
        if k not in pick:
            pick.append(k)
    return pick[:5]


def _workout_view(gs: GameState) -> list[dict]:
    """Тренировка дня для простого режима: 5 уникальных упражнений под цели."""
    mult = _mult(gs)
    done = {x for x in (gs.workout_done or "").split(",") if x}
    out = []
    for k in _pick_daily_exercises(gs):
        e = C.EXERCISES[k]
        if e["mode"] == "hold":
            target = max(15, round(30 * mult))
        elif e["mode"] == "manual":
            target = max(10, round(15 * mult))
        else:
            target = max(6, round(12 * mult))
        out.append({
            "key": k, "name": e["name"], "icon": e["icon"], "mode": e["mode"], "type": e["type"],
            "detector": e["detector"], "how": e.get("how", ""), "tip": e.get("tip", ""),
            "groups": e["groups"], "target": target, "done": k in done,
        })
    return out


def workout_day_keys(gs: GameState) -> set[str]:
    """Ключи упражнений тренировки дня (для валидации API)."""
    _roll_day(gs)
    return {x["key"] for x in _workout_view(gs)}


def complete_exercise(gs: GameState, key: str) -> dict:
    """Отметить упражнение тренировки дня выполненным (+бонус XP)."""
    _roll_day(gs)
    events: list[dict] = []
    day_keys = {x["key"] for x in _workout_view(gs)}
    if key in day_keys:
        done = {x for x in (gs.workout_done or "").split(",") if x}
        if key not in done:
            done.add(key)
            gs.workout_done = ",".join(sorted(done))
            _gain_xp(gs, 15, events)
            events.append({"type": "workout_done", "name": C.EXERCISES[key]["name"]})
            if all(x["done"] for x in _workout_view(gs)):
                _gain_xp(gs, 40, events)
                events.append({"type": "workout_complete"})
            _grant_quests(gs, events)
    gs.updated_at = datetime.utcnow()
    snap = snapshot(gs)
    snap["events"] = events
    return snap


def _bump_daily(gs: GameState, events: list[dict], reps=0, kills=0, gates=0) -> None:
    """Обновить дневные счётчики, стрик и проверить задания."""
    _roll_day(gs)
    today = _today()
    # стрик — раз в день при любой активности (с учётом дней отдыха/заморозок)
    if reps > 0 and gs.streak_date != today:
        if gs.streak_date is None:
            gs.streak_count = 1
        else:
            gap = (today - gs.streak_date).days
            if gap == 1:
                gs.streak_count += 1
            else:
                missed = gap - 1
                if 0 < missed <= gs.freezes:
                    gs.freezes -= missed  # день отдыха спас серию
                    gs.streak_count += 1
                    events.append({"type": "freeze_used", "left": gs.freezes})
                else:
                    gs.streak_count = 1
        gs.streak_date = today
        # начисление дня отдыха за каждые N дней серии
        if gs.streak_count % C.FREEZE_EVERY_STREAK == 0 and gs.freezes < C.MAX_FREEZES:
            gs.freezes += 1
            events.append({"type": "freeze_gained", "left": gs.freezes})
        events.append({"type": "streak", "count": gs.streak_count})

    gs.daily_reps += reps
    gs.daily_kills += kills
    gs.daily_gates += gates
    _grant_quests(gs, events)


# --- helpers ------------------------------------------------------------------

def _cleared_set(gs: GameState) -> set[str]:
    return {x for x in (gs.cleared_gates or "").split(",") if x}


def _apply_regen(gs: GameState) -> None:
    """Восстановление HP в реальном времени с момента последнего апдейта."""
    now = datetime.utcnow()
    last = gs.hp_updated_at or now
    minutes = max(0.0, (now - last).total_seconds() / 60.0)
    max_hp = C.max_hp_for_level(gs.level)
    if gs.player_hp < max_hp and minutes > 0:
        gs.player_hp = min(max_hp, gs.player_hp + minutes * C.HP_REGEN_PER_MIN)
    gs.hp_updated_at = now


def _current_gate(gs: GameState) -> dict:
    return C.GATES_BY_ID.get(gs.current_gate, C.GATES[0])


def _current_enemy(gs: GameState) -> dict | None:
    gate = _current_gate(gs)
    if gs.enemy_index >= len(gate["enemies"]):
        return None
    return gate["enemies"][gs.enemy_index]


def _mult(gs: GameState) -> float:
    prog = C.PROGRAMS.get(gs.program)
    return prog["mult"] if prog else C.DEFAULT_PROGRAM_MULT


def _enemy_max_hp(gs: GameState, enemy: dict) -> int:
    return max(1, round(enemy["hp"] * _mult(gs)))


def _goals_list(gs: GameState) -> list[str]:
    return [x for x in (gs.goals or "").split(",") if x]


def _enemy_exercise(gs: GameState, enemy: dict) -> str:
    """Упражнение врага под цели игрока (70% выбранные группы, 30% база)."""
    goals = _goals_list(gs)
    if not goals:
        return enemy["exercise"]
    primary, base = C.exercises_for_goals(goals)
    h = sum(ord(c) for c in enemy["id"])
    pool = primary if (h % 10) < 7 else base
    return pool[h % len(pool)] if pool else enemy["exercise"]


def _ensure_enemy_hp(gs: GameState) -> None:
    """Инициализировать HP текущего врага, если бой не начат."""
    enemy = _current_enemy(gs)
    if enemy is None:
        return
    if gs.enemy_hp <= 0:
        gs.enemy_hp = float(_enemy_max_hp(gs, enemy))


# --- сериализация состояния для фронта ----------------------------------------

def _clamp_current_gate(gs: GameState) -> None:
    """Если текущие врата недоступны (Premium) — откатить на последний доступный уровень."""
    gate = _current_gate(gs)
    cleared = _cleared_set(gs)
    idx = C.gate_index(gate["id"])
    progression = (idx == 0) or (C.GATES[idx - 1]["id"] in cleared)
    if can_enter_gate(gs, gate, progression_unlocked=progression):
        return

    fallback = C.GATES[0]["id"]
    for i, g in enumerate(C.GATES):
        prog = (i == 0) or (C.GATES[i - 1]["id"] in cleared)
        if can_enter_gate(gs, g, progression_unlocked=prog):
            fallback = g["id"]
        elif gate_requires_premium(g) and not has_premium(gs):
            break
        elif not prog:
            break

    if gs.current_gate != fallback:
        gs.current_gate = fallback
        gs.enemy_index = 0
        gs.enemy_hp = 0.0


def snapshot(gs: GameState) -> dict:
    _clamp_current_gate(gs)
    _apply_regen(gs)
    _roll_day(gs)
    _ensure_enemy_hp(gs)

    gate = _current_gate(gs)
    enemy = _current_enemy(gs)
    max_hp = C.max_hp_for_level(gs.level)
    cleared = _cleared_set(gs)

    # список врат с блокировками (прогресс + Premium с 3-го биома)
    premium = has_premium(gs)
    gates_view = []
    for i, g in enumerate(C.GATES):
        progression = (i == 0) or (C.GATES[i - 1]["id"] in cleared)
        needs_prem = gate_requires_premium(g)
        premium_locked = needs_prem and not premium
        unlocked = can_enter_gate(gs, g, progression_unlocked=progression)
        # упражнения как в бою (с учётом целей игрока), без дублей
        ex_list, seen_ex = [], set()
        for en in g["enemies"]:
            key = _enemy_exercise(gs, en)
            if key not in seen_ex:
                seen_ex.add(key)
                ex = C.EXERCISES[key]
                ex_list.append({"icon": ex["icon"], "name": ex["name"]})
        gates_view.append({
            "id": g["id"],
            "rank": g["rank"],
            "name": g["name"],
            "subtitle": g["subtitle"],
            "color": g["color"],
            "biome": g.get("biome", "forest"),
            "biome_name": g.get("biome_name", ""),
            "is_biome_boss": g.get("is_biome_boss", False),
            "node_avatar": g["enemies"][-1]["avatar"] if g["enemies"] else "ogre",
            "enemies_count": len(g["enemies"]),
            "exercises": ex_list,
            "unlocked": unlocked,
            "progression_unlocked": progression,
            "premium_locked": premium_locked,
            "cleared": g["id"] in cleared,
            "is_current": g["id"] == gs.current_gate,
        })

    # дневной лимит разминки
    today = _today()
    train_used = gs.train_xp_today if gs.train_date == today else 0
    train_left = max(0, C.TRAIN_DAILY_XP_CAP - train_used)
    title_stats = _title_stats(gs)

    enemy_view = None
    if enemy is not None:
        eff_ex = _enemy_exercise(gs, enemy)
        ex = C.EXERCISES[eff_ex]
        enemy_view = {
            "id": enemy["id"],
            "name": enemy["name"],
            "hp": round(gs.enemy_hp),
            "max_hp": _enemy_max_hp(gs, enemy),
            "attack": enemy["attack"],
            "kind": enemy["kind"],
            "avatar": enemy["avatar"],
            "exercise": eff_ex,
            "exercise_name": ex["name"],
            "exercise_icon": ex["icon"],
            "exercise_type": ex["type"],
            "detector": ex["detector"],
            "tip": ex.get("tip", ""),
            "how": ex.get("how", ""),
            "index": gs.enemy_index,
            "total": len(gate["enemies"]),
        }

    return {
        "player": {
            "level": gs.level,
            "xp": gs.xp,
            "xp_this_level": gs.xp - C.xp_for_level(gs.level),
            "xp_next_level": C.xp_for_level(gs.level + 1) - C.xp_for_level(gs.level),
            "hp": round(gs.player_hp),
            "max_hp": max_hp,
            "damage": C.damage_for_level(gs.level),
            "total_reps": gs.total_reps,
            "total_kills": gs.total_kills,
            "gates_cleared": len(cleared),
            "train_left": train_left,
            "train_cap": C.TRAIN_DAILY_XP_CAP,
            "streak": live_streak(gs),
            "title": C.TITLES_BY_ID.get(gs.title, C.TITLES[0])["name"],
            "avatar_emoji": gs.avatar_emoji or "🧑",
            "program": gs.program,
            "program_name": C.PROGRAMS.get(gs.program, {}).get("name", "Средний"),
            "needs_program": gs.program == "",
            "freezes": gs.freezes,
            "gender": gs.gender,
            "mode": gs.mode or "adventure",
            "goals": _goals_list(gs),
            "needs_onboarding": gs.gender == "",
            "nickname": gs.name or ("Охотник-" + str(abs(gs.telegram_id))[-4:]),
            "reminders": gs.reminders_on,
            "reminder_hour": int(getattr(gs, "reminder_hour", 19) or 19),
            "reminder_minute": int(getattr(gs, "reminder_minute", 0) or 0),
            "friends_count": len(friend_id_set(gs)),
            "duel_wins": int(getattr(gs, "duel_wins", 0) or 0),
            "duel_losses": int(getattr(gs, "duel_losses", 0) or 0),
            "duel_draws": int(getattr(gs, "duel_draws", 0) or 0),
        },
        "gate": {
            "id": gate["id"],
            "rank": gate["rank"],
            "name": gate["name"],
            "subtitle": gate["subtitle"],
            "color": gate["color"],
            "biome_name": gate.get("biome_name", ""),
            "is_biome_boss": gate.get("is_biome_boss", False),
            "node_avatar": gate["enemies"][-1]["avatar"] if gate["enemies"] else "ogre",
            "cleared_enemies": gs.enemy_index,
            "total_enemies": len(gate["enemies"]),
        },
        "enemy": enemy_view,
        "gates": gates_view,
        "gate_cleared": enemy is None,
        "daily": {
            "quests": _daily_quests_view(gs),
            "reps": gs.daily_reps, "kills": gs.daily_kills, "gates": gs.daily_gates,
        },
        "history": _history_view(gs),
        "titles": [
            {"id": t["id"], "name": t["name"], "desc": t["desc"],
             "unlocked": _title_unlocked(t, title_stats), "selected": t["id"] == gs.title}
            for t in C.TITLES
        ],
        "avatars": C.AVATAR_CHOICES,
        "avatar_emoji": gs.avatar_emoji or "🧑",
        "programs": [
            {"id": k, "name": v["name"], "icon": v["icon"], "desc": v["desc"],
             "selected": k == gs.program}
            for k, v in C.PROGRAMS.items()
        ],
        "goal_groups": C.GOAL_GROUPS,
        "workout": _workout_view(gs),
        "exercises": [
            {
                "key": k, "name": ex["name"], "icon": ex["icon"], "type": ex["type"],
                "mode": ex.get("mode", "reps"), "groups": ex.get("groups", []),
                "detector": ex["detector"], "how": ex.get("how", ""), "tip": ex.get("tip", ""),
            }
            for k, ex in C.EXERCISES.items()
        ],
        "premium": premium_info(gs),
    }


# --- действия -----------------------------------------------------------------

def select_gate(gs: GameState, gate_id: str) -> dict:
    """Выбрать врата (если открыты). Повторный вход в те же — сохраняет прогресс боя."""
    if gate_id not in C.GATES_BY_ID:
        raise ValueError("unknown gate")
    gate = C.GATES_BY_ID[gate_id]
    idx = C.gate_index(gate_id)
    cleared = _cleared_set(gs)
    progression = (idx == 0) or (C.GATES[idx - 1]["id"] in cleared)
    if gate_requires_premium(gate) and not has_premium(gs):
        raise PermissionError("premium_required")
    if not progression:
        raise PermissionError("gate locked")
    if gs.current_gate != gate_id:
        gs.current_gate = gate_id
        gs.enemy_index = 0
        gs.enemy_hp = 0.0
    gs.updated_at = datetime.utcnow()
    return snapshot(gs)


def attack(gs: GameState, reps: int) -> dict:
    """Провести подход: reps повторов по текущему врагу. Возвращает snapshot+events."""
    _clamp_current_gate(gs)
    gate0 = _current_gate(gs)
    if gate_requires_premium(gate0) and not has_premium(gs):
        snap = snapshot(gs)
        snap["events"] = [{"type": "premium_required"}]
        snap["error"] = "premium_required"
        return snap
    _apply_regen(gs)
    _ensure_enemy_hp(gs)
    events: list[dict] = []

    reps = max(0, int(reps))
    enemy = _current_enemy(gs)
    if enemy is None:
        snap = snapshot(gs)
        snap["events"] = events
        return snap

    dmg_per_rep = C.damage_for_level(gs.level)
    max_hp_before = C.max_hp_for_level(gs.level)

    gs.total_reps += reps

    # Урон по врагу
    damage = reps * dmg_per_rep
    gs.enemy_hp -= damage

    # Контратака врага (микро-урон за каждый повтор — гонка на истощение)
    counter = reps * enemy["attack"]
    gs.player_hp = max(0.0, gs.player_hp - counter)

    events.append({
        "type": "hit",
        "reps": reps,
        "damage": round(damage),
        "counter": round(counter, 1),
    })

    # Игрок пал
    if gs.player_hp <= 0:
        gs.player_hp = round(max_hp_before * 0.5)  # возрождение с половиной HP
        gs.enemy_index = 0
        gs.enemy_hp = 0.0
        gs.hp_updated_at = datetime.utcnow()
        gs.updated_at = datetime.utcnow()
        events.append({"type": "player_defeated"})
        _bump_daily(gs, events, reps=reps)
        snap = snapshot(gs)
        snap["events"] = events
        return snap

    # Враг убит (возможно несколько за подход); overkill переносится дальше
    gate = _current_gate(gs)
    while gs.enemy_hp <= 0 and gs.enemy_index < len(gate["enemies"]):
        overkill = -gs.enemy_hp  # остаток урона после убийства
        dead = gate["enemies"][gs.enemy_index]
        gs.total_kills += 1
        _gain_xp(gs, dead["xp"], events)
        events.append({
            "type": "enemy_defeated",
            "name": dead["name"],
            "kind": dead["kind"],
            "xp": dead["xp"],
        })
        gs.enemy_index += 1
        if gs.enemy_index < len(gate["enemies"]):
            nxt_max = float(_enemy_max_hp(gs, gate["enemies"][gs.enemy_index]))
            gs.enemy_hp = nxt_max - overkill
        else:
            gs.enemy_hp = 0.0

    # Врата зачищены
    if gs.enemy_index >= len(gate["enemies"]):
        cleared = _cleared_set(gs)
        first_clear = gate["id"] not in cleared
        if first_clear:
            cleared.add(gate["id"])
            gs.cleared_gates = ",".join(sorted(cleared))
            _gain_xp(gs, gate["reward_xp"], events)
        events.append({
            "type": "gate_cleared",
            "gate": gate["name"],
            "rank": gate["rank"],
            "first_clear": first_clear,
            "reward_xp": gate["reward_xp"] if first_clear else 0,
        })
        # авто-открытие следующих врат
        nxt = C.gate_index(gate["id"]) + 1
        if nxt < len(C.GATES):
            nxt_gate = C.GATES[nxt]
            ev = {
                "type": "gate_unlocked",
                "gate": nxt_gate["name"],
                "rank": nxt_gate["rank"],
            }
            if gate_requires_premium(nxt_gate) and not has_premium(gs):
                ev["premium_required"] = True
                ev["type"] = "premium_gate_ahead"
                ev["biome_name"] = nxt_gate.get("biome_name", "")
            events.append(ev)

    kills = sum(1 for e in events if e["type"] == "enemy_defeated")
    gates_done = sum(1 for e in events if e["type"] == "gate_cleared" and e.get("first_clear"))
    _bump_daily(gs, events, reps=reps, kills=kills, gates=gates_done)

    gs.updated_at = datetime.utcnow()
    snap = snapshot(gs)
    snap["events"] = events
    return snap


def _gain_xp(gs: GameState, amount: int, events: list[dict]) -> None:
    before = gs.level
    gs.xp += amount
    gs.level = C.level_from_xp(gs.xp)
    if gs.level > before:
        # при апе уровня добираем HP до нового максимума (награда)
        gs.player_hp = C.max_hp_for_level(gs.level)
        events.append({
            "type": "level_up",
            "level": gs.level,
            "max_hp": C.max_hp_for_level(gs.level),
            "damage": C.damage_for_level(gs.level),
        })


def train(gs: GameState, reps: int) -> dict:
    """Свободная разминка: начислить XP за повторы с дневным лимитом."""
    _apply_regen(gs)
    events: list[dict] = []
    reps = max(0, int(reps))
    today = _today()
    if gs.train_date != today:
        gs.train_date = today
        gs.train_xp_today = 0

    room = max(0, C.TRAIN_DAILY_XP_CAP - gs.train_xp_today)
    # после капа XP повторы не качают лидерборд/стрик/квесты
    effective = min(reps, room // C.TRAIN_XP_PER_REP if C.TRAIN_XP_PER_REP else reps)
    gained = effective * C.TRAIN_XP_PER_REP

    gs.total_reps += effective
    gs.train_xp_today += gained
    if gained > 0:
        _gain_xp(gs, gained, events)
    events.append({
        "type": "train",
        "reps": effective,
        "xp": gained,
        "capped": effective < reps,
    })
    if effective > 0:
        _bump_daily(gs, events, reps=effective)
    gs.updated_at = datetime.utcnow()
    snap = snapshot(gs)
    snap["events"] = events
    return snap


def reset(gs: GameState) -> dict:
    """Полный сброс прогресса (для теста)."""
    gs.level = 1
    gs.xp = 0
    gs.player_hp = float(C.BASE_MAX_HP)
    gs.current_gate = "gate_1"
    gs.enemy_index = 0
    gs.enemy_hp = 0.0
    gs.cleared_gates = ""
    gs.total_reps = 0
    gs.total_kills = 0
    # стрик, задания, разминка
    gs.streak_count = 0
    gs.streak_date = None
    gs.daily_date = None
    gs.daily_reps = 0
    gs.daily_kills = 0
    gs.daily_gates = 0
    gs.quests_claimed = ""
    gs.train_date = None
    gs.train_xp_today = 0
    gs.history = ""
    gs.title = "rookie"
    gs.avatar_emoji = "🧑"
    gs.freezes = 1
    # программа сложности сохраняется (это настройка, а не прогресс)
    gs.hp_updated_at = datetime.utcnow()
    gs.updated_at = datetime.utcnow()
    return snapshot(gs)


def setup(gs: GameState, gender=None, mode=None, goals=None) -> dict:
    """Онбординг: пол, режим, цели (группы мышц)."""
    if gender in ("male", "female"):
        gs.gender = gender
    if mode in ("adventure", "simple"):
        gs.mode = mode
    if isinstance(goals, list):
        valid = {g["id"] for g in C.GOAL_GROUPS}
        picked = [g for g in goals if g in valid]
        gs.goals = ",".join(picked)
    gs.enemy_hp = 0.0  # переинициализировать под новые упражнения
    gs.updated_at = datetime.utcnow()
    return snapshot(gs)


def set_program(gs: GameState, program: str) -> dict:
    """Выбрать программу сложности (пересчитывает HP текущего врага)."""
    if program in C.PROGRAMS:
        gs.program = program
        gs.enemy_hp = 0.0  # переинициализируется под новый множитель
    gs.updated_at = datetime.utcnow()
    return snapshot(gs)


def customize(gs: GameState, title=None, avatar=None) -> dict:
    """Сменить титул (если открыт) и/или аватар."""
    if title and title in C.TITLES_BY_ID:
        if _title_unlocked(C.TITLES_BY_ID[title], _title_stats(gs)):
            gs.title = title
    if avatar and avatar in C.AVATAR_CHOICES:
        gs.avatar_emoji = avatar
    gs.updated_at = datetime.utcnow()
    return snapshot(gs)
