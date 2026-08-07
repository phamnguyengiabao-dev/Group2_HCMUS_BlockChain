"""
Tests for T4-11 (crash simulation) and T4-12 (restart simulation)
in src/scenario.py.
"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

import pytest

from src.block import BlockHeader, compute_tx_root
from src.event_log import EventLog, EventType
from src.identity import load_validator_keys
from src.ledger import Ledger
from src.scenario import NodeCrashState, simulate_crash, simulate_restart
from src.state import State

CHAIN_ID = "test-crash"


# ================================================================
# Helpers
# ================================================================

def make_event_log(scenario_id: str) -> EventLog:
    return EventLog(scenario_id=scenario_id, run_id="run1")


def make_finalized_ledger(chain_id: str, storage_path: str | None = None) -> tuple[Ledger, bytes]:
    """Create a ledger with one finalized block, return (ledger, block_hash)."""
    validators = load_validator_keys()
    tx_root = compute_tx_root([])
    state_hash = State().state_hash()
    proposer = validators[0]

    header = BlockHeader.create_signed(
        chain_id=chain_id,
        height=1,
        round=0,
        parent_hash=b"\x00" * 32,
        tx_root=tx_root,
        state_hash=state_hash,
        proposer_pubkey=proposer.public_key,
        proposer_privkey=proposer.private_key,
    )

    ledger = Ledger(chain_id=chain_id, storage_path=storage_path)
    ledger.finalize(
        header=header,
        applied_tx_ids=[],
        state=State(),
        nonces={},
    )
    return ledger, header.block_hash()


@pytest.fixture(autouse=True)
def clean_logs():
    shutil.rmtree("logs/t_crash_restart", ignore_errors=True)
    yield


# ================================================================
# T4-11 simulate_crash
# ================================================================

def test_simulate_crash_returns_crash_state():
    event_log = make_event_log("crash_basic")
    state = simulate_crash(
        node_id="validator_0",
        logical_time=50,
        event_log=event_log,
        event_no=1,
    )
    assert isinstance(state, NodeCrashState)
    assert state.node_id == "validator_0"
    assert state.crashed_at == 50
    assert state.restarted_at is None
    assert state.snapshot_path is None
    event_log.close()


def test_simulate_crash_writes_crash_event():
    event_log = make_event_log("crash_event")
    simulate_crash(
        node_id="validator_1",
        logical_time=100,
        event_log=event_log,
        event_no=1,
    )
    assert event_log.event_count == 1
    event_log.close()


def test_simulate_crash_clears_in_memory_cache():
    """In-memory cache for the crashed node is cleared."""
    event_log = make_event_log("crash_cache")
    cache = {"validator_0": {"pending_blocks": [1, 2, 3], "votes": ["v1"]}, "validator_1": {"data": "kept"}}

    simulate_crash(
        node_id="validator_0",
        logical_time=10,
        event_log=event_log,
        event_no=1,
        in_memory_caches=cache,
    )

    # validator_0's cache is cleared
    assert "validator_0" not in cache or cache["validator_0"] is None or cache["validator_0"] == {}
    # validator_1's cache is untouched
    assert cache["validator_1"] == {"data": "kept"}
    event_log.close()


def test_simulate_crash_preserves_snapshot_path():
    """snapshot_path is recorded but the file is NOT deleted."""
    event_log = make_event_log("crash_snapshot_path")
    with tempfile.TemporaryDirectory() as tmpdir:
        snap_path = str(Path(tmpdir) / "ledger.json")
        # Create a dummy snapshot file
        Path(snap_path).write_text("{}")

        state = simulate_crash(
            node_id="validator_2",
            logical_time=20,
            event_log=event_log,
            event_no=1,
            snapshot_path=snap_path,
        )

        assert state.snapshot_path == snap_path
        # File still exists (not deleted)
        assert Path(snap_path).exists()
    event_log.close()


def test_simulate_crash_no_cache_key_is_noop():
    """Crash of a node not in the cache dict is a no-op for other nodes."""
    event_log = make_event_log("crash_no_key")
    cache = {"validator_1": {"x": 1}}

    simulate_crash(
        node_id="validator_0",
        logical_time=5,
        event_log=event_log,
        event_no=1,
        in_memory_caches=cache,
    )

    assert cache == {"validator_1": {"x": 1}}
    event_log.close()


# ================================================================
# T4-12 simulate_restart
# ================================================================

def test_simulate_restart_returns_updated_state_and_ledger():
    """Restart without a snapshot creates an empty ledger and logs RESTART."""
    event_log = make_event_log("restart_empty")
    crash_state = NodeCrashState(
        node_id="validator_0",
        crashed_at=50,
    )

    updated, ledger = simulate_restart(
        crash_state=crash_state,
        logical_time=80,
        event_log=event_log,
        event_no=1,
        chain_id=CHAIN_ID,
    )

    assert updated.node_id == "validator_0"
    assert updated.crashed_at == 50
    assert updated.restarted_at == 80
    assert isinstance(ledger, Ledger)
    assert ledger.finalized_height == 0
    event_log.close()


def test_simulate_restart_writes_restart_event():
    event_log = make_event_log("restart_event")
    crash_state = NodeCrashState(node_id="validator_0", crashed_at=10)

    simulate_restart(
        crash_state=crash_state,
        logical_time=20,
        event_log=event_log,
        event_no=1,
        chain_id=CHAIN_ID,
    )

    assert event_log.event_count == 1
    event_log.close()


def test_simulate_restart_loads_snapshot():
    """Restart with a valid snapshot recovers the finalized height."""
    with tempfile.TemporaryDirectory() as tmpdir:
        snap_path = str(Path(tmpdir) / "ledger.json")
        ledger_orig, block_hash = make_finalized_ledger(CHAIN_ID, storage_path=snap_path)
        assert ledger_orig.finalized_height == 1

        event_log = make_event_log("restart_snapshot")
        crash_state = NodeCrashState(
            node_id="validator_0",
            crashed_at=30,
            snapshot_path=snap_path,
        )

        updated, recovered = simulate_restart(
            crash_state=crash_state,
            logical_time=60,
            event_log=event_log,
            event_no=1,
            chain_id=CHAIN_ID,
        )

        assert recovered.finalized_height == 1
        assert recovered.finalized_hash == block_hash
        assert updated.restarted_at == 60
        event_log.close()


def test_simulate_restart_discards_unfinalized_data():
    """Recovery from snapshot only restores finalized data (F-53)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        snap_path = str(Path(tmpdir) / "ledger.json")
        ledger_orig, _ = make_finalized_ledger(CHAIN_ID, storage_path=snap_path)

        event_log = make_event_log("restart_discard")
        crash_state = NodeCrashState(
            node_id="validator_0",
            crashed_at=40,
            snapshot_path=snap_path,
        )

        _, recovered = simulate_restart(
            crash_state=crash_state,
            logical_time=70,
            event_log=event_log,
            event_no=1,
            chain_id=CHAIN_ID,
        )

        # Only height 1 is finalized — no pending proposals/votes
        assert len(recovered) == 1
        assert recovered.is_finalized(1)
        # Height 2 was never finalized
        assert not recovered.is_finalized(2)
        event_log.close()


