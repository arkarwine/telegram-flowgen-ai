from __future__ import annotations

import py_compile
import re
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from builder.codegen.scaffolder import BotScaffolder
from builder.schema.blocks import BotSchema


def sample_schema() -> BotSchema:
    return BotSchema.model_validate(
        {
            "schema_version": "1.0",
            "bot_name": "sample_bot",
            "display_name": "Sample Bot",
            "description": "A generated bot that exercises every capability block.",
            "default_language": "en",
            "admins": [123456],
            "chat_scopes": ["private", "group", "channel"],
            "blocks": [
                {
                    "type": "rate_limiter",
                    "id": "rate_limit",
                    "max_events": 5,
                    "window_seconds": 30,
                    "applies_to": ["*"],
                },
                {
                    "type": "command_handler",
                    "id": "start_command",
                    "command": "hello",
                    "response": "Hello {first_name}.",
                },
                {
                    "type": "text_handler",
                    "id": "faq",
                    "match_mode": "contains",
                    "pattern": "help",
                    "response": "Here is help.",
                },
                {
                    "type": "conversation_flow",
                    "id": "signup",
                    "entry_triggers": ["sign up"],
                    "steps": [{"key": "email", "prompt": "Email?", "data_key": "email"}],
                    "final_response": "Saved {email}.",
                },
                {
                    "type": "inline_query_handler",
                    "id": "inline_help",
                    "results": [
                        {
                            "result_id": "help",
                            "title": "Help",
                            "description": "Send help",
                            "message_text": "Help text",
                        }
                    ],
                },
                {
                    "type": "callback_query_handler",
                    "id": "callback",
                    "callback_data_pattern": "^ok$",
                    "response": "OK",
                },
                {
                    "type": "media_handler",
                    "id": "photos",
                    "media_types": ["photo"],
                    "response": "Photo received.",
                },
                {
                    "type": "media_sender",
                    "id": "send_photo",
                    "trigger_text": "photo",
                    "media_type": "photo",
                    "source": "https://example.com/photo.jpg",
                },
                {
                    "type": "scheduler",
                    "id": "daily",
                    "name": "Daily",
                    "message": "Daily message",
                    "target_chat_id": 123456,
                    "interval_seconds": 60,
                },
                {
                    "type": "broadcast",
                    "id": "broadcast",
                    "message_template": "News",
                    "admin_ids": [123456],
                },
                {
                    "type": "user_data_store",
                    "id": "profile",
                    "fields": [{"key": "email", "value_type": "text", "prompt": "Email?"}],
                },
                {
                    "type": "admin_panel",
                    "id": "admin",
                    "admin_ids": [123456],
                    "commands": [{"name": "stats", "response": "Stats"}],
                },
                {"type": "welcome_handler", "id": "welcome", "message": "Welcome."},
                {
                    "type": "poll_creator",
                    "id": "poll",
                    "trigger_text": "poll",
                    "question": "Pick one",
                    "options": ["A", "B"],
                },
                {
                    "type": "quiz_creator",
                    "id": "quiz",
                    "trigger_text": "quiz",
                    "question": "2+2?",
                    "options": ["3", "4"],
                    "correct_option_id": 1,
                },
                {"type": "dice_roller", "id": "dice", "trigger_text": "dice"},
                {
                    "type": "chat_member_handler",
                    "id": "members",
                    "on_join_message": "Joined.",
                    "on_leave_message": "Left.",
                },
                {
                    "type": "file_downloader",
                    "id": "files",
                    "media_types": ["document"],
                    "directory": "downloads",
                },
                {
                    "type": "deeplink_handler",
                    "id": "deeplink",
                    "payload_actions": [{"pattern": "^promo", "response": "Promo", "store_key": "promo"}],
                },
                {
                    "type": "payment_handler",
                    "id": "pay",
                    "trigger_text": "buy",
                    "title": "Item",
                    "description_text": "One item",
                    "currency": "USD",
                    "prices": [{"label": "Item", "amount_minor_units": 100}],
                    "payload": "item",
                },
                {"type": "location_handler", "id": "location", "response": "Location saved."},
                {"type": "contact_handler", "id": "contact", "response": "Contact saved."},
                {"type": "forwarded_message_handler", "id": "forwarded", "response": "Forward seen."},
                {
                    "type": "sticker_set_handler",
                    "id": "stickers",
                    "trigger_text": "stickers",
                    "sticker_set_name": "Telegram",
                },
                {
                    "type": "game_handler",
                    "id": "game",
                    "trigger_text": "game",
                    "game_short_name": "sample_game",
                },
                {
                    "type": "channel_post_handler",
                    "id": "channel",
                    "match_mode": "always",
                    "response": "Channel post seen.",
                },
                {"type": "error_handler", "id": "errors"},
            ],
        }
    )


def main() -> None:
    schema = sample_schema()
    with tempfile.TemporaryDirectory() as tmp:
        bot_dir = BotScaffolder(Path(tmp)).write_bot(123456, schema)
        for path in bot_dir.rglob("*.py"):
            source = path.read_text(encoding="utf-8")
            if re.search(r"\bpass\b|TODO|placeholder", source, flags=re.IGNORECASE):
                raise AssertionError(f"Forbidden placeholder marker in {path}")
            py_compile.compile(str(path), doraise=True)
        if not (bot_dir / "schema.json").exists():
            raise AssertionError("schema.json was not generated")
    print("Smoke code generation passed.")


if __name__ == "__main__":
    main()
