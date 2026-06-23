#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICE_NAME="telegram-bot-builder"

select_python() {
  if [[ -n "${PYTHON_BIN:-}" ]]; then
    if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
      echo "PYTHON_BIN is set to '${PYTHON_BIN}', but that command was not found."
      exit 1
    fi
    "$PYTHON_BIN" - <<'PY'
import sys
if not ((3, 11) <= sys.version_info[:2] <= (3, 13)):
    raise SystemExit(
        f"Python {sys.version_info.major}.{sys.version_info.minor} is not supported by this installer. "
        "Use Python 3.11, 3.12, or 3.13."
    )
PY
    return
  fi

  for candidate in python3.13 python3.12 python3.11; do
    if command -v "$candidate" >/dev/null 2>&1; then
      PYTHON_BIN="$candidate"
      return
    fi
  done

  if command -v uv >/dev/null 2>&1; then
    for version in 3.13 3.12 3.11; do
      if uv python find "$version" >/dev/null 2>&1; then
        PYTHON_BIN="$(uv python find "$version")"
        return
      fi
    done
    echo "uv is installed, but no supported managed Python was found. Installing Python 3.12 with uv."
    uv python install 3.12
    PYTHON_BIN="$(uv python find 3.12)"
    return
  fi

  echo "Python 3.11, 3.12, or 3.13 is required."
  echo "Your system may be defaulting to Python 3.14, which is too new for current native dependencies."
  echo "Install a supported interpreter with uv:"
  echo "  curl -LsSf https://astral.sh/uv/install.sh | sh"
  echo "  export PATH=\"\$HOME/.local/bin:\$PATH\""
  echo "  uv python install 3.12"
  echo "  PYTHON_BIN=\"\$(uv python find 3.12)\" ./install.sh"
  echo "Or, on supported Ubuntu LTS releases, install python3.11 or python3.13 from deadsnakes."
  exit 1
}

select_python

cd "$PROJECT_DIR"
echo "Using $("$PYTHON_BIN" -c 'import sys; print(sys.executable, sys.version.split()[0])')"
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