def test_crash_then_restart_full_cycle():
    """Crash → restart → verify recovered state matches original."""
    with tempfile.TemporaryDirectory() as tmpdir:
        snap_path = str(Path(tmpdir) / "ledger.json")
        ledger_orig, original_hash = make_finalized_ledger(CHAIN_ID, storage_path=snap_path)

        event_log = make_event_log("crash_restart_cycle")

        crash_state = simulate_crash(
            node_id="validator_3",
            logical_time=100,
            event_log=event_log,
            event_no=1,
            snapshot_path=snap_path,
        )

        updated_state, recovered_ledger = simulate_restart(
            crash_state=crash_state,
            logical_time=150,
            event_log=event_log,
            event_no=2,
            chain_id=CHAIN_ID,
        )

        # State
        assert updated_state.node_id == "validator_3"
        assert updated_state.crashed_at == 100
        assert updated_state.restarted_at == 150

        # Ledger integrity
        assert recovered_ledger.finalized_height == 1
        assert recovered_ledger.finalized_hash == original_hash

        # 2 events were written (CRASH + RESTART)
        assert event_log.event_count == 2
        event_log.close()


def test_simulate_restart_without_snapshot_starts_empty():
    """No snapshot path → empty ledger (height 0), not an error."""
    event_log = make_event_log("restart_no_snap")
    crash_state = NodeCrashState(node_id="validator_5", crashed_at=10, snapshot_path=None)

    _, recovered = simulate_restart(
        crash_state=crash_state,
        logical_time=20,
        event_log=event_log,
        event_no=1,
        chain_id=CHAIN_ID,
    )

    assert recovered.finalized_height == 0
    assert len(recovered) == 0
    event_log.close()
