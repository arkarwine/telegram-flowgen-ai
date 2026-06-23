#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICE_NAME="telegram-bot-builder"
PYTHON_BIN="${PYTHON_BIN:-python3.11}"

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  PYTHON_BIN="python3"
fi

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  echo "Python 3.11+ is required."
  exit 1
fi

cd "$PROJECT_DIR"
"$PYTHON_BIN" -m venv .venv
".venv/bin/python" -m pip install --upgrade pip
".venv/bin/python" -m pip install -r requirements.txt

if [[ ! -f .env ]]; then
  MASTER_SECRET="$(".venv/bin/python" -c 'import secrets; print(secrets.token_urlsafe(32))')"
  cat > .env <<ENV
# Builder bot token from BotFather.
BUILDER_TOKEN=

# Required by Pyrogram/Pyrofork for both the builder and generated bots.
# Create these at https://my.telegram.org/apps
TELEGRAM_API_ID=
TELEGRAM_API_HASH=

# Gemini backend.
GEMINI_API_KEY=
GEMINI_MODEL=gemini-2.5-flash-lite

# Token encryption master secret. Keep this stable after bots are created.
MASTER_SECRET=${MASTER_SECRET}

# Comma-separated Telegram user IDs with operational read-only visibility.
SUPER_ADMIN_IDS=

BUILDER_DB_PATH=${PROJECT_DIR}/builder.db
BOTS_DIR=${PROJECT_DIR}/bots
LOG_LEVEL=INFO
WATCHDOG_INTERVAL_SECONDS=30
RESTART_WINDOW_SECONDS=300
MAX_RESTARTS_PER_WINDOW=3
ENV
  chmod 600 .env
  echo "Created .env. Fill in BUILDER_TOKEN, TELEGRAM_API_ID, TELEGRAM_API_HASH, and GEMINI_API_KEY before starting."
fi

".venv/bin/python" -m builder.db

SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"
sudo tee "$SERVICE_FILE" >/dev/null <<SERVICE
[Unit]
Description=Telegram Bot Builder
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=${USER}
WorkingDirectory=${PROJECT_DIR}
EnvironmentFile=${PROJECT_DIR}/.env
ExecStart=${PROJECT_DIR}/.venv/bin/python -m builder.main
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
SERVICE

sudo systemctl daemon-reload
sudo systemctl enable "${SERVICE_NAME}.service"

cat <<POSTINSTALL

Installation complete.

Next steps:
1. Edit ${PROJECT_DIR}/.env and fill the required secrets.
2. Start the builder:
   sudo systemctl start ${SERVICE_NAME}
3. Watch logs:
   journalctl -u ${SERVICE_NAME} -f
   tail -f ${PROJECT_DIR}/builder.log

POSTINSTALL

