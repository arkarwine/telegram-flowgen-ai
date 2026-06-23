from __future__ import annotations

import asyncio
import logging
from logging.handlers import RotatingFileHandler

from pyrogram import Client, idle
from pyrogram.handlers import MessageHandler

from builder.ai.gemini import GeminiClient
from builder.codegen.scaffolder import BotScaffolder
from builder.config import Settings, load_settings
from builder.conversation.discovery import BuilderConversation
from builder.conversation.lifecycle import LifecycleService
from builder.db import BuilderDatabase
from builder.process.manager import BotProcessManager
from builder.process.watchdog import Watchdog
from builder.schema.validator import SchemaValidator


def setup_logging(settings: Settings) -> None:
    log_path = settings.project_root / "builder.log"
    handler = RotatingFileHandler(log_path, maxBytes=3_000_000, backupCount=5, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    logging.basicConfig(level=getattr(logging, settings.log_level, logging.INFO), handlers=[handler])


async def main() -> None:
    settings = load_settings()
    setup_logging(settings)
    settings.bots_dir.mkdir(parents=True, exist_ok=True)
    (settings.project_root / "session").mkdir(parents=True, exist_ok=True)

    db = BuilderDatabase(settings.builder_db_path)
    db.init()
    gemini = GeminiClient(settings)
    validator = SchemaValidator(gemini)
    scaffolder = BotScaffolder(settings.bots_dir)
    manager = BotProcessManager(settings, db)
    lifecycle = LifecycleService(db, manager, validator, scaffolder, gemini)
    conversation = BuilderConversation(settings, db, manager, validator, scaffolder, lifecycle, gemini)

    app = Client(
        "builder",
        api_id=settings.telegram_api_id,
        api_hash=settings.telegram_api_hash,
        bot_token=settings.builder_token,
        workdir=str(settings.project_root / "session"),
    )

    async def on_message(client: Client, message: object) -> None:
        try:
            await conversation.handle(client, message)
        except Exception as exc:
            logging.exception("Builder conversation failed", exc_info=exc)
            try:
                await message.reply_text(f"I hit an internal error while handling that: {exc}")
            except Exception:
                return

    app.add_handler(MessageHandler(on_message), group=0)
    watchdog = Watchdog(settings, db, manager, app)
    watchdog_task: asyncio.Task[None] | None = None
    try:
        await app.start()
        await watchdog.restore_running_bots()
        watchdog_task = asyncio.create_task(watchdog.run())
        logging.info("Builder bot started")
        await idle()
    finally:
        if watchdog_task is not None:
            watchdog_task.cancel()
            await asyncio.gather(watchdog_task, return_exceptions=True)
        await app.stop()
        logging.info("Builder bot stopped")


if __name__ == "__main__":
    asyncio.run(main())
