"""Общий DeclarativeBase для SQLAlchemy-моделей (game_state, duels)."""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass
