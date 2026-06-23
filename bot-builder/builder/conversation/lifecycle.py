from __future__ import annotations

import json
import re
import shutil
from dataclasses import dataclass
from pathlib import Path

from builder.ai.parser import parse_json_object
from builder.ai.prompts import lifecycle_intent_prompt
from builder.codegen.scaffolder import BotScaffolder
from builder.db import BotRecord, BuilderDatabase
from builder.process.manager import BotProcessManager
from builder.schema.blocks import BotSchema
from builder.schema.validator import SchemaValidator


@dataclass(frozen=True)
class LifecycleReply:
    handled: bool
    text: str
    document_path: Path | None = None


class LifecycleService:
    def __init__(
        self,
        db: BuilderDatabase,
        manager: BotProcessManager,
        validator: SchemaValidator,
        scaffolder: BotScaffolder,
        gemini_client: object,
    ) -> None:
        self.db = db
        self.manager = manager
        self.validator = validator
        self.scaffolder = scaffolder
        self.gemini_client = gemini_client

    async def handle(self, user_id: int, text: str, is_super_admin: bool) -> LifecycleReply:
        owned_bots = self.db.list_bots(user_id)
        intent = await self._intent(text, [bot.bot_name for bot in owned_bots])
        kind = str(intent.get("intent", "none"))
        if kind == "none":
            return LifecycleReply(False, "")
        if kind == "list":
            return LifecycleReply(True, self._list_bots(user_id, is_super_admin, text))
        if not owned_bots:
            return LifecycleReply(False, "")
        bot = self._resolve_bot(user_id, str(intent.get("bot_name", "")))
        if bot is None:
            return LifecycleReply(True, "I could not tell which bot you mean. Please mention its name.")
        if kind == "start":
            pid = self.manager.start(bot)
            return LifecycleReply(True, f"{bot.bot_name} is running with PID {pid}.")
        if kind == "stop":
            self.manager.stop(bot)
            return LifecycleReply(True, f"{bot.bot_name} is stopped.")
        if kind == "restart":
            pid = self.manager.restart(bot)
            return LifecycleReply(True, f"{bot.bot_name} restarted with PID {pid}.")
        if kind == "delete":
            self.manager.stop(bot)
            if bot.directory.exists():
                shutil.rmtree(bot.directory)
            self.db.delete_bot(bot.bot_id)
            return LifecycleReply(True, f"{bot.bot_name} has been deleted.")
        if kind == "logs":
            line_count = int(intent.get("tail_lines", 80))
            logs = self.manager.tail_logs(bot, max(20, min(line_count, 500)))
            if len(logs) > 3500:
                log_copy = bot.directory / "last-requested.log"
                log_copy.write_text(logs, encoding="utf-8")
                return LifecycleReply(True, f"Here are the last {line_count} log lines for {bot.bot_name}.", log_copy)
            return LifecycleReply(True, f"Logs for {bot.bot_name}:\n\n{logs}")
        if kind == "update":
            return await self._update_bot(user_id, bot, str(intent.get("details", text)))
        return LifecycleReply(False, "")

    async def _intent(self, text: str, owned_bot_names: list[str]) -> dict[str, object]:
        try:
            raw = await self.gemini_client.generate_json(lifecycle_intent_prompt(text, owned_bot_names))
            parsed = parse_json_object(raw)
            if "intent" in parsed:
                return parsed
        except Exception:
            return self._fallback_intent(text, owned_bot_names)
        return self._fallback_intent(text, owned_bot_names)

    def _fallback_intent(self, text: str, owned_bot_names: list[str]) -> dict[str, object]:
        normalized = text.casefold()
        intent = "none"

        def contains_phrase(phrases: list[str]) -> bool:
            for phrase in phrases:
                if " " in phrase and phrase in normalized:
                    return True
                if " " not in phrase and re.search(rf"\b{re.escape(phrase)}\b", normalized):
                    return True
            return False

        if contains_phrase(["list", "show my bots", "what bots", "all bots"]):
            intent = "list"
        elif contains_phrase(["restart"]):
            intent = "restart"
        elif contains_phrase(["stop", "pause", "shut down"]):
            intent = "stop"
        elif contains_phrase(["start", "run", "turn on"]):
            intent = "start"
        elif contains_phrase(["delete", "remove"]):
            intent = "delete"
        elif contains_phrase(["log", "logs", "crash", "error"]):
            intent = "logs"
        elif contains_phrase(["update", "change", "add", "modify", "regenerate"]):
            intent = "update"
        bot_name = ""
        for name in owned_bot_names:
            if name.casefold() in normalized:
                bot_name = name
                break
        tail_match = re.search(r"(\d+)\s+lines", normalized)
        tail_lines = int(tail_match.group(1)) if tail_match else 80
        return {"intent": intent, "bot_name": bot_name, "details": text, "tail_lines": tail_lines}

    def _list_bots(self, user_id: int, is_super_admin: bool, text: str) -> str:
        show_all = is_super_admin and "all" in text.casefold()
        bots = self.db.list_bots(None if show_all else user_id)
        if not bots:
            return "No bots are registered yet."
        lines = ["Bots:"]
        for bot in bots:
            owner = f" owner {bot.owner_user_id}" if show_all else ""
            pid = f", PID {bot.pid}" if bot.pid else ""
            lines.append(f"- {bot.bot_name}: {bot.status}{pid}{owner}")
        return "\n".join(lines)

    def _resolve_bot(self, user_id: int, bot_name: str) -> BotRecord | None:
        return self.db.find_owned_bot(user_id, bot_name)

    async def _update_bot(self, user_id: int, bot: BotRecord, details: str) -> LifecycleReply:
        current_schema = BotSchema.model_validate_json(bot.schema_json)
        if any(phrase in details.casefold() for phrase in ["from scratch", "regenerate", "rebuild completely"]):
            next_schema = await self.validator.generate_from_spec(details)
        else:
            next_schema = await self.validator.patch_schema(current_schema, details)
        bot_dir = self.scaffolder.write_bot(user_id, next_schema, bot.directory)
        self.db.update_bot_schema(bot.bot_id, next_schema.model_dump_json(indent=2), bot_dir)
        fresh = self.db.get_bot_by_id(bot.bot_id)
        if fresh is None:
            return LifecycleReply(True, "The update was written, but I could not reload the bot record.")
        if bot.status == "running":
            pid = self.manager.restart(fresh)
            return LifecycleReply(True, f"{bot.bot_name} was updated and restarted with PID {pid}.")
        return LifecycleReply(True, f"{bot.bot_name} was updated. It is still stopped.")
