from __future__ import annotations

import json
import textwrap
from dataclasses import dataclass

from builder.schema.blocks import BotSchema


@dataclass(frozen=True)
class GeneratedFile:
    relative_path: str
    content: str


class BotCodeGenerator:
    def generate(self, schema: BotSchema) -> list[GeneratedFile]:
        schema_json = schema.model_dump_json(indent=2)
        return [
            GeneratedFile("schema.json", schema_json + "\n"),
            GeneratedFile("requirements.txt", self._requirements()),
            GeneratedFile("config.py", self._config_py()),
            GeneratedFile("db.py", self._db_py()),
            GeneratedFile("main.py", self._main_py(schema.bot_name)),
            GeneratedFile("handlers/__init__.py", '"""Generated bot handlers."""\n'),
            GeneratedFile("handlers/generated.py", self._handlers_py()),
            GeneratedFile(".env.example", self._env_example(schema.bot_name)),
        ]

    def _requirements(self) -> str:
        return "\n".join(
            [
                "pyrofork==2.3.68",
                "tgcrypto==1.2.5",
                "",
            ]
        )

    def _env_example(self, bot_name: str) -> str:
        return textwrap.dedent(
            f"""
            # Runtime secrets are normally provided by the builder process.
            GENERATED_BOT_TOKEN=
            TELEGRAM_API_ID=
            TELEGRAM_API_HASH=
            BOT_ADMIN_IDS=
            BOT_DEFAULT_LANGUAGE=en
            BOT_LOG_LEVEL=INFO
            PAYMENT_PROVIDER_TOKEN=
            BOT_NAME={bot_name}
            """
        ).lstrip()

    def _config_py(self) -> str:
        return textwrap.dedent(
            """
            from __future__ import annotations

            import os
            from dataclasses import dataclass
            from pathlib import Path


            BASE_DIR = Path(__file__).resolve().parent


            def _int_env(name: str, default: int = 0) -> int:
                value = os.getenv(name, "").strip()
                return int(value) if value else default


            def _int_list_env(name: str) -> tuple[int, ...]:
                values: list[int] = []
                for raw_item in os.getenv(name, "").split(","):
                    item = raw_item.strip()
                    if item:
                        values.append(int(item))
                return tuple(values)


            @dataclass(frozen=True)
            class Settings:
                bot_token: str
                telegram_api_id: int
                telegram_api_hash: str
                bot_admin_ids: tuple[int, ...]
                default_language: str
                db_path: Path
                log_path: Path
                log_level: str
                session_dir: Path


            def load_settings() -> Settings:
                token = os.getenv("GENERATED_BOT_TOKEN", "").strip()
                if not token:
                    raise RuntimeError("GENERATED_BOT_TOKEN is required")
                api_id = _int_env("TELEGRAM_API_ID")
                if api_id <= 0:
                    raise RuntimeError("TELEGRAM_API_ID is required")
                api_hash = os.getenv("TELEGRAM_API_HASH", "").strip()
                if not api_hash:
                    raise RuntimeError("TELEGRAM_API_HASH is required")
                session_dir = BASE_DIR / "session"
                session_dir.mkdir(parents=True, exist_ok=True)
                return Settings(
                    bot_token=token,
                    telegram_api_id=api_id,
                    telegram_api_hash=api_hash,
                    bot_admin_ids=_int_list_env("BOT_ADMIN_IDS"),
                    default_language=os.getenv("BOT_DEFAULT_LANGUAGE", "en"),
                    db_path=Path(os.getenv("BOT_DB_PATH", str(BASE_DIR / "bot.db"))),
                    log_path=Path(os.getenv("BOT_LOG_PATH", str(BASE_DIR / "bot.log"))),
                    log_level=os.getenv("BOT_LOG_LEVEL", "INFO").upper(),
                    session_dir=session_dir,
                )


            settings = load_settings()
            """
        ).lstrip()

    def _db_py(self) -> str:
        return textwrap.dedent(
            """
            from __future__ import annotations

            import json
            import sqlite3
            import time
            from pathlib import Path

            from config import settings


            def connect() -> sqlite3.Connection:
                settings.db_path.parent.mkdir(parents=True, exist_ok=True)
                conn = sqlite3.connect(settings.db_path)
                conn.row_factory = sqlite3.Row
                conn.execute("PRAGMA journal_mode=WAL")
                return conn


            def init_db() -> None:
                with connect() as conn:
                    conn.executescript(
                        '''
                        CREATE TABLE IF NOT EXISTS users (
                            user_id INTEGER PRIMARY KEY,
                            first_name TEXT NOT NULL DEFAULT '',
                            username TEXT NOT NULL DEFAULT '',
                            created_at REAL NOT NULL,
                            updated_at REAL NOT NULL
                        );

                        CREATE TABLE IF NOT EXISTS user_data (
                            user_id INTEGER NOT NULL,
                            key TEXT NOT NULL,
                            value TEXT NOT NULL,
                            updated_at REAL NOT NULL,
                            PRIMARY KEY(user_id, key),
                            FOREIGN KEY(user_id) REFERENCES users(user_id) ON DELETE CASCADE
                        );

                        CREATE TABLE IF NOT EXISTS conversation_state (
                            user_id INTEGER NOT NULL,
                            flow_id TEXT NOT NULL,
                            step_index INTEGER NOT NULL,
                            data_json TEXT NOT NULL,
                            updated_at REAL NOT NULL,
                            PRIMARY KEY(user_id, flow_id)
                        );

                        CREATE TABLE IF NOT EXISTS received_files (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            user_id INTEGER NOT NULL,
                            media_type TEXT NOT NULL,
                            file_path TEXT NOT NULL,
                            file_unique_id TEXT NOT NULL DEFAULT '',
                            created_at REAL NOT NULL
                        );

                        CREATE TABLE IF NOT EXISTS events (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            user_id INTEGER,
                            chat_id INTEGER,
                            event_type TEXT NOT NULL,
                            payload_json TEXT NOT NULL,
                            created_at REAL NOT NULL
                        );

                        CREATE TABLE IF NOT EXISTS payments (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            user_id INTEGER NOT NULL,
                            currency TEXT NOT NULL,
                            total_amount INTEGER NOT NULL,
                            invoice_payload TEXT NOT NULL,
                            created_at REAL NOT NULL
                        );

                        CREATE TABLE IF NOT EXISTS contacts (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            user_id INTEGER NOT NULL,
                            phone_number TEXT NOT NULL,
                            first_name TEXT NOT NULL DEFAULT '',
                            last_name TEXT NOT NULL DEFAULT '',
                            created_at REAL NOT NULL
                        );

                        CREATE TABLE IF NOT EXISTS locations (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            user_id INTEGER NOT NULL,
                            latitude REAL NOT NULL,
                            longitude REAL NOT NULL,
                            created_at REAL NOT NULL
                        );
                        '''
                    )


            def upsert_user(user_id: int, first_name: str = "", username: str = "") -> None:
                now = time.time()
                with connect() as conn:
                    conn.execute(
                        '''
                        INSERT INTO users(user_id, first_name, username, created_at, updated_at)
                        VALUES(?, ?, ?, ?, ?)
                        ON CONFLICT(user_id) DO UPDATE SET
                            first_name = excluded.first_name,
                            username = excluded.username,
                            updated_at = excluded.updated_at
                        ''',
                        (user_id, first_name or "", username or "", now, now),
                    )


            def set_user_value(user_id: int, key: str, value: str) -> None:
                now = time.time()
                with connect() as conn:
                    conn.execute(
                        '''
                        INSERT INTO user_data(user_id, key, value, updated_at)
                        VALUES(?, ?, ?, ?)
                        ON CONFLICT(user_id, key) DO UPDATE SET
                            value = excluded.value,
                            updated_at = excluded.updated_at
                        ''',
                        (user_id, key, value, now),
                    )


            def get_user_value(user_id: int, key: str) -> str:
                with connect() as conn:
                    row = conn.execute(
                        "SELECT value FROM user_data WHERE user_id = ? AND key = ?",
                        (user_id, key),
                    ).fetchone()
                return row["value"] if row else ""


            def get_user_profile(user_id: int) -> dict[str, str]:
                with connect() as conn:
                    rows = conn.execute(
                        "SELECT key, value FROM user_data WHERE user_id = ? ORDER BY key",
                        (user_id,),
                    ).fetchall()
                return {row["key"]: row["value"] for row in rows}


            def set_conversation_state(user_id: int, flow_id: str, step_index: int, data: dict[str, str]) -> None:
                now = time.time()
                with connect() as conn:
                    conn.execute(
                        '''
                        INSERT INTO conversation_state(user_id, flow_id, step_index, data_json, updated_at)
                        VALUES(?, ?, ?, ?, ?)
                        ON CONFLICT(user_id, flow_id) DO UPDATE SET
                            step_index = excluded.step_index,
                            data_json = excluded.data_json,
                            updated_at = excluded.updated_at
                        ''',
                        (user_id, flow_id, step_index, json.dumps(data, ensure_ascii=True), now),
                    )


            def get_conversation_state(user_id: int, flow_id: str) -> tuple[int, dict[str, str]] | None:
                with connect() as conn:
                    row = conn.execute(
                        '''
                        SELECT step_index, data_json
                        FROM conversation_state
                        WHERE user_id = ? AND flow_id = ?
                        ''',
                        (user_id, flow_id),
                    ).fetchone()
                if row is None:
                    return None
                return int(row["step_index"]), json.loads(row["data_json"])


            def clear_conversation_state(user_id: int, flow_id: str) -> None:
                with connect() as conn:
                    conn.execute(
                        "DELETE FROM conversation_state WHERE user_id = ? AND flow_id = ?",
                        (user_id, flow_id),
                    )


            def add_file(user_id: int, media_type: str, file_path: Path, file_unique_id: str = "") -> None:
                with connect() as conn:
                    conn.execute(
                        '''
                        INSERT INTO received_files(user_id, media_type, file_path, file_unique_id, created_at)
                        VALUES(?, ?, ?, ?, ?)
                        ''',
                        (user_id, media_type, str(file_path), file_unique_id, time.time()),
                    )


            def log_event(user_id: int | None, chat_id: int | None, event_type: str, payload: dict[str, str]) -> None:
                with connect() as conn:
                    conn.execute(
                        '''
                        INSERT INTO events(user_id, chat_id, event_type, payload_json, created_at)
                        VALUES(?, ?, ?, ?, ?)
                        ''',
                        (user_id, chat_id, event_type, json.dumps(payload, ensure_ascii=True), time.time()),
                    )


            def add_payment(user_id: int, currency: str, total_amount: int, invoice_payload: str) -> None:
                with connect() as conn:
                    conn.execute(
                        '''
                        INSERT INTO payments(user_id, currency, total_amount, invoice_payload, created_at)
                        VALUES(?, ?, ?, ?, ?)
                        ''',
                        (user_id, currency, total_amount, invoice_payload, time.time()),
                    )


            def add_contact(user_id: int, phone_number: str, first_name: str, last_name: str) -> None:
                with connect() as conn:
                    conn.execute(
                        '''
                        INSERT INTO contacts(user_id, phone_number, first_name, last_name, created_at)
                        VALUES(?, ?, ?, ?, ?)
                        ''',
                        (user_id, phone_number, first_name, last_name, time.time()),
                    )


            def add_location(user_id: int, latitude: float, longitude: float) -> None:
                with connect() as conn:
                    conn.execute(
                        '''
                        INSERT INTO locations(user_id, latitude, longitude, created_at)
                        VALUES(?, ?, ?, ?)
                        ''',
                        (user_id, latitude, longitude, time.time()),
                    )


            def list_user_ids() -> list[int]:
                with connect() as conn:
                    rows = conn.execute("SELECT user_id FROM users ORDER BY created_at").fetchall()
                return [int(row["user_id"]) for row in rows]
            """
        ).lstrip()

    def _main_py(self, bot_name: str) -> str:
        bot_name_literal = json.dumps(bot_name)
        return textwrap.dedent(
            f"""
            from __future__ import annotations

            import asyncio
            import logging
            from logging.handlers import RotatingFileHandler

            from pyrogram import Client, idle

            import db
            from config import settings
            from handlers.generated import register_handlers, start_schedulers


            def setup_logging() -> None:
                settings.log_path.parent.mkdir(parents=True, exist_ok=True)
                handler = RotatingFileHandler(
                    settings.log_path,
                    maxBytes=2_000_000,
                    backupCount=5,
                    encoding="utf-8",
                )
                formatter = logging.Formatter(
                    "%(asctime)s %(levelname)s %(name)s %(message)s"
                )
                handler.setFormatter(formatter)
                logging.basicConfig(
                    level=getattr(logging, settings.log_level, logging.INFO),
                    handlers=[handler],
                )


            async def main() -> None:
                setup_logging()
                db.init_db()
                app = Client(
                    {bot_name_literal},
                    api_id=settings.telegram_api_id,
                    api_hash=settings.telegram_api_hash,
                    bot_token=settings.bot_token,
                    workdir=str(settings.session_dir),
                )
                register_handlers(app)
                scheduler_tasks = []
                try:
                    await app.start()
                    scheduler_tasks = start_schedulers(app)
                    logging.info("Generated bot started")
                    await idle()
                finally:
                    for task in scheduler_tasks:
                        task.cancel()
                    if scheduler_tasks:
                        await asyncio.gather(*scheduler_tasks, return_exceptions=True)
                    await app.stop()
                    logging.info("Generated bot stopped")


            if __name__ == "__main__":
                asyncio.run(main())
            """
        ).lstrip()

    def _handlers_py(self) -> str:
        return textwrap.dedent(
            r'''
            from __future__ import annotations

            import asyncio
            import json
            import logging
            import os
            import re
            import time
            from datetime import datetime, timedelta, timezone
            from pathlib import Path

            from pyrogram.handlers import CallbackQueryHandler, InlineQueryHandler, MessageHandler
            try:
                from pyrogram.handlers import PreCheckoutQueryHandler
            except ImportError:
                PreCheckoutQueryHandler = None
            from pyrogram.types import InlineQueryResultArticle, InputTextMessageContent, LabeledPrice

            import db
            from config import BASE_DIR, settings


            LOGGER = logging.getLogger("generated.handlers")
            SCHEMA = json.loads((BASE_DIR / "schema.json").read_text(encoding="utf-8"))
            RATE_EVENTS: dict[tuple[int, str], list[float]] = {}


            class SafeDict(dict[str, str]):
                def __missing__(self, key: str) -> str:
                    return "{" + key + "}"


            def enabled_blocks(block_type: str | None = None) -> list[dict[str, object]]:
                blocks: list[dict[str, object]] = []
                for block in SCHEMA.get("blocks", []):
                    if not isinstance(block, dict):
                        continue
                    if block.get("enabled", True) is not True:
                        continue
                    if block_type is None or block.get("type") == block_type:
                        blocks.append(block)
                return blocks


            def message_text(message: object) -> str:
                return str(getattr(message, "text", None) or getattr(message, "caption", None) or "")


            def actor_id(message: object) -> int:
                user = getattr(message, "from_user", None)
                return int(getattr(user, "id", 0) or 0)


            def chat_id(message: object) -> int:
                chat = getattr(message, "chat", None)
                return int(getattr(chat, "id", 0) or 0)


            def chat_type(message: object) -> str:
                chat = getattr(message, "chat", None)
                value = getattr(chat, "type", "")
                raw = getattr(value, "value", value)
                return str(raw)


            def upsert_message_user(message: object) -> None:
                user = getattr(message, "from_user", None)
                if user is not None and getattr(user, "id", None) is not None:
                    db.upsert_user(
                        int(user.id),
                        str(getattr(user, "first_name", "") or ""),
                        str(getattr(user, "username", "") or ""),
                    )


            def scope_matches(block: dict[str, object], message: object) -> bool:
                scope = str(block.get("scope", "all"))
                if scope == "all":
                    return True
                current = chat_type(message)
                if scope == "group":
                    return current in {"group", "supergroup"}
                return current == scope


            def text_matches(block: dict[str, object], text: str, pattern_field: str = "pattern") -> bool:
                mode = str(block.get("match_mode", "contains"))
                pattern = str(block.get(pattern_field, ""))
                candidate = text.strip()
                if mode == "always":
                    return True
                if not pattern:
                    return False
                if mode == "exact":
                    return candidate.casefold() == pattern.casefold()
                if mode in {"contains", "intent"}:
                    return pattern.casefold() in candidate.casefold()
                if mode == "regex":
                    return re.search(pattern, candidate, flags=re.IGNORECASE) is not None
                return False


            def trigger_matches(trigger: str, text: str) -> bool:
                return text.strip().casefold() == trigger.strip().casefold()


            def command_name(text: str) -> tuple[str, list[str]]:
                if not text.startswith("/"):
                    return "", []
                parts = text.split()
                first = parts[0][1:]
                if "@" in first:
                    first = first.split("@", 1)[0]
                return first.casefold(), parts[1:]


            def is_admin(user_id: int, block: dict[str, object] | None = None) -> bool:
                admins = set(int(item) for item in SCHEMA.get("admins", []))
                admins.update(settings.bot_admin_ids)
                if block is not None:
                    admins.update(int(item) for item in block.get("admin_ids", []))
                return user_id in admins


            def render(template: str, message: object | None = None, data: dict[str, str] | None = None) -> str:
                user = getattr(message, "from_user", None) if message is not None else None
                chat = getattr(message, "chat", None) if message is not None else None
                values = SafeDict(
                    user_id=str(getattr(user, "id", "") or ""),
                    first_name=str(getattr(user, "first_name", "") or ""),
                    username=str(getattr(user, "username", "") or ""),
                    chat_id=str(getattr(chat, "id", "") or ""),
                    bot_name=str(SCHEMA.get("display_name", SCHEMA.get("bot_name", ""))),
                    language=str(SCHEMA.get("default_language", settings.default_language)),
                )
                if data:
                    values.update({key: str(value) for key, value in data.items()})
                try:
                    return template.format_map(values)
                except ValueError:
                    return template


            async def check_rate_limit(message: object, block: dict[str, object]) -> bool:
                user_id = actor_id(message)
                if user_id == 0:
                    return True
                for limiter in enabled_blocks("rate_limiter"):
                    applies = [str(item) for item in limiter.get("applies_to", ["*"])]
                    if "*" not in applies and str(block.get("id", "")) not in applies and str(block.get("type", "")) not in applies:
                        continue
                    key = (user_id, str(limiter.get("id", "rate_limiter")))
                    now = time.time()
                    window = int(limiter.get("window_seconds", 30))
                    events = [timestamp for timestamp in RATE_EVENTS.get(key, []) if now - timestamp <= window]
                    if len(events) >= int(limiter.get("max_events", 6)):
                        await message.reply_text(str(limiter.get("action_message", "Please slow down.")))
                        RATE_EVENTS[key] = events
                        return False
                    events.append(now)
                    RATE_EVENTS[key] = events
                return True


            async def handle_error(client: object, message: object | None, exc: BaseException) -> None:
                LOGGER.exception("Handler failed", exc_info=exc)
                user_message = "Something went wrong. Please try again later."
                notify_admins = True
                for block in enabled_blocks("error_handler"):
                    user_message = str(block.get("user_message", user_message))
                    notify_admins = bool(block.get("notify_admins", notify_admins))
                    break
                if message is not None:
                    try:
                        await message.reply_text(user_message)
                    except Exception as reply_exc:
                        LOGGER.exception("Could not notify user about handler failure", exc_info=reply_exc)
                if notify_admins:
                    admin_ids = set(int(item) for item in SCHEMA.get("admins", []))
                    admin_ids.update(settings.bot_admin_ids)
                    for admin_id in admin_ids:
                        try:
                            await client.send_message(admin_id, f"Bot error: {exc}")
                        except Exception as admin_exc:
                            LOGGER.exception("Could not notify admin", exc_info=admin_exc)


            async def run_block(client: object, message: object, block: dict[str, object], handler) -> bool:
                if not scope_matches(block, message):
                    return False
                if not await check_rate_limit(message, block):
                    return True
                try:
                    await handler()
                except Exception as exc:
                    await handle_error(client, message, exc)
                return True


            async def process_command(client: object, message: object, text: str) -> bool:
                name, args = command_name(text)
                if not name:
                    return False
                for block in enabled_blocks("deeplink_handler"):
                    if name == "start":
                        payload = " ".join(args)
                        for action in block.get("payload_actions", []):
                            pattern = str(action.get("pattern", ""))
                            if re.search(pattern, payload):
                                async def respond(action=action, payload=payload) -> None:
                                    store_key = action.get("store_key")
                                    if store_key:
                                        db.set_user_value(actor_id(message), str(store_key), payload)
                                    await message.reply_text(render(str(action.get("response", "")), message, {"payload": payload}))
                                return await run_block(client, message, block, respond)
                        async def default_response(block=block) -> None:
                            await message.reply_text(render(str(block.get("default_response", "Welcome.")), message))
                        return await run_block(client, message, block, default_response)
                for block in enabled_blocks("command_handler"):
                    commands = [str(block.get("command", "")).casefold()]
                    commands.extend(str(alias).casefold() for alias in block.get("aliases", []))
                    if name in commands:
                        async def respond(block=block) -> None:
                            if bool(block.get("persist_user", True)):
                                db.log_event(actor_id(message), chat_id(message), "command", {"command": name})
                            await message.reply_text(render(str(block.get("response", "")), message))
                        return await run_block(client, message, block, respond)
                return False


            async def process_conversations(client: object, message: object, text: str) -> bool:
                user_id = actor_id(message)
                if user_id == 0:
                    return False
                normalized = text.strip().casefold()
                for block in enabled_blocks("conversation_flow"):
                    state = db.get_conversation_state(user_id, str(block.get("id", "")))
                    steps = list(block.get("steps", []))
                    cancel_words = [str(item).casefold() for item in block.get("cancel_words", [])]
                    if state is None:
                        triggers = [str(item).casefold() for item in block.get("entry_triggers", [])]
                        if normalized not in triggers:
                            continue
                        async def start_flow(block=block, steps=steps) -> None:
                            first_step = steps[0]
                            db.set_conversation_state(user_id, str(block.get("id", "")), 0, {})
                            await message.reply_text(str(first_step.get("prompt", "")))
                        return await run_block(client, message, block, start_flow)
                    step_index, data = state
                    if normalized in cancel_words:
                        async def cancel_flow(block=block) -> None:
                            db.clear_conversation_state(user_id, str(block.get("id", "")))
                            await message.reply_text("Okay, cancelled.")
                        return await run_block(client, message, block, cancel_flow)
                    if step_index >= len(steps):
                        db.clear_conversation_state(user_id, str(block.get("id", "")))
                        return False
                    step = steps[step_index]
                    validation_regex = str(step.get("validation_regex") or "")
                    if validation_regex and re.fullmatch(validation_regex, text.strip()) is None:
                        await message.reply_text(str(step.get("retry_message", "Please try again.")))
                        return True
                    async def continue_flow(block=block, steps=steps, step=step, step_index=step_index, data=data) -> None:
                        data[str(step.get("data_key", step.get("key", "value")))] = text.strip()
                        next_index = step_index + 1
                        if next_index >= len(steps):
                            db.clear_conversation_state(user_id, str(block.get("id", "")))
                            for key, value in data.items():
                                db.set_user_value(user_id, key, value)
                            await message.reply_text(render(str(block.get("final_response", "Done.")), message, data))
                        else:
                            db.set_conversation_state(user_id, str(block.get("id", "")), next_index, data)
                            await message.reply_text(str(steps[next_index].get("prompt", "")))
                    return await run_block(client, message, block, continue_flow)
                return False


            async def process_user_data(message: object, text: str) -> bool:
                user_id = actor_id(message)
                if user_id == 0:
                    return False
                for block in enabled_blocks("user_data_store"):
                    fields = list(block.get("fields", []))
                    normalized = text.strip().casefold()
                    if bool(block.get("expose_profile_command", True)) and normalized in {"profile", "/profile", "my profile"}:
                        profile = db.get_user_profile(user_id)
                        if profile:
                            lines = [f"{key}: {value}" for key, value in sorted(profile.items())]
                            await message.reply_text("\n".join(lines))
                        else:
                            await message.reply_text("No profile data saved yet.")
                        return True
                    for field in fields:
                        key = str(field.get("key", ""))
                        prefix = f"set {key} "
                        if normalized.startswith(prefix.casefold()):
                            value = text.strip()[len(prefix):].strip()
                            db.set_user_value(user_id, key, value)
                            await message.reply_text(f"Saved {key}.")
                            return True
                return False


            async def process_admin_panel(message: object, text: str) -> bool:
                user_id = actor_id(message)
                name, _args = command_name(text)
                normalized = text.strip().casefold()
                for block in enabled_blocks("admin_panel"):
                    if not is_admin(user_id, block):
                        continue
                    for command in block.get("commands", []):
                        command_name_value = str(command.get("name", "")).casefold()
                        if name == command_name_value or normalized == command_name_value:
                            await message.reply_text(render(str(command.get("response", "")), message))
                            return True
                return False


            async def process_broadcast(client: object, message: object, text: str) -> bool:
                user_id = actor_id(message)
                for block in enabled_blocks("broadcast"):
                    if not is_admin(user_id, block):
                        continue
                    trigger = str(block.get("trigger_text", "broadcast"))
                    if not text.strip().casefold().startswith(trigger.casefold()):
                        continue
                    payload = text.strip()[len(trigger):].strip()
                    template = payload or str(block.get("message_template", ""))
                    sent = 0
                    for target_user_id in db.list_user_ids():
                        try:
                            await client.send_message(target_user_id, render(template, message))
                            sent += 1
                        except Exception as exc:
                            LOGGER.exception("Broadcast failed for %s", target_user_id, exc_info=exc)
                    await message.reply_text(f"Broadcast sent to {sent} users.")
                    return True
                return False


            async def process_text_blocks(client: object, message: object, text: str) -> bool:
                if await process_command(client, message, text):
                    return True
                if await process_conversations(client, message, text):
                    return True
                if await process_admin_panel(message, text):
                    return True
                if await process_broadcast(client, message, text):
                    return True
                if await process_user_data(message, text):
                    return True
                for block in enabled_blocks("text_handler"):
                    if text_matches(block, text):
                        async def respond(block=block) -> None:
                            if bool(block.get("persist_interaction", True)):
                                db.log_event(actor_id(message), chat_id(message), "text", {"text": text[:512]})
                            await message.reply_text(render(str(block.get("response", "")), message))
                        return await run_block(client, message, block, respond)
                for block in enabled_blocks("media_sender"):
                    if trigger_matches(str(block.get("trigger_text", "")), text):
                        async def send_media(block=block) -> None:
                            media_type = str(block.get("media_type", "photo"))
                            source = str(block.get("source", ""))
                            caption = render(str(block.get("caption", "")), message)
                            send_method = getattr(client, f"send_{media_type}", None)
                            if send_method is None:
                                await message.reply_text("This media type cannot be sent by the current runtime.")
                                return
                            kwargs = {"chat_id": chat_id(message), media_type: source}
                            if caption and media_type != "sticker":
                                kwargs["caption"] = caption
                            await send_method(**kwargs)
                        return await run_block(client, message, block, send_media)
                for block in enabled_blocks("poll_creator"):
                    if trigger_matches(str(block.get("trigger_text", "")), text):
                        async def send_poll(block=block) -> None:
                            await message.reply_poll(
                                question=str(block.get("question", "")),
                                options=[str(item) for item in block.get("options", [])],
                                is_anonymous=bool(block.get("is_anonymous", False)),
                                allows_multiple_answers=bool(block.get("allows_multiple_answers", False)),
                            )
                        return await run_block(client, message, block, send_poll)
                for block in enabled_blocks("quiz_creator"):
                    if trigger_matches(str(block.get("trigger_text", "")), text):
                        async def send_quiz(block=block) -> None:
                            await message.reply_poll(
                                question=str(block.get("question", "")),
                                options=[str(item) for item in block.get("options", [])],
                                type="quiz",
                                correct_option_id=int(block.get("correct_option_id", 0)),
                                explanation=str(block.get("explanation", "")) or None,
                                is_anonymous=False,
                            )
                        return await run_block(client, message, block, send_quiz)
                for block in enabled_blocks("dice_roller"):
                    if trigger_matches(str(block.get("trigger_text", "")), text):
                        async def send_dice(block=block) -> None:
                            await message.reply_dice(emoji=str(block.get("emoji", "\U0001F3B2")))
                        return await run_block(client, message, block, send_dice)
                for block in enabled_blocks("sticker_set_handler"):
                    if trigger_matches(str(block.get("trigger_text", "")), text):
                        async def send_sticker_set(block=block) -> None:
                            sticker_set = await client.get_sticker_set(str(block.get("sticker_set_name", "")))
                            await message.reply_text(render(str(block.get("response", "Here is the sticker set.")), message))
                            stickers = list(getattr(sticker_set, "stickers", []) or [])
                            if bool(block.get("send_first_sticker", True)) and stickers:
                                await message.reply_sticker(stickers[0].file_id)
                        return await run_block(client, message, block, send_sticker_set)
                for block in enabled_blocks("game_handler"):
                    if trigger_matches(str(block.get("trigger_text", "")), text):
                        async def send_game(block=block) -> None:
                            try:
                                await client.send_game(chat_id(message), str(block.get("game_short_name", "")))
                            except Exception as exc:
                                LOGGER.exception("Game launch failed", exc_info=exc)
                                await message.reply_text(str(block.get("fallback_text", "Launching the game.")))
                        return await run_block(client, message, block, send_game)
                for block in enabled_blocks("payment_handler"):
                    if trigger_matches(str(block.get("trigger_text", "")), text):
                        async def send_invoice(block=block) -> None:
                            provider_token = os.getenv(str(block.get("provider_token_env", "PAYMENT_PROVIDER_TOKEN")), "")
                            if not provider_token:
                                await message.reply_text("Payment provider is not configured.")
                                return
                            prices = [
                                LabeledPrice(label=str(item.get("label", "")), amount=int(item.get("amount_minor_units", 0)))
                                for item in block.get("prices", [])
                            ]
                            await client.send_invoice(
                                chat_id(message),
                                title=str(block.get("title", "")),
                                description=str(block.get("description_text", "")),
                                payload=str(block.get("payload", "")),
                                provider_token=provider_token,
                                currency=str(block.get("currency", "USD")),
                                prices=prices,
                                start_parameter=str(block.get("start_parameter", "checkout")),
                            )
                        return await run_block(client, message, block, send_invoice)
                return False


            def media_file(message: object, media_type: str) -> object | None:
                return getattr(message, media_type, None)


            async def process_media_blocks(client: object, message: object) -> bool:
                handled = False
                for block in enabled_blocks("file_downloader") + enabled_blocks("media_handler"):
                    for media_type in [str(item) for item in block.get("media_types", [])]:
                        telegram_file = media_file(message, media_type)
                        if telegram_file is None:
                            continue
                        async def handle_media(block=block, media_type=media_type, telegram_file=telegram_file) -> None:
                            should_save = bool(block.get("save_files", False)) or block.get("type") == "file_downloader"
                            if should_save:
                                directory = BASE_DIR / str(block.get("directory", "downloads"))
                                directory.mkdir(parents=True, exist_ok=True)
                                path = await message.download(file_name=str(directory / ""))
                                db.add_file(
                                    actor_id(message),
                                    media_type,
                                    Path(path),
                                    str(getattr(telegram_file, "file_unique_id", "") or ""),
                                )
                            if block.get("type") == "file_downloader":
                                if bool(block.get("notify_user", True)):
                                    await message.reply_text("File saved.")
                            else:
                                if bool(block.get("store_metadata", True)):
                                    db.log_event(actor_id(message), chat_id(message), "media", {"media_type": media_type})
                                await message.reply_text(render(str(block.get("response", "")), message))
                        handled = await run_block(client, message, block, handle_media)
                        if handled:
                            return True
                return handled


            async def process_service_messages(client: object, message: object) -> bool:
                new_members = getattr(message, "new_chat_members", None)
                if new_members:
                    for block in enabled_blocks("welcome_handler"):
                        async def welcome(block=block) -> None:
                            text = str(block.get("message", "Welcome."))
                            if bool(block.get("include_rules", False)) and block.get("rules_text"):
                                text = text + "\n\n" + str(block.get("rules_text", ""))
                            await message.reply_text(render(text, message))
                        return await run_block(client, message, block, welcome)
                    for block in enabled_blocks("chat_member_handler"):
                        if block.get("on_join_message"):
                            async def member_join(block=block) -> None:
                                if bool(block.get("track_members", True)):
                                    for member in new_members:
                                        db.log_event(
                                            int(getattr(member, "id", 0) or 0),
                                            chat_id(message),
                                            "member_join",
                                            {"first_name": str(getattr(member, "first_name", "") or "")},
                                        )
                                await message.reply_text(render(str(block.get("on_join_message", "")), message))
                            return await run_block(client, message, block, member_join)
                left_member = getattr(message, "left_chat_member", None)
                if left_member:
                    for block in enabled_blocks("chat_member_handler"):
                        if block.get("on_leave_message"):
                            async def member_leave(block=block) -> None:
                                if bool(block.get("track_members", True)):
                                    db.log_event(
                                        int(getattr(left_member, "id", 0) or 0),
                                        chat_id(message),
                                        "member_leave",
                                        {"first_name": str(getattr(left_member, "first_name", "") or "")},
                                    )
                                await message.reply_text(render(str(block.get("on_leave_message", "")), message))
                            return await run_block(client, message, block, member_leave)
                return False


            async def process_special_messages(client: object, message: object) -> bool:
                if getattr(message, "successful_payment", None) is not None:
                    payment = message.successful_payment
                    db.add_payment(
                        actor_id(message),
                        str(getattr(payment, "currency", "")),
                        int(getattr(payment, "total_amount", 0)),
                        str(getattr(payment, "invoice_payload", "")),
                    )
                    for block in enabled_blocks("payment_handler"):
                        await message.reply_text(render(str(block.get("successful_payment_message", "Payment received.")), message))
                        return True
                if getattr(message, "location", None) is not None:
                    location = message.location
                    for block in enabled_blocks("location_handler"):
                        async def location_handler(block=block) -> None:
                            if bool(block.get("store_location", True)):
                                db.add_location(actor_id(message), float(location.latitude), float(location.longitude))
                            await message.reply_text(render(str(block.get("response", "")), message))
                        return await run_block(client, message, block, location_handler)
                if getattr(message, "contact", None) is not None:
                    contact = message.contact
                    for block in enabled_blocks("contact_handler"):
                        async def contact_handler(block=block) -> None:
                            if bool(block.get("store_contact", True)):
                                db.add_contact(
                                    actor_id(message),
                                    str(getattr(contact, "phone_number", "") or ""),
                                    str(getattr(contact, "first_name", "") or ""),
                                    str(getattr(contact, "last_name", "") or ""),
                                )
                            await message.reply_text(render(str(block.get("response", "")), message))
                        return await run_block(client, message, block, contact_handler)
                if getattr(message, "forward_from", None) is not None or getattr(message, "forward_sender_name", None):
                    for block in enabled_blocks("forwarded_message_handler"):
                        if bool(block.get("require_original_sender", False)) and getattr(message, "forward_from", None) is None:
                            continue
                        async def forwarded_handler(block=block) -> None:
                            db.log_event(actor_id(message), chat_id(message), "forwarded_message", {"text": message_text(message)[:512]})
                            await message.reply_text(render(str(block.get("response", "")), message))
                        return await run_block(client, message, block, forwarded_handler)
                if chat_type(message) == "channel":
                    for block in enabled_blocks("channel_post_handler"):
                        text = message_text(message)
                        if text_matches(block, text):
                            async def channel_handler(block=block, text=text) -> None:
                                if bool(block.get("log_posts", True)):
                                    db.log_event(None, chat_id(message), "channel_post", {"text": text[:512]})
                                response = str(block.get("response", ""))
                                if response:
                                    await message.reply_text(render(response, message))
                            return await run_block(client, message, block, channel_handler)
                return False


            async def message_router(client: object, message: object) -> None:
                try:
                    upsert_message_user(message)
                    if await process_service_messages(client, message):
                        return
                    if await process_special_messages(client, message):
                        return
                    if await process_media_blocks(client, message):
                        return
                    text = message_text(message)
                    if text and await process_text_blocks(client, message, text):
                        return
                except Exception as exc:
                    await handle_error(client, message, exc)


            async def callback_router(client: object, callback_query: object) -> None:
                try:
                    data = str(getattr(callback_query, "data", "") or "")
                    message = getattr(callback_query, "message", None)
                    for block in enabled_blocks("callback_query_handler"):
                        if re.search(str(block.get("callback_data_pattern", "")), data):
                            if bool(block.get("edit_message", False)) and message is not None:
                                await message.edit_text(render(str(block.get("response", "")), message, {"callback_data": data}))
                            else:
                                await callback_query.answer(
                                    render(str(block.get("response", "")), message, {"callback_data": data}),
                                    show_alert=bool(block.get("answer_alert", False)),
                                )
                            return
                    await callback_query.answer()
                except Exception as exc:
                    await handle_error(client, getattr(callback_query, "message", None), exc)


            async def inline_router(client: object, inline_query: object) -> None:
                try:
                    query = str(getattr(inline_query, "query", "") or "")
                    results = []
                    for block in enabled_blocks("inline_query_handler"):
                        if not text_matches(block, query):
                            continue
                        for result in block.get("results", []):
                            results.append(
                                InlineQueryResultArticle(
                                    id=str(result.get("result_id", "")),
                                    title=str(result.get("title", "")),
                                    description=str(result.get("description", "")),
                                    input_message_content=InputTextMessageContent(str(result.get("message_text", ""))),
                                )
                            )
                    await inline_query.answer(results, cache_time=1, is_personal=True)
                except Exception as exc:
                    LOGGER.exception("Inline query failed", exc_info=exc)


            async def precheckout_router(client: object, pre_checkout_query: object) -> None:
                try:
                    await pre_checkout_query.answer(ok=True)
                except Exception as exc:
                    LOGGER.exception("Pre-checkout query failed", exc_info=exc)


            async def scheduler_loop(client: object, block: dict[str, object]) -> None:
                if bool(block.get("run_on_start", False)) and block.get("target_chat_id") is not None:
                    await client.send_message(int(block["target_chat_id"]), render(str(block.get("message", ""))))
                while True:
                    try:
                        if block.get("interval_seconds") is not None:
                            await asyncio.sleep(int(block.get("interval_seconds", 60)))
                        else:
                            now = datetime.now(timezone.utc)
                            target = now.replace(
                                hour=int(block.get("daily_hour_utc", 0)),
                                minute=int(block.get("daily_minute_utc", 0)),
                                second=0,
                                microsecond=0,
                            )
                            if target <= now:
                                target = target + timedelta(days=1)
                            await asyncio.sleep((target - now).total_seconds())
                        if block.get("target_chat_id") is not None:
                            await client.send_message(int(block["target_chat_id"]), render(str(block.get("message", ""))))
                    except asyncio.CancelledError:
                        raise
                    except Exception as exc:
                        await handle_error(client, None, exc)


            def register_handlers(app: object) -> None:
                app.add_handler(MessageHandler(message_router), group=0)
                app.add_handler(CallbackQueryHandler(callback_router), group=1)
                app.add_handler(InlineQueryHandler(inline_router), group=1)
                if PreCheckoutQueryHandler is not None and enabled_blocks("payment_handler"):
                    app.add_handler(PreCheckoutQueryHandler(precheckout_router), group=1)


            def start_schedulers(app: object) -> list[asyncio.Task[None]]:
                tasks: list[asyncio.Task[None]] = []
                for block in enabled_blocks("scheduler"):
                    tasks.append(asyncio.create_task(scheduler_loop(app, block)))
                return tasks
            '''
        ).lstrip()
