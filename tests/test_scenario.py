import shutil
from pathlib import Path
import json

import pytest

from src.block import BlockHeader
from src.ledger import Ledger
from src.scenario import ScenarioRunner, _config_fingerprint

CHAIN_ID = "test-chain"
DEFAULT_CONFIG = {
    "chain_id": CHAIN_ID,
    "spec_version": "0.1",
}

def teardown_function():
    """Clean logs created by tests."""
    shutil.rmtree("logs", ignore_errors=True)

def make_header(height, round_=0, parent_hash=b"\x00" * 32, salt=b"\x00"):
    """
    A signed-looking header for Ledger tests. Ledger.finalize() only
    checks chain_id / height / parent_hash — it never verifies the signature
    so an unrelated random privkey/pubkey pair is fine here.
    """
    import os

    sk = os.urandom(32)
    pk = os.urandom(32)
    return BlockHeader.create_signed(
        chain_id=CHAIN_ID,
        height=height,
        round=round_,
        parent_hash=parent_hash,
        tx_root=salt * 32,
        state_hash=salt * 32,
        proposer_pubkey=pk,
        proposer_privkey=sk,
    )


def finalize_height_1(ledger: Ledger, salt: bytes) -> BlockHeader:
    from src.state import State

    header = make_header(height=1, salt=salt)
    ledger.finalize(
        header=header,
        applied_tx_ids=[],
        state=State(),
        nonces={},
    )
    return header


def test_load():
    scenario_config = {
        "scenario_id": "test_scenario",
        "run_id": "run1",
        "seed": 12345,
    }

    runner = ScenarioRunner(scenario_config, DEFAULT_CONFIG)
    runner.load()

    assert runner.event_log is not None
    assert runner.scheduler is not None
    assert runner.network is not None
    assert runner.fault_injector is not None

    # SCENARIO_START must already have been written as event_no=1.
    assert runner.event_log.event_count == 1

    runner.shutdown()


def test_execute_empty():
    scenario_config = {
        "scenario_id": "empty",
        "run_id": "run1",
        "seed": 1,
    }

    runner = ScenarioRunner(scenario_config, DEFAULT_CONFIG)

    payloads = runner.execute()

    assert payloads == []

    summary = runner.summary()

    # Only SCENARIO_START — no messages, no consensus.
    assert summary["event_count"] == 1
    assert Path(summary["log_path"]).exists()
    assert len(summary["log_sha256"]) == 64
    assert summary["logical_time"] == 0

    # No ledgers registered -> nothing to check, both trivially ok.
    assert summary["safety_ok"] is True
    assert summary["safety_violations"] == 0
    assert summary["liveness_ok"] is True  # max_height defaults to 0 (no-op)


def test_execute_with_messages():
    scenario_config = {
        "scenario_id": "messages",
        "run_id": "run1",
        "seed": 99,
        "messages": [
            {
                "sender": "A",
                "receiver": "B",
                "payload": b"hello",
                "logical_time": 5,
            },
            {
                "sender": "B",
                "receiver": "C",
                "payload": b"world",
                "logical_time": 7,
            },
        ],
    }

    runner = ScenarioRunner(scenario_config, DEFAULT_CONFIG)

    payloads = runner.execute()

    assert payloads == [
        b"hello",
        b"world",
    ]

    summary = runner.summary()

    # 1 SCENARIO_START + 2 SEND + 2 DELIVER
    assert summary["event_count"] == 5
    assert summary["logical_time"] == 7

# ---------------------------------------------------------------------
# spec_version / config_fingerprint (T3-15)
# ---------------------------------------------------------------------

def test_scenario_start_is_first_event_and_has_fingerprint():
    scenario_config = {
        "scenario_id": "fingerprint_check",
        "run_id": "run1",
        "seed": 7,
    }
    default_config = {"chain_id": CHAIN_ID, "spec_version": "0.1"}

    runner = ScenarioRunner(scenario_config, DEFAULT_CONFIG)
    runner.load()
    runner.shutdown()

    log_path = Path(runner.event_log.log_path)
    lines = log_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1  # only SCENARIO_START was written

    record = json.loads(lines[0])
    assert record["event_no"] == 1
    assert record["event_type"] == "SCENARIO_START"
    assert record["details"]["spec_version"] == "0.1"
    assert record["details"]["config_fingerprint"] == _config_fingerprint(default_config)
    # SHA-256 hex digest length.
    assert len(record["details"]["config_fingerprint"]) == 64


def test_config_fingerprint_changes_with_config():
    fp_a = _config_fingerprint({"a": 1, "b": 2})
    fp_b = _config_fingerprint({"b": 2, "a": 1})  # same content, different key order
    fp_c = _config_fingerprint({"a": 1, "b": 3})  # different content

    assert fp_a == fp_b  # sorted-key JSON makes ordering irrelevant
    assert fp_a != fp_c


