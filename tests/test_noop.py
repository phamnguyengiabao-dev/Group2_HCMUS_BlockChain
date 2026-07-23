"""
test_noop.py — Pytest tests for the no-op scenario.

Tests:
1. Log file is created and non-empty.
2. Every line is valid JSON with all required fields.
3. event_no starts at 1 and increments by 1.
"""

import json
import os
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = REPO_ROOT / "config"


def _load_json(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _run_noop(tmp_path=None):
    """Run the noop scenario and return the summary dict."""
    # Change to repo root so relative 'logs/' path works in EventLog
    original_cwd = os.getcwd()
    os.chdir(REPO_ROOT)
    try:
        from src.scenario_runner import run_scenario  # noqa: PLC0415

        scenario_config = _load_json(CONFIG_DIR / "scenario_noop.json")
        default_config = _load_json(CONFIG_DIR / "default.json")
        return run_scenario(scenario_config, default_config, run_id="test_run_noop")
    finally:
        os.chdir(original_cwd)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

REQUIRED_FIELDS = {"event_no", "logical_time", "node_id", "event_type", "height", "round", "details"}


def test_noop_scenario_creates_log():
    """Log file must exist and be non-empty after running the noop scenario."""
    summary = _run_noop()
    log_path = Path(summary["log_path"])
    assert log_path.exists(), f"Log file not found: {log_path}"
    assert log_path.stat().st_size > 0, "Log file is empty"


def test_noop_scenario_log_is_valid_jsonl():
    """Every line in the log must be valid JSON containing all required fields."""
    summary = _run_noop()
    log_path = Path(summary["log_path"])

    with open(log_path, encoding="utf-8") as f:
        lines = f.readlines()

    assert len(lines) > 0, "Log file has no lines"

    for i, line in enumerate(lines, start=1):
        line = line.strip()
        assert line, f"Line {i} is empty"
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            pytest.fail(f"Line {i} is not valid JSON: {exc}")

        missing = REQUIRED_FIELDS - set(record.keys())
        assert not missing, f"Line {i} missing fields: {missing}"


def test_noop_scenario_event_nos_are_monotonic():
    """event_no must start at 1 and increment by exactly 1 per line."""
    summary = _run_noop()
    log_path = Path(summary["log_path"])

    with open(log_path, encoding="utf-8") as f:
        lines = f.readlines()

    for expected_no, line in enumerate(lines, start=1):
        record = json.loads(line.strip())
        actual_no = record["event_no"]
        assert actual_no == expected_no, (
            f"Expected event_no={expected_no}, got {actual_no} on line {expected_no}"
        )
