from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass

from pydantic import ValidationError

from builder.ai.prompts import patch_schema_prompt, repair_schema_prompt, schema_generation_prompt
from builder.ai.parser import extract_json_object
from builder.schema.blocks import BotSchema
from builder.schema.registry import registry_prompt


@dataclass(frozen=True)
class SchemaValidationFailure:
    attempt: int
    errors: list[dict[str, object]]
    candidate: str


class SchemaValidationError(RuntimeError):
    def __init__(self, failures: list[SchemaValidationFailure]) -> None:
        self.failures = failures
        details = failures[-1].errors if failures else []
        super().__init__(f"Schema validation failed after repair attempts: {details}")


class SchemaValidator:
    def __init__(self, gemini_client: object, max_repair_attempts: int = 3) -> None:
        self.gemini_client = gemini_client
        self.max_repair_attempts = max_repair_attempts

    async def generate_from_spec(self, spec_text: str) -> BotSchema:
        prompt = schema_generation_prompt(spec_text, registry_prompt())
        raw = await self.gemini_client.generate_json(prompt)
        return await self.validate_with_repair(raw)

    async def patch_schema(self, current_schema: BotSchema, change_request: str) -> BotSchema:
        prompt = patch_schema_prompt(current_schema.model_dump_json(indent=2), change_request, registry_prompt())
        raw = await self.gemini_client.generate_json(prompt)
        return await self.validate_with_repair(raw)

    async def validate_with_repair(self, raw_output: str | Mapping[str, object]) -> BotSchema:
        candidate = json.dumps(raw_output) if isinstance(raw_output, Mapping) else raw_output
        failures: list[SchemaValidationFailure] = []
        for attempt in range(self.max_repair_attempts + 1):
            try:
                schema = self.parse(candidate)
                return self._ensure_default_blocks(schema)
            except ValidationError as exc:
                errors = exc.errors(include_url=False)
                failures.append(SchemaValidationFailure(attempt=attempt, errors=errors, candidate=candidate))
                if attempt >= self.max_repair_attempts:
                    raise SchemaValidationError(failures) from exc
                repair_prompt = repair_schema_prompt(candidate, errors, registry_prompt())
                candidate = await self.gemini_client.generate_json(repair_prompt)
            except json.JSONDecodeError as exc:
                error = {
                    "type": "json_decode",
                    "location": "root",
                    "message": str(exc),
                }
                failures.append(SchemaValidationFailure(attempt=attempt, errors=[error], candidate=candidate))
                if attempt >= self.max_repair_attempts:
                    raise SchemaValidationError(failures) from exc
                repair_prompt = repair_schema_prompt(candidate, [error], registry_prompt())
                candidate = await self.gemini_client.generate_json(repair_prompt)
        raise SchemaValidationError(failures)

    def parse(self, raw_output: str) -> BotSchema:
        json_text = extract_json_object(raw_output)
        return BotSchema.model_validate_json(json_text)

    def _ensure_default_blocks(self, schema: BotSchema) -> BotSchema:
        block_types = {block.type for block in schema.blocks}
        data = schema.model_dump(mode="json")
        if "rate_limiter" not in block_types:
            data["blocks"].insert(
                0,
                {
                    "type": "rate_limiter",
                    "id": "default_rate_limiter",
                    "enabled": True,
                    "description": "Default protection for user-facing handlers.",
                    "max_events": 6,
                    "window_seconds": 30,
                    "applies_to": ["*"],
                    "action_message": "Please slow down and try again in a moment.",
                },
            )
        if "error_handler" not in block_types:
            data["blocks"].append(
                {
                    "type": "error_handler",
                    "id": "default_error_handler",
                    "enabled": True,
                    "description": "Default structured error logging.",
                    "log_level": "ERROR",
                    "notify_admins": True,
                    "user_message": "Something went wrong. Please try again later.",
                }
            )
        return BotSchema.model_validate(data)

