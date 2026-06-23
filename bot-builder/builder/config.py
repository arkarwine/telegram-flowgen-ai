from __future__ import annotations

import base64
import hashlib
import os
from dataclasses import dataclass
from pathlib import Path

try:
    from dotenv import load_dotenv as _load_dotenv
except ImportError:
    def _load_dotenv(path: Path) -> bool:
        return False


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = PROJECT_ROOT / ".env"


@dataclass(frozen=True)
class Settings:
    builder_token: str
    telegram_api_id: int
    telegram_api_hash: str
    gemini_api_key: str
    master_secret: str
    super_admin_ids: tuple[int, ...]
    project_root: Path
    builder_db_path: Path
    bots_dir: Path
    log_level: str
    gemini_model: str
    watchdog_interval_seconds: int
    restart_window_seconds: int
    max_restarts_per_window: int


def _parse_int_list(value: str) -> tuple[int, ...]:
    ids: list[int] = []
    for raw_item in value.split(","):
        item = raw_item.strip()
        if item:
            ids.append(int(item))
    return tuple(ids)


def _required(name: str, require_secrets: bool) -> str:
    value = os.getenv(name, "").strip()
    if require_secrets and not value:
        raise RuntimeError(f"{name} is required in {ENV_PATH}")
    return value


def load_settings(require_secrets: bool = True) -> Settings:
    _load_dotenv(ENV_PATH)
    api_id_raw = _required("TELEGRAM_API_ID", require_secrets)
    api_id = int(api_id_raw) if api_id_raw else 0
    bots_dir = Path(os.getenv("BOTS_DIR", str(PROJECT_ROOT / "bots"))).expanduser()
    builder_db_path = Path(os.getenv("BUILDER_DB_PATH", str(PROJECT_ROOT / "builder.db"))).expanduser()
    return Settings(
        builder_token=_required("BUILDER_TOKEN", require_secrets),
        telegram_api_id=api_id,
        telegram_api_hash=_required("TELEGRAM_API_HASH", require_secrets),
        gemini_api_key=_required("GEMINI_API_KEY", require_secrets),
        master_secret=_required("MASTER_SECRET", require_secrets),
        super_admin_ids=_parse_int_list(os.getenv("SUPER_ADMIN_IDS", "")),
        project_root=PROJECT_ROOT,
        builder_db_path=builder_db_path,
        bots_dir=bots_dir,
        log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
        gemini_model=os.getenv("GEMINI_MODEL", "gemini-2.5-flash-lite"),
        watchdog_interval_seconds=int(os.getenv("WATCHDOG_INTERVAL_SECONDS", "30")),
        restart_window_seconds=int(os.getenv("RESTART_WINDOW_SECONDS", "300")),
        max_restarts_per_window=int(os.getenv("MAX_RESTARTS_PER_WINDOW", "3")),
    )


def build_fernet(master_secret: str):
    from cryptography.fernet import Fernet

    digest = hashlib.sha256(master_secret.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_token(token: str, settings: Settings) -> str:
    return build_fernet(settings.master_secret).encrypt(token.encode("utf-8")).decode("utf-8")


def decrypt_token(token_encrypted: str, settings: Settings) -> str:
    return build_fernet(settings.master_secret).decrypt(token_encrypted.encode("utf-8")).decode("utf-8")
