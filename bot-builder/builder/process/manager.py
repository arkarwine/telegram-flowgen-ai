from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

from builder.config import Settings, decrypt_token
from builder.db import BotRecord, BuilderDatabase


class BotProcessManager:
    def __init__(self, settings: Settings, db: BuilderDatabase) -> None:
        self.settings = settings
        self.db = db
        self.processes: dict[str, subprocess.Popen[str]] = {}

    def start(self, bot: BotRecord) -> int:
        live = self.processes.get(bot.bot_id)
        if live is not None and live.poll() is None:
            self.db.update_bot_status(bot.bot_id, "running", live.pid)
            return live.pid

        bot.directory.mkdir(parents=True, exist_ok=True)
        log_path = bot.directory / "bot.log"
        env = self._child_env(bot, log_path)
        creation_kwargs: dict[str, object] = {}
        if os.name != "nt":
            creation_kwargs["start_new_session"] = True
        with log_path.open("a", encoding="utf-8") as log_handle:
            process = subprocess.Popen(
                [sys.executable, "main.py"],
                cwd=bot.directory,
                env=env,
                stdout=log_handle,
                stderr=subprocess.STDOUT,
                text=True,
                **creation_kwargs,
            )
        self.processes[bot.bot_id] = process
        self.db.update_bot_status(bot.bot_id, "running", process.pid)
        return process.pid

    def stop(self, bot: BotRecord, timeout_seconds: int = 15) -> None:
        process = self.processes.get(bot.bot_id)
        pid = process.pid if process is not None else bot.pid
        if pid is None:
            self.db.update_bot_status(bot.bot_id, "stopped", None)
            return
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=timeout_seconds)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=timeout_seconds)
        elif self._pid_is_alive(pid):
            self._terminate_pid(pid)
        self.processes.pop(bot.bot_id, None)
        self.db.update_bot_status(bot.bot_id, "stopped", None)

    def restart(self, bot: BotRecord) -> int:
        self.stop(bot)
        fresh = self.db.get_bot_by_id(bot.bot_id)
        if fresh is None:
            raise RuntimeError("Bot disappeared before restart")
        return self.start(fresh)

    def is_alive(self, bot: BotRecord) -> bool:
        process = self.processes.get(bot.bot_id)
        if process is not None:
            return process.poll() is None
        return bot.pid is not None and self._pid_is_alive(bot.pid)

    def tail_logs(self, bot: BotRecord, line_count: int = 80) -> str:
        log_path = bot.directory / "bot.log"
        if not log_path.exists():
            return "No log file exists yet."
        lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
        return "\n".join(lines[-line_count:]) or "The log file is empty."

    def _child_env(self, bot: BotRecord, log_path: Path) -> dict[str, str]:
        env = os.environ.copy()
        schema = json.loads(bot.schema_json)
        schema_admins = ",".join(str(item) for item in schema.get("admins", []))
        env.update(
            {
                "GENERATED_BOT_TOKEN": decrypt_token(bot.token_encrypted, self.settings),
                "TELEGRAM_API_ID": str(self.settings.telegram_api_id),
                "TELEGRAM_API_HASH": self.settings.telegram_api_hash,
                "BOT_DB_PATH": str(bot.directory / "bot.db"),
                "BOT_LOG_PATH": str(log_path),
                "BOT_LOG_LEVEL": self.settings.log_level,
                "BOT_ADMIN_IDS": schema_admins,
                "BOT_DEFAULT_LANGUAGE": str(schema.get("default_language", "en")),
            }
        )
        return env

    def _pid_is_alive(self, pid: int) -> bool:
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False

    def _terminate_pid(self, pid: int) -> None:
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError:
            return
        deadline = time.time() + 10
        while time.time() < deadline:
            if not self._pid_is_alive(pid):
                return
            time.sleep(0.2)
        try:
            os.kill(pid, signal.SIGKILL)
        except OSError:
            return
