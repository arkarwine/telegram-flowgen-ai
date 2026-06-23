from __future__ import annotations

import json
import sqlite3
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

from builder.config import PROJECT_ROOT


@dataclass(frozen=True)
class BotRecord:
    bot_id: str
    owner_user_id: int
    bot_name: str
    directory: Path
    token_encrypted: str
    schema_json: str
    status: str
    pid: int | None
    restart_count: int
    crash_window_started_at: float | None
    created_at: float
    updated_at: float
    last_error: str | None


class BuilderDatabase:
    def __init__(self, db_path: Path | str = PROJECT_ROOT / "builder.db") -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def init(self) -> None:
        with self.connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                );

                CREATE TABLE IF NOT EXISTS conversations (
                    user_id INTEGER PRIMARY KEY,
                    phase TEXT NOT NULL,
                    state_json TEXT NOT NULL,
                    updated_at REAL NOT NULL,
                    FOREIGN KEY(user_id) REFERENCES users(user_id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS bots (
                    bot_id TEXT PRIMARY KEY,
                    owner_user_id INTEGER NOT NULL,
                    bot_name TEXT NOT NULL,
                    directory TEXT NOT NULL,
                    token_encrypted TEXT NOT NULL,
                    schema_json TEXT NOT NULL,
                    status TEXT NOT NULL,
                    pid INTEGER,
                    restart_count INTEGER NOT NULL DEFAULT 0,
                    crash_window_started_at REAL,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    last_error TEXT,
                    UNIQUE(owner_user_id, bot_name),
                    FOREIGN KEY(owner_user_id) REFERENCES users(user_id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_bots_owner_status ON bots(owner_user_id, status);
                CREATE INDEX IF NOT EXISTS idx_bots_status ON bots(status);
                """
            )

    def ensure_user(self, user_id: int) -> None:
        now = time.time()
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO users(user_id, created_at, updated_at)
                VALUES(?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET updated_at = excluded.updated_at
                """,
                (user_id, now, now),
            )

    def get_conversation(self, user_id: int) -> tuple[str, dict[str, object]] | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT phase, state_json FROM conversations WHERE user_id = ?",
                (user_id,),
            ).fetchone()
        if row is None:
            return None
        return row["phase"], json.loads(row["state_json"])

    def save_conversation(self, user_id: int, phase: str, state: dict[str, object]) -> None:
        self.ensure_user(user_id)
        now = time.time()
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO conversations(user_id, phase, state_json, updated_at)
                VALUES(?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    phase = excluded.phase,
                    state_json = excluded.state_json,
                    updated_at = excluded.updated_at
                """,
                (user_id, phase, json.dumps(state, ensure_ascii=True), now),
            )

    def clear_conversation(self, user_id: int) -> None:
        with self.connect() as conn:
            conn.execute("DELETE FROM conversations WHERE user_id = ?", (user_id,))

    def register_bot(
        self,
        owner_user_id: int,
        bot_name: str,
        directory: Path,
        token_encrypted: str,
        schema_json: str,
    ) -> BotRecord:
        self.ensure_user(owner_user_id)
        now = time.time()
        bot_id = str(uuid.uuid4())
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO bots(
                    bot_id, owner_user_id, bot_name, directory, token_encrypted,
                    schema_json, status, pid, restart_count, crash_window_started_at,
                    created_at, updated_at, last_error
                )
                VALUES(?, ?, ?, ?, ?, ?, 'stopped', NULL, 0, NULL, ?, ?, NULL)
                """,
                (
                    bot_id,
                    owner_user_id,
                    bot_name,
                    str(directory),
                    token_encrypted,
                    schema_json,
                    now,
                    now,
                ),
            )
        record = self.get_bot_by_id(bot_id)
        if record is None:
            raise RuntimeError("Bot registration succeeded but the record could not be loaded")
        return record

    def update_bot_schema(self, bot_id: str, schema_json: str, directory: Path | None = None) -> None:
        now = time.time()
        with self.connect() as conn:
            if directory is None:
                conn.execute(
                    "UPDATE bots SET schema_json = ?, updated_at = ? WHERE bot_id = ?",
                    (schema_json, now, bot_id),
                )
            else:
                conn.execute(
                    "UPDATE bots SET schema_json = ?, directory = ?, updated_at = ? WHERE bot_id = ?",
                    (schema_json, str(directory), now, bot_id),
                )

    def update_bot_status(
        self,
        bot_id: str,
        status: str,
        pid: int | None,
        last_error: str | None = None,
    ) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE bots
                SET status = ?, pid = ?, last_error = ?, updated_at = ?
                WHERE bot_id = ?
                """,
                (status, pid, last_error, time.time(), bot_id),
            )

    def update_restart_window(
        self,
        bot_id: str,
        restart_count: int,
        crash_window_started_at: float | None,
        status: str | None = None,
        last_error: str | None = None,
    ) -> None:
        now = time.time()
        with self.connect() as conn:
            if status is None:
                conn.execute(
                    """
                    UPDATE bots
                    SET restart_count = ?, crash_window_started_at = ?, last_error = ?, updated_at = ?
                    WHERE bot_id = ?
                    """,
                    (restart_count, crash_window_started_at, last_error, now, bot_id),
                )
            else:
                conn.execute(
                    """
                    UPDATE bots
                    SET restart_count = ?, crash_window_started_at = ?, status = ?,
                        last_error = ?, updated_at = ?
                    WHERE bot_id = ?
                    """,
                    (restart_count, crash_window_started_at, status, last_error, now, bot_id),
                )

    def delete_bot(self, bot_id: str) -> None:
        with self.connect() as conn:
            conn.execute("DELETE FROM bots WHERE bot_id = ?", (bot_id,))

    def list_bots(self, owner_user_id: int | None = None) -> list[BotRecord]:
        params: tuple[int, ...] = ()
        query = "SELECT * FROM bots"
        if owner_user_id is not None:
            query += " WHERE owner_user_id = ?"
            params = (owner_user_id,)
        query += " ORDER BY updated_at DESC"
        with self.connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [self._record(row) for row in rows]

    def list_running_bots(self) -> list[BotRecord]:
        with self.connect() as conn:
            rows = conn.execute("SELECT * FROM bots WHERE status = 'running' ORDER BY updated_at").fetchall()
        return [self._record(row) for row in rows]

    def get_bot_by_id(self, bot_id: str) -> BotRecord | None:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM bots WHERE bot_id = ?", (bot_id,)).fetchone()
        return self._record(row) if row is not None else None

    def find_owned_bot(self, owner_user_id: int, query: str) -> BotRecord | None:
        normalized = query.strip().lower()
        owned = self.list_bots(owner_user_id)
        for bot in owned:
            if bot.bot_id == query or bot.bot_name.lower() == normalized:
                return bot
        for bot in owned:
            if normalized and normalized in bot.bot_name.lower():
                return bot
        return owned[0] if len(owned) == 1 and not normalized else None

    def _record(self, row: sqlite3.Row) -> BotRecord:
        return BotRecord(
            bot_id=row["bot_id"],
            owner_user_id=int(row["owner_user_id"]),
            bot_name=row["bot_name"],
            directory=Path(row["directory"]),
            token_encrypted=row["token_encrypted"],
            schema_json=row["schema_json"],
            status=row["status"],
            pid=int(row["pid"]) if row["pid"] is not None else None,
            restart_count=int(row["restart_count"]),
            crash_window_started_at=(
                float(row["crash_window_started_at"]) if row["crash_window_started_at"] is not None else None
            ),
            created_at=float(row["created_at"]),
            updated_at=float(row["updated_at"]),
            last_error=row["last_error"],
        )


def main() -> None:
    db = BuilderDatabase(PROJECT_ROOT / "builder.db")
    db.init()
    print(f"Initialized {db.db_path}")


if __name__ == "__main__":
    main()

