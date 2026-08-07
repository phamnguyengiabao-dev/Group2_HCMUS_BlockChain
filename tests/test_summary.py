"""
Tests for src/summary.py (T5-09).
"""

from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path

import pytest

from src.block import BlockHeader, compute_tx_root
from src.event_log import EventLog
from src.identity import load_validator_keys
from src.ledger import Ledger
from src.network import Network
from src.scenario import ScenarioRunner
from src.scheduler import Scheduler
from src.state import State
from src.summary import (
    NodeSummary,
    RunSummary,
    _count_rejections,
    build_summary,
    format_summary_json,
    to_dict,
)

CHAIN_ID = "summary-test"


# ================================================================
# Helpers
# ================================================================

def make_noop_runner() -> ScenarioRunner:
    """Create a ScenarioRunner for a no-op scenario (max_height=0)."""
    scenario_config = {
        "scenario_id": "summary_noop",
        "seed": 99,
        "max_height": 0,
    }
    default_config = {"spec_version": "0.1"}
    return ScenarioRunner(scenario_config, default_config)


def make_finalized_ledger(chain_id: str) -> tuple[Ledger, bytes]:
    validators = load_validator_keys()
    header = BlockHeader.create_signed(
        chain_id=chain_id,
        height=1,
        round=0,
        parent_hash=b"\x00" * 32,
        tx_root=compute_tx_root([]),
        state_hash=State().state_hash(),
        proposer_pubkey=validators[0].public_key,
        proposer_privkey=validators[0].private_key,
    )
    ledger = Ledger(chain_id=chain_id)
    ledger.finalize(header=header, applied_tx_ids=[], state=State(), nonces={})
    return ledger, header.block_hash()


def write_reject_events(log_path: Path, codes: list[str]) -> None:
    """Append fake REJECT JSONL lines to an existing log file."""
    with log_path.open("a", encoding="utf-8") as fh:
        for code in codes:
            record = {
                "event_no": 999,
                "logical_time": 0,
                "node_id": "router",
                "event_type": "REJECT",
                "height": 1,
                "round": 0,
                "details": {"code": code},
            }
            fh.write(json.dumps(record, separators=(",", ":")) + "\n")


@pytest.fixture(autouse=True)
def clean_logs():
    yield
    shutil.rmtree("logs", ignore_errors=True)


# ================================================================
# build_summary — basic structure
# ================================================================

def test_build_summary_raises_before_execute():
    runner = ScenarioRunner({"scenario_id": "x", "seed": 1}, {})
    with pytest.raises(RuntimeError):
        build_summary(runner)


def test_build_summary_noop_scenario():
    runner = make_noop_runner()
    runner.execute()

    summary = build_summary(runner)

    assert isinstance(summary, RunSummary)
    assert summary.scenario_id == "summary_noop"
    assert summary.total_events > 0
    assert summary.log_sha256 != ""
    assert len(summary.log_sha256) == 64  # sha256 hex


def test_build_summary_no_ledgers_empty_nodes():
    runner = make_noop_runner()
    runner.execute()

    summary = build_summary(runner)

    # noop runner registers no ledgers
    assert summary.nodes == []


def test_build_summary_with_ledger():
    runner = make_noop_runner()
    runner.execute()

    ledger, block_hash = make_finalized_ledger(CHAIN_ID)
    runner.ledgers["node_a"] = ledger

    summary = build_summary(runner)

    assert len(summary.nodes) == 1
    node = summary.nodes[0]
    assert node.node_id == "node_a"
    assert node.finalized_height == 1
    assert node.finalized_hash == block_hash.hex()
    assert len(node.state_hash) == 64


def test_build_summary_nodes_sorted_by_node_id():
    runner = make_noop_runner()
    runner.execute()

    for name in ["node_c", "node_a", "node_b"]:
        ledger, _ = make_finalized_ledger(CHAIN_ID)
        runner.ledgers[name] = ledger

    summary = build_summary(runner)

    assert [n.node_id for n in summary.nodes] == ["node_a", "node_b", "node_c"]