def test_config_fingerprint_is_independent_of_scenario_config():
    """Two runs with the SAME default_config but DIFFERENT scenario_config
    (seed, run_id, messages...) must produce the SAME fingerprint"""
    
    default_config = {"chain_id": CHAIN_ID, "spec_version": "0.1"}

    scenario_a = {
        "scenario_id": "a",
        "run_id": "run_a",
        "seed": 1,
        "messages": [{"sender": "A", "receiver": "B", "payload": b"x", "logical_time": 0}],
    }
    scenario_b = {
        "scenario_id": "b",
        "run_id": "run_b",
        "seed": 999,
        "messages": [],
    }

    runner_a = ScenarioRunner(scenario_a, default_config)
    runner_a.load()
    runner_a.shutdown()
    fp_a = json.loads(
        Path(runner_a.event_log.log_path).read_text(encoding="utf-8").splitlines()[0]
    )["details"]["config_fingerprint"]

    runner_b = ScenarioRunner(scenario_b, default_config)
    runner_b.load()
    runner_b.shutdown()
    fp_b = json.loads(
        Path(runner_b.event_log.log_path).read_text(encoding="utf-8").splitlines()[0]
    )["details"]["config_fingerprint"]
    
    assert fp_a == fp_b


# event_no shared between ScenarioRunner and Network (regression check)
def test_event_no_is_monotonic_across_scenario_and_network():
    scenario_config = {
        "scenario_id": "event_no_check",
        "run_id": "run1",
        "seed": 3,
        "messages": [
            {"sender": "A", "receiver": "B", "payload": b"x", "logical_time": 1},
        ],
    }

    runner = ScenarioRunner(scenario_config, DEFAULT_CONFIG)
    runner.execute()

    log_path = Path(runner.event_log.log_path)
    lines = log_path.read_text(encoding="utf-8").splitlines()
    event_nos = [json.loads(line)["event_no"] for line in lines]

    assert event_nos == list(range(1, len(event_nos) + 1))
    assert event_nos[0] == 1  # SCENARIO_START
    # confirms Network did NOT restart its own counter at 1


# ---------------------------------------------------------------------
# Safety assertion
# ---------------------------------------------------------------------

def test_safety_ok_when_all_nodes_agree():
    scenario_config = {"scenario_id": "safety_ok", "run_id": "run1", "seed": 1}
    runner = ScenarioRunner(scenario_config, DEFAULT_CONFIG)

    ledger_a = Ledger(chain_id=CHAIN_ID)
    ledger_b = Ledger(chain_id=CHAIN_ID)
    header = finalize_height_1(ledger_a, salt=b"\xaa")
    # Both nodes finalize the SAME header -> same block_hash.
    from src.state import State

    ledger_b.finalize(header=header, applied_tx_ids=[], state=State(), nonces={})

    runner.register_ledger("node_a", ledger_a)
    runner.register_ledger("node_b", ledger_b)

    runner.check_assertions()

    assert runner.safety_result.ok
    assert runner.safety_result.violations == []


def test_safety_detects_conflicting_finalized_hashes():
    scenario_config = {"scenario_id": "safety_violation", "run_id": "run1", "seed": 1}
    runner = ScenarioRunner(scenario_config, DEFAULT_CONFIG)

    ledger_a = Ledger(chain_id=CHAIN_ID)
    ledger_b = Ledger(chain_id=CHAIN_ID)
    # Different salts -> different tx_root/state_hash -> different block_hash
    # at the SAME height 1.
    finalize_height_1(ledger_a, salt=b"\xaa")
    finalize_height_1(ledger_b, salt=b"\xbb")

    runner.register_ledger("node_a", ledger_a)
    runner.register_ledger("node_b", ledger_b)

    runner.check_assertions()

    assert not runner.safety_result.ok
    assert len(runner.safety_result.violations) == 1
    violation = runner.safety_result.violations[0]
    assert violation.height == 1
    assert len(violation.conflicting_hashes) == 2  # two distinct block_hash values
    all_nodes = sorted(n for nodes in violation.conflicting_hashes.values() for n in nodes)
    assert all_nodes == ["node_a", "node_b"]


# ---------------------------------------------------------------------
# Liveness assertion
# ---------------------------------------------------------------------

def test_liveness_ok_when_target_reached():
    scenario_config = {"scenario_id": "liveness_ok", "run_id": "run1", "seed": 1, "max_height": 1}
    runner = ScenarioRunner(scenario_config, DEFAULT_CONFIG)

    ledger = Ledger(chain_id=CHAIN_ID)
    finalize_height_1(ledger, salt=b"\xaa")
    runner.register_ledger("node_a", ledger)

    runner.check_assertions()

    assert runner.liveness_result.ok
    assert runner.liveness_result.min_expected_height == 1
    assert runner.liveness_result.max_finalized_height == 1


def test_liveness_fails_when_target_not_reached():
    scenario_config = {"scenario_id": "liveness_fail", "run_id": "run1", "seed": 1, "max_height": 5}
    runner = ScenarioRunner(scenario_config, DEFAULT_CONFIG)

    ledger = Ledger(chain_id=CHAIN_ID)
    finalize_height_1(ledger, salt=b"\xaa")  # only reaches height 1, target is 5
    runner.register_ledger("node_a", ledger)

    runner.check_assertions()

    assert not runner.liveness_result.ok
    assert runner.liveness_result.min_expected_height == 5
    assert runner.liveness_result.max_finalized_height == 1


def test_liveness_trivially_ok_for_noop_scenario():
    """max_height defaults to 0 (or is explicitly 0) -> no progress is
    expected, so liveness is trivially satisfied even with zero ledgers."""
    scenario_config = {"scenario_id": "noop", "run_id": "run1", "seed": 1, "max_height": 0}
    runner = ScenarioRunner(scenario_config, DEFAULT_CONFIG)

    runner.check_assertions()

    assert runner.liveness_result.ok
    assert runner.liveness_result.max_finalized_height == 0