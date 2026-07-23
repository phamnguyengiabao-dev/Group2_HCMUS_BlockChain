"""
scenario_runner.py — Runs a scenario config and produces a deterministic event log.

Usage:
    from src.scenario_runner import run_scenario
    summary = run_scenario(scenario_config, default_config, run_id)
"""

import hashlib
import json

from src.event_log import EventLog


def _config_fingerprint(default_config: dict) -> str:
    """Return SHA-256 hex of the canonical sorted-key JSON of default_config."""
    canonical = json.dumps(default_config, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def run_scenario(scenario_config: dict, default_config: dict, run_id: str) -> dict:
    """
    Run a scenario and write a deterministic JSONL event log.

    Parameters
    ----------
    scenario_config : dict
        Loaded scenario JSON (e.g. scenario_noop.json).
    default_config : dict
        Loaded default config JSON (config/default.json).
    run_id : str
        Unique identifier for this run (used as log filename).

    Returns
    -------
    dict with keys: scenario_id, run_id, log_path, log_sha256, total_events
    """
    scenario_id: str = scenario_config["scenario_id"]
    seed: int = scenario_config["seed"]
    num_validators: int = scenario_config["num_validators"]
    max_height: int = scenario_config.get("max_height", 0)
    spec_version: str = default_config.get("spec_version", "0.1")

    log = EventLog(scenario_id=scenario_id, run_id=run_id)
    event_no = 1

    # --- SCENARIO_START ---
    log.write_event(
        event_no=event_no,
        logical_time=0,
        node_id="system",
        event_type="SCENARIO_START",
        height=0,
        round=0,
        details={
            "config_fingerprint": _config_fingerprint(default_config),
            "num_validators": num_validators,
            "scenario_id": scenario_id,
            "seed": seed,
            "spec_version": spec_version,
        },
    )
    event_no += 1

    # --- NODE_INIT per validator ---
    for idx in range(num_validators):
        node_id = f"validator_{idx}"
        log.write_event(
            event_no=event_no,
            logical_time=0,
            node_id=node_id,
            event_type="NODE_INIT",
            height=0,
            round=0,
            details={
                "node_id": node_id,
                "validator_index": idx,
            },
        )
        event_no += 1

    # --- Consensus (skipped for no-op when max_height == 0) ---
    if max_height > 0:
        # Placeholder for future consensus simulation phases.
        # Phase 0 only handles max_height=0 (no-op) and max_height>0 scaffold.
        pass

    # --- SCENARIO_END ---
    total_events = event_no  # will be the count after this event
    log.write_event(
        event_no=event_no,
        logical_time=0,
        node_id="system",
        event_type="SCENARIO_END",
        height=0,
        round=0,
        details={
            "scenario_id": scenario_id,
            "total_events": total_events,
        },
    )

    log.close()

    return {
        "scenario_id": scenario_id,
        "run_id": run_id,
        "log_path": str(log.log_path),
        "log_sha256": log.get_sha256(),
        "total_events": total_events,
    }
