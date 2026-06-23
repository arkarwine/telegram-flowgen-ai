from __future__ import annotations

import os
import re
from pathlib import Path

from builder.codegen.generator import BotCodeGenerator
from builder.schema.blocks import BotSchema


class BotScaffolder:
    def __init__(self, bots_dir: Path, generator: BotCodeGenerator | None = None) -> None:
        self.bots_dir = bots_dir
        self.generator = generator or BotCodeGenerator()

    def bot_directory(self, owner_user_id: int, bot_name: str) -> Path:
        safe_name = re.sub(r"[^a-zA-Z0-9_-]+", "-", bot_name).strip("-").lower()
        if not safe_name:
            safe_name = "bot"
        return self.bots_dir / f"{owner_user_id}_{safe_name}"

    def write_bot(self, owner_user_id: int, schema: BotSchema, directory: Path | None = None) -> Path:
        bot_dir = directory or self.bot_directory(owner_user_id, schema.bot_name)
        bot_dir.mkdir(parents=True, exist_ok=True)
        (bot_dir / "handlers").mkdir(parents=True, exist_ok=True)
        for generated_file in self.generator.generate(schema):
            target = bot_dir / generated_file.relative_path
            target.parent.mkdir(parents=True, exist_ok=True)
            self._atomic_write(target, generated_file.content)
        (bot_dir / "bot.log").touch(exist_ok=True)
        (bot_dir / "downloads").mkdir(exist_ok=True)
        return bot_dir

    def _atomic_write(self, target: Path, content: str) -> None:
        tmp = target.with_suffix(target.suffix + ".tmp")
        tmp.write_text(content, encoding="utf-8", newline="\n")
        os.replace(tmp, target)

