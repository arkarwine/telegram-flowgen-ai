from __future__ import annotations

import asyncio
import time

from builder.config import Settings
from builder.db import BuilderDatabase
from builder.process.manager import BotProcessManager


class Watchdog:
    def __init__(
        self,
        settings: Settings,
        db: BuilderDatabase,
        manager: BotProcessManager,
        builder_app: object,
    ) -> None:
        self.settings = settings
        self.db = db
        self.manager = manager
        self.builder_app = builder_app

    async def restore_running_bots(self) -> None:
        for bot in self.db.list_running_bots():
            try:
                self.manager.start(bot)
                await self._notify(bot.owner_user_id, f"{bot.bot_name} was restored and is running.")
            except Exception as exc:
                self.db.update_bot_status(bot.bot_id, "crashed", None, str(exc))
                await self._notify(bot.owner_user_id, f"{bot.bot_name} could not be restored: {exc}")

    async def run(self) -> None:
        while True:
            await asyncio.sleep(self.settings.watchdog_interval_seconds)
            await self.check_once()

    async def check_once(self) -> None:
        for bot in self.db.list_running_bots():
            if self.manager.is_alive(bot):
                continue
            await self._handle_crash(bot)

    async def _handle_crash(self, bot) -> None:
        now = time.time()
        window_start = bot.crash_window_started_at
        if window_start is None or now - window_start > self.settings.restart_window_seconds:
            window_start = now
            restart_count = 0
        else:
            restart_count = bot.restart_count
        if restart_count >= self.settings.max_restarts_per_window:
            self.db.update_restart_window(
                bot.bot_id,
                restart_count,
                window_start,
                status="crashed",
                last_error="Restart limit exceeded",
            )
            await self._notify(
                bot.owner_user_id,
                f"{bot.bot_name} crashed repeatedly and has been marked crashed. Ask me for its logs when you want to inspect it.",
            )
            return
        restart_count += 1
        self.db.update_restart_window(bot.bot_id, restart_count, window_start, status="running")
        fresh = self.db.get_bot_by_id(bot.bot_id)
        if fresh is None:
            return
        try:
            self.manager.start(fresh)
            await self._notify(bot.owner_user_id, f"{bot.bot_name} crashed and was restarted.")
        except Exception as exc:
            self.db.update_restart_window(
                bot.bot_id,
                restart_count,
                window_start,
                status="crashed",
                last_error=str(exc),
            )
            await self._notify(bot.owner_user_id, f"{bot.bot_name} crashed and could not restart: {exc}")

    async def _notify(self, user_id: int, text: str) -> None:
        try:
            await self.builder_app.send_message(user_id, text)
        except Exception:
            return

