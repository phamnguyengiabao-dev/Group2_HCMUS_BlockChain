"""
summary.py — Export compact simulation summary (T5-09).

Produces a deterministic dict/JSON summarising a completed run:
    - (height, hash) per node in sorted node_id order
    - final state_hash per node
    - REJECT event counts by rejection code
    - SHA-256 of the canonical event log

Usage:
    from src.summary import build_summary, format_summary_json
    summary = build_summary(runner)
    print(format_summary_json(summary))
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from src.scenario import ScenarioRunner


@dataclass(frozen=True)
class NodeSummary:
    """Per-node compact summary."""

    node_id: str
    finalized_height: int
    finalized_hash: str          # hex or "" if nothing finalized
    state_hash: str              # hex of post-state at finalized_height, or "" if empty


@dataclass
class RunSummary:
    """Complete compact summary of one simulation run."""

    scenario_id: str
    run_id: str
    log_path: str
    log_sha256: str
    total_events: int
    logical_time: int

    # Sorted by node_id
    nodes: list[NodeSummary] = field(default_factory=list)

    # REJECT counts: rejection_code -> count  (sorted by code)
    rejection_counts: dict[str, int] = field(default_factory=dict)

    safety_ok: bool | None = None
    liveness_ok: bool | None = None
    liveness_max_finalized_height: int = 0


# ------------------------------------------------------------------ #
# Public API
# ------------------------------------------------------------------ #

def build_summary(runner: "ScenarioRunner") -> RunSummary:
    """
    Build a compact summary from a completed ScenarioRunner.

    Args:
        runner: A ScenarioRunner that has already called execute() or
                at least load() + run() + check_assertions().

    Returns:
        RunSummary with all fields populated.

    Raises:
        RuntimeError: If the runner has not been executed yet.
    """
    if runner.event_log is None:
        raise RuntimeError("ScenarioRunner has not been executed")

    event_log = runner.event_log
    scenario_config = runner.scenario_config

    # ---- per-node summary ----------------------------------------
    nodes: list[NodeSummary] = []
    for node_id in sorted(runner.ledgers):
        ledger = runner.ledgers[node_id]
        fh = ledger.finalized_height
        if fh > 0:
            entry = ledger.get_entry(fh)
            fhash = entry.block_hash.hex()
            shash = entry.state.state_hash().hex()
        else:
            fhash = ""
            shash = ""
        nodes.append(NodeSummary(
            node_id=node_id,
            finalized_height=fh,
            finalized_hash=fhash,
            state_hash=shash,
        ))

    # ---- rejection counts ----------------------------------------
    rejection_counts = _count_rejections(event_log.log_path)

    # ---- assertion results ----------------------------------------
    safety_ok = runner.safety_result.ok if runner.safety_result is not None else None
    liveness_ok = runner.liveness_result.ok if runner.liveness_result is not None else None
    liveness_max = (
        runner.liveness_result.max_finalized_height
        if runner.liveness_result is not None
        else 0
    )

    scheduler = runner.scheduler
    logical_time = scheduler.logical_time if scheduler is not None else 0

    return RunSummary(
        scenario_id=scenario_config.get("scenario_id", "unknown"),
        run_id=event_log.run_id,
        log_path=str(event_log.log_path),
        log_sha256=event_log.get_sha256(),
        total_events=event_log.event_count,
        logical_time=logical_time,
        nodes=nodes,
        rejection_counts=rejection_counts,
        safety_ok=safety_ok,
        liveness_ok=liveness_ok,
        liveness_max_finalized_height=liveness_max,
    )


def _count_rejections(log_path: "Path | str") -> dict[str, int]:
    """
    Scan the JSONL log file and count REJECT events by rejection code.

    Returns a dict sorted by rejection code (alphabetically).
    """
    counts: dict[str, int] = {}
    path = Path(log_path)

    if not path.exists():
        return counts

    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue

            if record.get("event_type") != "REJECT":
                continue

            details = record.get("details", {})
            code = details.get("code", "UNKNOWN")
            counts[code] = counts.get(code, 0) + 1

    return dict(sorted(counts.items()))


def to_dict(summary: RunSummary) -> dict[str, Any]:
    """Convert RunSummary to a plain dict suitable for JSON serialization."""
    return {
        "scenario_id": summary.scenario_id,
        "run_id": summary.run_id,
        "log_path": summary.log_path,
        "log_sha256": summary.log_sha256,
        "total_events": summary.total_events,
        "logical_time": summary.logical_time,
        "nodes": [
            {
                "node_id": n.node_id,
                "finalized_height": n.finalized_height,
                "finalized_hash": n.finalized_hash,
                "state_hash": n.state_hash,
            }
            for n in summary.nodes
        ],
        "rejection_counts": summary.rejection_counts,
        "safety_ok": summary.safety_ok,
        "liveness_ok": summary.liveness_ok,
        "liveness_max_finalized_height": summary.liveness_max_finalized_height,
    }


def format_summary_json(summary: RunSummary, *, indent: int = 2) -> str:
    """Serialize RunSummary to a human-readable JSON string."""
    return json.dumps(to_dict(summary), indent=indent, ensure_ascii=False)


__all__ = [
    "NodeSummary",
    "RunSummary",
    "build_summary",
    "format_summary_json",
    "to_dict",
]
