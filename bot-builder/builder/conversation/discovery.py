from __future__ import annotations

import re

from builder.ai.prompts import confirmation_summary_prompt, discovery_question_prompt
from builder.codegen.scaffolder import BotScaffolder
from builder.config import Settings, encrypt_token
from builder.conversation.confirmation import looks_like_approval, looks_like_correction
from builder.conversation.lifecycle import LifecycleService
from builder.db import BuilderDatabase
from builder.process.manager import BotProcessManager
from builder.schema.blocks import BotSchema
from builder.schema.validator import SchemaValidator


BOT_TOKEN_RE = re.compile(r"^\d{6,}:[A-Za-z0-9_-]{20,}$")


class BuilderConversation:
    def __init__(
        self,
        settings: Settings,
        db: BuilderDatabase,
        manager: BotProcessManager,
        validator: SchemaValidator,
        scaffolder: BotScaffolder,
        lifecycle: LifecycleService,
        gemini_client: object,
    ) -> None:
        self.settings = settings
        self.db = db
        self.manager = manager
        self.validator = validator
        self.scaffolder = scaffolder
        self.lifecycle = lifecycle
        self.gemini_client = gemini_client

    async def handle(self, client: object, message: object) -> None:
        user = getattr(message, "from_user", None)
        text = str(getattr(message, "text", "") or "").strip()
        if user is None or not text:
            return
        user_id = int(user.id)
        self.db.ensure_user(user_id)
        conversation = self.db.get_conversation(user_id)
        phase = conversation[0] if conversation else "discovery"
        state = conversation[1] if conversation else {"history": []}

        if phase == "awaiting_token":
            await self._handle_token(client, message, user_id, text, state)
            return

        if phase not in {"discovery", "confirmation"}:
            self.db.clear_conversation(user_id)
            phase = "discovery"
            state = {"history": []}

        lifecycle_reply = await self.lifecycle.handle(
            user_id,
            text,
            user_id in self.settings.super_admin_ids,
        )
        if lifecycle_reply.handled:
            await message.reply_text(lifecycle_reply.text)
            if lifecycle_reply.document_path is not None:
                await message.reply_document(str(lifecycle_reply.document_path))
            return

        if phase == "confirmation":
            await self._handle_confirmation(message, user_id, text, state)
            return

        await self._handle_discovery(message, user_id, text, state)

    async def _handle_discovery(self, message: object, user_id: int, text: str, state: dict[str, object]) -> None:
        history = self._history(state)
        history.append(f"User: {text}")
        if self._has_enough_discovery(history):
            summary = await self._summary(history)
            self.db.save_conversation(
                user_id,
                "confirmation",
                {"history": history, "summary": summary},
            )
            await message.reply_text(summary)
            return
        question = await self._next_question(history)
        history.append(f"Builder: {question}")
        self.db.save_conversation(user_id, "discovery", {"history": history})
        await message.reply_text(question)

    async def _handle_confirmation(
        self,
        message: object,
        user_id: int,
        text: str,
        state: dict[str, object],
    ) -> None:
        history = self._history(state)
        if looks_like_approval(text):
            approved_spec = "\n".join(history)
            await message.reply_text("Great. I am generating the bot schema and source files now.")
            schema = await self.validator.generate_from_spec(approved_spec)
            self.db.save_conversation(
                user_id,
                "awaiting_token",
                {
                    "history": history,
                    "schema_json": schema.model_dump_json(indent=2),
                },
            )
            await message.reply_text(
                "Now send the bot token from BotFather in this private chat. I will encrypt it in the builder database and pass it to the bot only as a process environment variable."
            )
            return
        history.append(f"User correction: {text}")
        if looks_like_correction(text) or len(history) < 10:
            summary = await self._summary(history)
            self.db.save_conversation(user_id, "confirmation", {"history": history, "summary": summary})
            await message.reply_text(summary)
            return
        self.db.save_conversation(user_id, "discovery", {"history": history})
        question = await self._next_question(history)
        await message.reply_text(question)

    async def _handle_token(
        self,
        client: object,
        message: object,
        user_id: int,
        token: str,
        state: dict[str, object],
    ) -> None:
        chat = getattr(message, "chat", None)
        chat_type_value = getattr(getattr(chat, "type", ""), "value", getattr(chat, "type", ""))
        if str(chat_type_value) != "private":
            await message.reply_text("Please send the bot token to me in a private chat so it is not exposed in a group.")
            return
        if BOT_TOKEN_RE.fullmatch(token) is None:
            await message.reply_text("That does not look like a Telegram bot token. Please send the token exactly as BotFather gave it to you.")
            return
        schema_json = str(state.get("schema_json", ""))
        schema = BotSchema.model_validate_json(schema_json)
        existing = self.db.find_owned_bot(user_id, schema.bot_name)
        if existing is not None and existing.bot_name.casefold() == schema.bot_name.casefold():
            await message.reply_text(
                f"You already have a bot named {schema.bot_name}. Ask me to update or delete that bot, or create this one with a different name."
            )
            return
        bot_dir = self.scaffolder.write_bot(user_id, schema)
        encrypted_token = encrypt_token(token, self.settings)
        record = self.db.register_bot(
            owner_user_id=user_id,
            bot_name=schema.bot_name,
            directory=bot_dir,
            token_encrypted=encrypted_token,
            schema_json=schema.model_dump_json(indent=2),
        )
        try:
            pid = self.manager.start(record)
        except Exception as exc:
            self.db.update_bot_status(record.bot_id, "crashed", None, str(exc))
            self.db.clear_conversation(user_id)
            await message.reply_text(f"The bot files were created, but the process did not start: {exc}")
            return
        self.db.clear_conversation(user_id)
        await message.reply_text(
            f"{schema.display_name} is built and running with PID {pid}. You can now talk to that bot directly, or ask me to list, stop, restart, update, delete, or inspect logs for your bots."
        )

    async def _next_question(self, history: list[str]) -> str:
        fallback = [
            "What should the bot do, and who will use it?",
            "Should it remember anything about each user between conversations?",
            "Should it work in private chats, groups, channels, or a mix?",
            "Should any behavior be limited to admins?",
            "What language should the bot use with people?",
        ]
        try:
            return await self.gemini_client.generate_text(discovery_question_prompt(history))
        except Exception:
            index = min(len([item for item in history if item.startswith("Builder:")]), len(fallback) - 1)
            return fallback[index]

    async def _summary(self, history: list[str]) -> str:
        try:
            return await self.gemini_client.generate_text(confirmation_summary_prompt(history))
        except Exception:
            user_lines = [item.replace("User: ", "").replace("User correction: ", "") for item in history if item.startswith("User")]
            summary = "\n".join(f"- {line}" for line in user_lines[-6:])
            return summary + "\n\nDoes that look right, or should I change anything?"

    def _has_enough_discovery(self, history: list[str]) -> bool:
        user_text = " ".join(item for item in history if item.startswith("User"))
        user_turns = len([item for item in history if item.startswith("User")])
        enough_words = len(user_text.split()) >= 45
        has_purpose = any(word in user_text.casefold() for word in ["bot", "users", "customers", "students", "group", "admin"])
        return user_turns >= 5 or (user_turns >= 2 and enough_words and has_purpose)

    def _history(self, state: dict[str, object]) -> list[str]:
        raw_history = state.get("history", [])
        if isinstance(raw_history, list):
            return [str(item) for item in raw_history]
        return []
