"""Async database engine и сессии."""

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from config import DATABASE_URL
from models import Base

engine = create_async_engine(DATABASE_URL, echo=False)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


def _table_migrate(sync_conn, table: str, migrations: dict[str, str]) -> None:
    import sqlalchemy as sa

    rows = sync_conn.execute(sa.text(f"PRAGMA table_info({table})")).fetchall()
    if not rows:
        return
    existing = {row[1] for row in rows}
    for col, typedef in migrations.items():
        if col not in existing:
            sync_conn.execute(sa.text(f"ALTER TABLE {table} ADD COLUMN {col} {typedef}"))


async def _migrate_columns(conn) -> None:
    """Добавить новые колонки в существующую SQLite БД."""

    def _run(sync_conn):
        _table_migrate(sync_conn, "game_state", {
            "train_date": "DATE",
            "train_xp_today": "INTEGER DEFAULT 0",
            "streak_count": "INTEGER DEFAULT 0",
            "streak_date": "DATE",
            "daily_date": "DATE",
            "daily_reps": "INTEGER DEFAULT 0",
            "daily_kills": "INTEGER DEFAULT 0",
            "daily_gates": "INTEGER DEFAULT 0",
            "quests_claimed": "TEXT DEFAULT ''",
            "history": "TEXT DEFAULT ''",
            "title": "VARCHAR(32) DEFAULT 'rookie'",
            "avatar_emoji": "VARCHAR(8) DEFAULT '🧑'",
            "program": "VARCHAR(16) DEFAULT ''",
            "freezes": "INTEGER DEFAULT 1",
            "gender": "VARCHAR(8) DEFAULT ''",
            "mode": "VARCHAR(16) DEFAULT 'adventure'",
            "goals": "TEXT DEFAULT ''",
            "workout_done": "TEXT DEFAULT ''",
            "name": "VARCHAR(64) DEFAULT ''",
            "real_name": "VARCHAR(64) DEFAULT ''",
            "real_username": "VARCHAR(64) DEFAULT ''",
            "reminders_on": "BOOLEAN DEFAULT 1",
            "reminder_hour": "INTEGER DEFAULT 19",
            "reminder_minute": "INTEGER DEFAULT 0",
            "last_reminder_slot": "VARCHAR(32) DEFAULT ''",
            "friends": "TEXT DEFAULT ''",
            "feedback_date": "DATE",
            "feedback_count": "INTEGER DEFAULT 0",
            "premium": "BOOLEAN DEFAULT 0",
            "premium_charge_id": "VARCHAR(128) DEFAULT ''",
            "premium_at": "DATETIME",
            "donated_stars": "INTEGER DEFAULT 0",
            "duel_wins": "INTEGER DEFAULT 0",
            "duel_losses": "INTEGER DEFAULT 0",
            "duel_draws": "INTEGER DEFAULT 0",
        })

    await conn.run_sync(_run)


async def init_db() -> None:
    """Создание таблиц."""
    from game import duel as _duel  # noqa: F401
    from game.state import GameState  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await _migrate_columns(conn)


async def get_session() -> AsyncSession:
    """Генератор сессии для dependency injection."""
    async with async_session() as session:
        yield session
