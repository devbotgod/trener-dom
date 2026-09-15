"""Модель игрового состояния «You vs You»."""

from datetime import date, datetime
from typing import Optional

from sqlalchemy import BigInteger, Boolean, Date, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from models import Base


class GameState(Base):
    __tablename__ = "game_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False)

    level: Mapped[int] = mapped_column(Integer, default=1)
    xp: Mapped[int] = mapped_column(Integer, default=0)

    player_hp: Mapped[float] = mapped_column(Float, default=168.0)
    hp_updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    current_gate: Mapped[str] = mapped_column(String(32), default="gate_1")
    enemy_index: Mapped[int] = mapped_column(Integer, default=0)
    enemy_hp: Mapped[float] = mapped_column(Float, default=0.0)  # 0 => не инициализирован

    cleared_gates: Mapped[str] = mapped_column(Text, default="")   # csv id врат
    total_reps: Mapped[int] = mapped_column(Integer, default=0)
    total_kills: Mapped[int] = mapped_column(Integer, default=0)

    # Разминка (свободная тренировка)
    train_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    train_xp_today: Mapped[int] = mapped_column(Integer, default=0)

    # Стрик (серия дней)
    streak_count: Mapped[int] = mapped_column(Integer, default=0)
    streak_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)

    # Дневные счётчики и квесты
    daily_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    daily_reps: Mapped[int] = mapped_column(Integer, default=0)
    daily_kills: Mapped[int] = mapped_column(Integer, default=0)
    daily_gates: Mapped[int] = mapped_column(Integer, default=0)
    quests_claimed: Mapped[str] = mapped_column(Text, default="")

    # История по дням (JSON) и кастомизация
    history: Mapped[str] = mapped_column(Text, default="")
    title: Mapped[str] = mapped_column(String(32), default="rookie")
    avatar_emoji: Mapped[str] = mapped_column(String(8), default="🧑")

    # Программа сложности и дни отдыха (заморозки стрика)
    program: Mapped[str] = mapped_column(String(16), default="")  # "" => не выбрана
    freezes: Mapped[int] = mapped_column(Integer, default=1)

    # Онбординг: пол, режим, цели (группы мышц)
    gender: Mapped[str] = mapped_column(String(8), default="")     # "" => онбординг
    mode: Mapped[str] = mapped_column(String(16), default="adventure")
    goals: Mapped[str] = mapped_column(Text, default="")           # csv id групп мышц
    workout_done: Mapped[str] = mapped_column(Text, default="")    # csv выполненных упр. дня
    name: Mapped[str] = mapped_column(String(64), default="")       # ник для лидерборда

    # Реальный Telegram-профиль (для приватного просмотра владельцем в отзывах)
    real_name: Mapped[str] = mapped_column(String(64), default="")
    real_username: Mapped[str] = mapped_column(String(64), default="")

    # Уведомления (напоминания)
    reminders_on: Mapped[bool] = mapped_column(Boolean, default=True)
    reminder_hour: Mapped[int] = mapped_column(Integer, default=19)
    reminder_minute: Mapped[int] = mapped_column(Integer, default=0)
    last_reminder_slot: Mapped[str] = mapped_column(String(32), default="")

    # Друзья для рейтинга (csv telegram_id)
    friends: Mapped[str] = mapped_column(Text, default="")

    # Обратная связь (антиспам)
    feedback_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    feedback_count: Mapped[int] = mapped_column(Integer, default=0)

    # Premium (Telegram Stars) — VIP обходит через config.VIP_USER_IDS
    premium: Mapped[bool] = mapped_column(Boolean, default=False)
    premium_charge_id: Mapped[str] = mapped_column(String(128), default="")
    premium_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # Сумма пожертвований Stars (накопительно)
    donated_stars: Mapped[int] = mapped_column(Integer, default=0)

    # PvP арена
    duel_wins: Mapped[int] = mapped_column(Integer, default=0)
    duel_losses: Mapped[int] = mapped_column(Integer, default=0)
    duel_draws: Mapped[int] = mapped_column(Integer, default=0)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
