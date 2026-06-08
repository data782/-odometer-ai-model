import logging
import os
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[2]
logger = logging.getLogger(__name__)


def _audit_log_path() -> Path | None:
    explicit_path = os.getenv("AUDIT_LOG_PATH")
    if explicit_path:
        return Path(explicit_path)

    environment = os.getenv("ENVIRONMENT", "local").strip().lower()
    if environment in {"local", "dev", "development", "test"}:
        return BASE_DIR / "logs.txt"

    return None


def write_log(status: str, mode: str, value: str | None) -> None:
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    if status == "success":
        line = f"{timestamp} | SUCCESS | mode={mode} | value={value}\n"
    else:
        line = f"{timestamp} | FAIL | mode={mode} | NOT_FOUND\n"

    log_file = _audit_log_path()
    if log_file is None:
        logger.info(line.strip())
        return

    log_file.parent.mkdir(parents=True, exist_ok=True)
    with log_file.open("a", encoding="utf-8") as file_handle:
        file_handle.write(line)
