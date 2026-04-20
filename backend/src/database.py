"""
Database setup and initialization.

Choice: SQLite via aiosqlite
- Zero external dependencies — no DB server to manage
- File-based persistence — survives restarts, easy to inspect
- Sufficient for a personal finance tool with one user
- aiosqlite gives async access compatible with FastAPI

Money: stored as INTEGER (paise = 1/100 of a rupee).
Never store money as FLOAT — IEEE-754 rounding errors corrupt financial data.
Display layer converts paise → rupees.
"""

import aiosqlite
import os


def get_db_path() -> str:
    """Read lazily so tests can override os.environ per-fixture."""
    return os.getenv("DB_PATH", "expenses.db")


async def get_db() -> aiosqlite.Connection:
    db = await aiosqlite.connect(get_db_path())
    db.row_factory = aiosqlite.Row
    try:
        yield db
    finally:
        await db.close()


async def init_db():
    async with aiosqlite.connect(get_db_path()) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS expenses (
                id              TEXT PRIMARY KEY,
                idempotency_key TEXT UNIQUE NOT NULL,
                amount_paise    INTEGER NOT NULL,
                category        TEXT NOT NULL,
                description     TEXT NOT NULL,
                date            TEXT NOT NULL,
                created_at      TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_expenses_category
            ON expenses(category)
        """)
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_expenses_date
            ON expenses(date DESC)
        """)
        await db.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_expenses_idempotency
            ON expenses(idempotency_key)
        """)
        await db.commit()
