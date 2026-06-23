# Telegram Bot Builder Engine

A bare-metal, multi-tenant Telegram bot builder. One Pyrofork builder bot chats with users in natural language, turns an approved bot idea into a strict validated schema, generates a self-contained Python bot directory, encrypts that bot token in `builder.db`, and runs each generated bot as its own subprocess.

No Docker, no web server, no webhooks, and no external services except Telegram Bot API and Gemini.

## Setup

Use Python 3.11, 3.12, or 3.13. Python 3.14 is currently too new for some native dependencies in this stack and can fail while building `pydantic-core`.

On Ubuntu:

```bash
cd bot-builder
chmod +x install.sh
./install.sh
```

If your server defaults to Python 3.14, install a supported interpreter and pass it explicitly:

```bash
sudo apt-get update
sudo apt-get install -y python3.12 python3.12-venv python3.12-dev
PYTHON_BIN=python3.12 ./install.sh
```

Then edit `.env`:

```bash
nano .env
sudo systemctl start telegram-bot-builder
journalctl -u telegram-bot-builder -f
```

Pyrogram/Pyrofork requires `TELEGRAM_API_ID` and `TELEGRAM_API_HASH`; create them at [my.telegram.org/apps](https://my.telegram.org/apps).

## Environment

- `BUILDER_TOKEN`: BotFather token for the builder bot.
- `TELEGRAM_API_ID`: Telegram application API ID.
- `TELEGRAM_API_HASH`: Telegram application API hash.
- `GEMINI_API_KEY`: Gemini API key.
- `GEMINI_MODEL`: Defaults to `gemini-2.5-flash-lite`.
- `MASTER_SECRET`: Stable secret used to derive the Fernet key for generated bot token encryption.
- `SUPER_ADMIN_IDS`: Comma-separated Telegram user IDs with operational visibility across all bots.
- `BUILDER_DB_PATH`: Optional path for `builder.db`.
- `BOTS_DIR`: Optional directory for generated bot folders.
- `LOG_LEVEL`: `DEBUG`, `INFO`, `WARNING`, `ERROR`, or `CRITICAL`.

Keep `MASTER_SECRET` stable. Changing it after bots are registered prevents decrypting stored bot tokens.

## How It Works

The builder has three guardrails around AI output:

1. A fixed capability block registry in `builder/schema/registry.py`.
2. Strict Pydantic v2 models in `builder/schema/blocks.py`.
3. A repair loop in `builder/schema/validator.py` that retries invalid Gemini output up to three times with exact validation errors.

Gemini never writes Python code. It only fills typed schema fields. Code is generated locally by `builder/codegen/generator.py`.

## Conversation Flow

Users describe a bot in plain language. The builder asks a few open questions, summarizes what it understood, and waits for natural approval or corrections. After approval, it generates the schema and source files, asks for the child bot token in private chat, encrypts it, writes the bot directory, initializes state, and starts the subprocess.

Users can later ask naturally to list, start, stop, restart, delete, update, or inspect logs for their bots. Tenant isolation is enforced by `owner_user_id` in `builder.db`.

## Generated Bots

Each generated bot directory contains:

```text
main.py
config.py
db.py
schema.json
handlers/
requirements.txt
bot.log
bot.db
downloads/
```

Generated bots keep persistent state in their own SQLite database and receive secrets only through environment variables at process start.

## Adding Capability Blocks

1. Add a strict Pydantic model to `builder/schema/blocks.py`.
2. Add the model to the `CapabilityBlock` discriminated union.
3. Register it in `builder/schema/registry.py`.
4. Implement runtime behavior in `builder/codegen/generator.py`.
5. Add it to `tests/smoke_codegen.py` so schema validation and generated Python compilation keep covering it.

Do not add free-form fields or `Any` to block models. New blocks should be explicit and fully executable.

## Logs And Operations

Builder service logs:

```bash
journalctl -u telegram-bot-builder -f
tail -f builder.log
```

Generated bot logs:

```bash
tail -f bots/<owner>_<bot-name>/bot.log
```

The builder watchdog checks child processes every 30 seconds by default. It restarts a crashed bot up to three times within five minutes, then marks it `crashed` and notifies the owner.

## Local Verification

After installing dependencies:

```bash
python -m compileall builder tests
python tests/smoke_codegen.py
```

The smoke test validates a schema containing every registered capability block, generates a bot directory in a temporary folder, checks for forbidden placeholder markers in generated source, and compiles every generated Python file.
