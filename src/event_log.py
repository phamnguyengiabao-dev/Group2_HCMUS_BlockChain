"""
event_log.py — Canonical JSONL event logger for blockchain simulator.

Each event line has fixed key order:
  event_no, logical_time, node_id, event_type, height, round, details
Details keys are sorted alphabetically.
"""

import hashlib
import json
import os
from pathlib import Path


class EventLog:
    """Writes deterministic JSONL event logs to logs/<scenario_id>/<run_id>.jsonl."""

    def __init__(self, scenario_id: str, run_id: str):
        self.scenario_id = scenario_id
        self.run_id = run_id

        log_dir = Path("logs") / scenario_id
        log_dir.mkdir(parents=True, exist_ok=True)

        self.log_path = log_dir / f"{run_id}.jsonl"
        self._file = open(self.log_path, "w", encoding="utf-8")
        self._event_count = 0

    def write_event(
        self,
        event_no: int,
        logical_time: int,
        node_id: str,
        event_type: str,
        height: int,
        round: int,  # noqa: A002  (shadows built-in, but required by spec)
        details: dict,
    ) -> None:
        """Write one canonical JSON line with fixed key order."""
        record = {
            "event_no": event_no,
            "logical_time": logical_time,
            "node_id": node_id,
            "event_type": event_type,
            "height": height,
            "round": round,
            "details": {k: details[k] for k in sorted(details)},
        }
        self._file.write(json.dumps(record, separators=(",", ":")) + "\n")
        self._event_count += 1

    def close(self) -> None:
        """Flush and close the log file."""
        self._file.flush()
        self._file.close()

    def get_sha256(self) -> str:
        """Return the hex SHA-256 digest of the written log file."""
        h = hashlib.sha256()
        with open(self.log_path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()

    @property
    def event_count(self) -> int:
        return self._event_count
