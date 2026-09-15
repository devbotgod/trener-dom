"""Утилиты для работы с временем приложения (TIMEZONE из config)."""

from datetime import date, datetime, timedelta, time
from zoneinfo import ZoneInfo

from config import TIMEZONE

TZ = ZoneInfo(TIMEZONE)


def now_msk() -> datetime:
    """Текущее время в TIMEZONE приложения (по умолчанию Europe/Moscow)."""
    return datetime.now(TZ)


def today_msk() -> date:
    """Сегодняшняя дата в TIMEZONE приложения."""
    return now_msk().date()


def format_msk(dt: datetime | None = None) -> str:
    """Форматирование даты/времени."""
    if dt is None:
        dt = now_msk()
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=TZ)
    else:
        dt = dt.astimezone(TZ)
    return dt.strftime("%d.%m.%Y %H:%M")


def parse_time_hm(value: str) -> time:
    """Парсинг 'HH:MM' в time."""
    parts = value.strip().split(":")
    return time(int(parts[0]), int(parts[1]))


def week_start(d: date | None = None) -> date:
    """Понедельник текущей недели."""
    if d is None:
        d = today_msk()
    return d - timedelta(days=d.weekday())
