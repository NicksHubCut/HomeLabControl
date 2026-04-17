"""
Audit Log – schreibt JSON-Lines in logs/audit.log
"""

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock


class AuditLog:
    def __init__(self, log_path: Path):
        self.log_path = log_path
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()

    def log(self, event: str, client_ip: str, path: str, extra: dict = None):
        entry = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "event": event,
            "ip": client_ip,
            "path": path,
        }
        if extra:
            entry.update(extra)

        with self._lock:
            with open(self.log_path, "a") as f:
                f.write(json.dumps(entry) + "\n")

    def get_recent(self, limit: int = 50) -> list[dict]:
        if not self.log_path.exists():
            return []
        try:
            with self._lock:
                lines = self.log_path.read_text().splitlines()
            entries = []
            for line in reversed(lines[-limit * 2:]):
                try:
                    entries.append(json.loads(line))
                except Exception:
                    continue
                if len(entries) >= limit:
                    break
            return entries
        except Exception:
            return []
