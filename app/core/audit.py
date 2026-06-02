from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[2]
LOG_FILE = BASE_DIR / "logs.txt"


def write_log(status: str, mode: str, value: str | None) -> None:
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    if status == "success":
        line = f"{timestamp} | SUCCESS | mode={mode} | value={value}\n"
    else:
        line = f"{timestamp} | FAIL | mode={mode} | NOT_FOUND\n"

    with LOG_FILE.open("a", encoding="utf-8") as file_handle:
        file_handle.write(line)