def test_build_summary_empty_ledger_gives_empty_hashes():
    runner = make_noop_runner()
    runner.execute()

    runner.ledgers["node_empty"] = Ledger(chain_id=CHAIN_ID)
    summary = build_summary(runner)

    node = summary.nodes[0]
    assert node.finalized_height == 0
    assert node.finalized_hash == ""
    assert node.state_hash == ""


# ================================================================
# rejection counts
# ================================================================

def test_count_rejections_empty_file(tmp_path):
    empty = tmp_path / "empty.jsonl"
    empty.write_text("")
    assert _count_rejections(empty) == {}


def test_count_rejections_no_file(tmp_path):
    missing = tmp_path / "missing.jsonl"
    assert _count_rejections(missing) == {}


def test_count_rejections_multiple_codes(tmp_path):
    log = tmp_path / "test.jsonl"
    log.write_text("")
    write_reject_events(log, ["CHAIN_ID_MISMATCH", "UNKNOWN_SENDER", "CHAIN_ID_MISMATCH"])

    counts = _count_rejections(log)

    assert counts["CHAIN_ID_MISMATCH"] == 2
    assert counts["UNKNOWN_SENDER"] == 1


def test_count_rejections_sorted_alphabetically(tmp_path):
    log = tmp_path / "test.jsonl"
    log.write_text("")
    write_reject_events(log, ["UNKNOWN_SENDER", "CHAIN_ID_MISMATCH", "PAYLOAD_MISMATCH"])

    counts = _count_rejections(log)

    assert list(counts.keys()) == sorted(counts.keys())


def test_count_rejections_in_summary():
    runner = make_noop_runner()
    runner.execute()

    # Manually inject REJECT lines into the log
    write_reject_events(
        runner.event_log.log_path,
        ["INVALID_SIGNATURE", "INVALID_SIGNATURE", "CHAIN_ID_MISMATCH"],
    )

    summary = build_summary(runner)

    assert summary.rejection_counts.get("INVALID_SIGNATURE") == 2
    assert summary.rejection_counts.get("CHAIN_ID_MISMATCH") == 1


# ================================================================
# safety / liveness fields
# ================================================================

def test_build_summary_safety_liveness_from_runner():
    runner = make_noop_runner()
    runner.execute()  # calls check_assertions() internally

    summary = build_summary(runner)

    # noop scenario: safety=True (no conflicts), liveness=True (max_height=0)
    assert summary.safety_ok is True
    assert summary.liveness_ok is True


# ================================================================
# to_dict / format_summary_json
# ================================================================

def test_to_dict_is_json_serializable():
    runner = make_noop_runner()
    runner.execute()
    summary = build_summary(runner)
    d = to_dict(summary)
    # Must serialize without error
    encoded = json.dumps(d)
    assert isinstance(encoded, str)


def test_to_dict_required_keys():
    runner = make_noop_runner()
    runner.execute()
    d = to_dict(build_summary(runner))

    required = {
        "scenario_id", "run_id", "log_path", "log_sha256",
        "total_events", "logical_time", "nodes",
        "rejection_counts", "safety_ok", "liveness_ok",
        "liveness_max_finalized_height",
    }
    assert required <= set(d.keys())


def test_format_summary_json_is_valid_json():
    runner = make_noop_runner()
    runner.execute()
    json_str = format_summary_json(build_summary(runner))
    parsed = json.loads(json_str)
    assert parsed["scenario_id"] == "summary_noop"


def test_format_summary_json_node_fields():
    runner = make_noop_runner()
    runner.execute()
    ledger, block_hash = make_finalized_ledger(CHAIN_ID)
    runner.ledgers["v0"] = ledger

    json_str = format_summary_json(build_summary(runner))
    parsed = json.loads(json_str)

    assert len(parsed["nodes"]) == 1
    node = parsed["nodes"][0]
    assert set(node.keys()) == {"node_id", "finalized_height", "finalized_hash", "state_hash"}
    assert node["finalized_hash"] == block_hash.hex()
