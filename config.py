"""Конфигурация You vs You (Telegram Mini App + бот).

Секреты и персональные ID только из переменных окружения / .env — в репозитории их нет.
"""

from __future__ import annotations

import os
from pathlib import Path

# Подхватить локальный .env, если есть (без внешней зависимости).
_env_path = Path(__file__).resolve().parent / ".env"
if _env_path.is_file():
    for _line in _env_path.read_text(encoding="utf-8").splitlines():
        _line = _line.strip()
        if not _line or _line.startswith("#") or "=" not in _line:
            continue
        _k, _v = _line.split("=", 1)
        _k, _v = _k.strip(), _v.strip().strip('"').strip("'")
        os.environ.setdefault(_k, _v)


def _require(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(
            f"Не задана переменная окружения {name}. "
            f"Скопируйте .env.example → .env и заполните значения."
        )
    return value


def _int_set(name: str) -> set[int]:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return set()
    out: set[int] = set()
    for part in raw.replace(";", ",").split(","):
        part = part.strip()
        if not part:
            continue
        out.add(int(part))
    return out


BOT_TOKEN = _require("BOT_TOKEN")
WEBAPP_URL = os.environ.get("WEBAPP_URL", "http://127.0.0.1:8090/").rstrip("/") + "/"
BOT_USERNAME = os.environ.get("BOT_USERNAME", "").lstrip("@")

# Владелец: отзывы из Mini App и DEV-auth (если ALLOW_DEV_AUTH=1).
OWNER_TELEGRAM_ID = int(os.environ.get("OWNER_TELEGRAM_ID", "0") or "0")

TIMEZONE = os.environ.get("TIMEZONE", "Europe/Moscow")

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "sqlite+aiosqlite:///data/youvsyou.db",
)

# --- Premium (Telegram Stars) -------------------------------------------------
FREE_BIOME_COUNT = int(os.environ.get("FREE_BIOME_COUNT", "2"))
PREMIUM_STARS_PRICE = int(os.environ.get("PREMIUM_STARS_PRICE", "150"))
PREMIUM_PAYLOAD = os.environ.get("PREMIUM_PAYLOAD", "yvy_premium_v1")
PREMIUM_TITLE = "YOU vs YOU Premium"
PREMIUM_DESCRIPTION = (
    "Открывает все локации и полный прогресс без ограничений. "
    "Первые 2 локации уже бесплатны."
)

# Telegram ID с полным доступом без оплаты (через env, через запятую).
VIP_USER_IDS: set[int] = _int_set("VIP_USER_IDS")
if OWNER_TELEGRAM_ID:
    VIP_USER_IDS = set(VIP_USER_IDS) | {OWNER_TELEGRAM_ID}

# --- Пожертвования (Telegram Stars) ------------------------------------------
DONATE_PAYLOAD_PREFIX = "yvy_donate:"
DONATE_MIN_STARS = 1
DONATE_MAX_STARS = 10000
DONATE_TITLE = "Поддержка YOU vs YOU"
DONATE_DESCRIPTION = (
    "Добровольное пожертвование на развитие проекта. "
    "Спасибо, что помогаешь игре расти!"
)
