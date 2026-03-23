from datetime import datetime
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_FILE = os.path.join(BASE_DIR, "logs.txt")

def write_log(status: str, mode: str, value: str | None):

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    if status == "success":
        line = f"{timestamp} | SUCCESS | mode={mode} | value={value}\n"
    else:
        line = f"{timestamp} | FAIL | mode={mode} | NOT_FOUND\n"

    with open(LOG_FILE, "a") as f:
        f.write(line)

    print("Log written:", line.strip())