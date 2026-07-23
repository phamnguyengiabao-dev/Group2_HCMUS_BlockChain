"""
verify_determinism.py — Standalone determinism verification script.

Runs the noop scenario twice with the same seed and compares the log files
byte-by-byte. Prints PASS or FAIL and exits with code 0 (pass) or 1 (fail).

Usage:
    python tests/verify_determinism.py
"""

import json
import os
import sys
from pathlib import Path

# Ensure repo root is on sys.path when run directly
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from src.scenario_runner import run_scenario  # noqa: E402


CONFIG_DIR = REPO_ROOT / "config"


def _load_json(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def main() -> None:
    original_cwd = os.getcwd()
    os.chdir(REPO_ROOT)

    try:
        scenario_config = _load_json(CONFIG_DIR / "scenario_noop.json")
        default_config = _load_json(CONFIG_DIR / "default.json")

        summary_a = run_scenario(scenario_config, default_config, run_id="determinism_run_a")
        summary_b = run_scenario(scenario_config, default_config, run_id="determinism_run_b")

        path_a = Path(summary_a["log_path"])
        path_b = Path(summary_b["log_path"])

        content_a = path_a.read_bytes()
        content_b = path_b.read_bytes()

        sha_a = summary_a["log_sha256"]
        sha_b = summary_b["log_sha256"]

        if content_a == content_b and sha_a == sha_b:
            print(f"PASS — both runs produced identical logs (SHA-256: {sha_a})")
            sys.exit(0)
        else:
            print("FAIL — log files differ between runs")
            print(f"  Run A SHA-256: {sha_a}")
            print(f"  Run B SHA-256: {sha_b}")
            if content_a != content_b:
                lines_a = content_a.decode("utf-8").splitlines()
                lines_b = content_b.decode("utf-8").splitlines()
                for i, (la, lb) in enumerate(zip(lines_a, lines_b), start=1):
                    if la != lb:
                        print(f"  First diff at line {i}:")
                        print(f"    A: {la}")
                        print(f"    B: {lb}")
                        break
            sys.exit(1)
    finally:
        os.chdir(original_cwd)


if __name__ == "__main__":
    main()
