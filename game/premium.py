"""Premium-доступ: VIP whitelist + оплата Stars + лимит бесплатных биомов."""

from __future__ import annotations

from config import FREE_BIOME_COUNT, VIP_USER_IDS
from game import content as C
from game.state import GameState


def biome_index(biome_key: str) -> int:
    for i, b in enumerate(C.BIOMES):
        if b["key"] == biome_key:
            return i
    return 0


def gate_biome_index(gate: dict) -> int:
    return biome_index(gate.get("biome") or C.BIOMES[0]["key"])


def has_premium(gs: GameState) -> bool:
    """Полный доступ: VIP или купленный Premium."""
    if gs.telegram_id in VIP_USER_IDS:
        return True
    return bool(gs.premium)


def gate_requires_premium(gate: dict) -> bool:
    """Нужен Premium, если биом за пределами бесплатных."""
    return gate_biome_index(gate) >= FREE_BIOME_COUNT


def can_enter_gate(gs: GameState, gate: dict, *, progression_unlocked: bool) -> bool:
    if not progression_unlocked:
        return False
    if gate_requires_premium(gate) and not has_premium(gs):
        return False
    return True


def premium_info(gs: GameState) -> dict:
    from config import FREE_BIOME_COUNT, PREMIUM_STARS_PRICE

    free_names = [b["name"] for b in C.BIOMES[:FREE_BIOME_COUNT]]
    return {
        "premium": has_premium(gs),
        "vip": gs.telegram_id in VIP_USER_IDS,
        "stars_price": PREMIUM_STARS_PRICE,
        "free_biome_count": FREE_BIOME_COUNT,
        "free_biome_names": free_names,
        "donated_stars": int(getattr(gs, "donated_stars", 0) or 0),
    }
