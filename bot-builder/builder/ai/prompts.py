from __future__ import annotations

import json


def discovery_question_prompt(history: list[str]) -> str:
    return f"""
You are the natural-language discovery brain for a Telegram bot builder.
Ask exactly one concise, open question that helps clarify the requested bot.
Do not mention JSON, schemas, commands, menus, buttons, implementation files, or Telegram internals.
Stop asking once the user's purpose, audience, memory needs, chat scope, admin restrictions, and language are clear.

Conversation so far:
{json.dumps(history, ensure_ascii=False, indent=2)}
""".strip()


def confirmation_summary_prompt(history: list[str]) -> str:
    return f"""
Summarize the Telegram bot the user wants in friendly plain language.
Use 5 to 8 short bullet points. Avoid technical jargon, JSON, schemas, commands, and implementation details.
End with one sentence asking the user to approve or correct the summary in natural language.

Conversation:
{json.dumps(history, ensure_ascii=False, indent=2)}
""".strip()


def schema_generation_prompt(spec_text: str, registry_text: str) -> str:
    return f"""
You convert a natural-language Telegram bot specification into one strict BotSchema JSON object.
Return JSON only. Do not wrap it in Markdown.

Rules:
- Use schema_version "1.0".
- Select only block types listed in the registry.
- Never invent a new block type, field, or nested structure.
- Prefer a small complete set of blocks over many overlapping handlers.
- Include admin_ids/admins when the user gives admin user IDs; otherwise leave admin arrays empty.
- Include a user_data_store block when the bot must remember information across conversations.
- Include conversation_flow when the bot collects multi-step input.
- Include text_handler or command_handler so the bot responds to at least one normal user message.
- Do not include secrets or bot tokens.

User-approved specification:
{spec_text}

{registry_text}
""".strip()


def repair_schema_prompt(raw_output: str, errors: list[dict[str, object]], registry_text: str) -> str:
    return f"""
Repair the JSON below so it validates against the BotSchema and allowed capability block registry.
Return JSON only. Preserve the user's intended behavior. Change only fields needed to fix validation.

Validation errors:
{json.dumps(errors, ensure_ascii=False, indent=2)}

Invalid JSON or invalid schema:
{raw_output}

{registry_text}
""".strip()


def patch_schema_prompt(current_schema_json: str, change_request: str, registry_text: str) -> str:
    return f"""
Apply the user's requested change to the current BotSchema.
Return one complete updated BotSchema JSON object only.
Modify only the affected blocks when possible. Keep existing bot data model and behavior unless the user asks to change it.
Use only block types and fields from the registry.

User change request:
{change_request}

Current schema:
{current_schema_json}

{registry_text}
""".strip()


def lifecycle_intent_prompt(message_text: str, owned_bot_names: list[str]) -> str:
    return f"""
Classify this natural-language builder message.
Return JSON only with fields:
  intent: one of ["none","list","start","stop","restart","delete","logs","update"]
  bot_name: matching owned bot name when implied, otherwise ""
  details: short natural-language details for update/log/delete requests, otherwise ""
  tail_lines: integer between 20 and 500, default 80

Owned bot names:
{json.dumps(owned_bot_names, ensure_ascii=False)}

Message:
{message_text}
""".strip()

