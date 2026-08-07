"""
consensus_log_helper.py — Shared helpers for logging consensus events
into the canonical event log during test scenario runs.

Every test that drives the consensus pipeline manually (propose →
prevote → lock → precommit → finalize) should import and use these
helpers so that the JSONL log files produced under logs/ contain the
full set of protocol events required by Lab01.pdf §8:

  PROPOSE, PREVOTE, LOCK, PRECOMMIT, FINALIZE

These supplement the SEND/DELIVER events that the Network layer already
writes automatically.
"""

from __future__ import annotations

from src.consensus import ConsensusState
from src.event_log import EventType
from src.scenario import ScenarioRunner
from src.vote import Vote


def log_propose(
    runner: ScenarioRunner,
    *,
    proposer_node_id: str,
    block_hash: bytes,
    tx_count: int,
    height: int,
    round_: int,
    logical_time: int,
) -> None:
    """Write one PROPOSE event to the canonical log."""
    runner.event_log.write_event(
        event_no=runner._next_event_no(),
        logical_time=max(logical_time, runner.network.logical_time),
        node_id=proposer_node_id,
        event_type=EventType.PROPOSE,
        height=height,
        round=round_,
        details={
            "block_hash": block_hash.hex(),
            "proposer": proposer_node_id,
            "tx_count": tx_count,
        },
    )


def log_prevotes(
    runner: ScenarioRunner,
    *,
    node_ids: list[str],
    prevotes: list[Vote],
    height: int,
    round_: int,
    logical_time: int,
) -> None:
    """Write one PREVOTE event per validator to the canonical log."""
    t = max(logical_time, runner.network.logical_time)
    for nid, vote in zip(node_ids, prevotes):
        runner.event_log.write_event(
            event_no=runner._next_event_no(),
            logical_time=t,
            node_id=nid,
            event_type=EventType.PREVOTE,
            height=height,
            round=round_,
            details={
                "block_hash": (
                    vote.block_hash_or_nil.hex()
                    if vote.block_hash_or_nil is not None
                    else "nil"
                ),
                "validator": nid,
            },
        )


def log_locks(
    runner: ScenarioRunner,
    *,
    node_ids: list[str],
    states: dict[str, ConsensusState],
    height: int,
    round_: int,
    logical_time: int,
) -> None:
    """Write one LOCK event per validator that has a lock set."""
    t = max(logical_time, runner.network.logical_time)
    for nid in node_ids:
        locked_hash = states[nid].locked_block_hash
        if locked_hash is not None:
            runner.event_log.write_event(
                event_no=runner._next_event_no(),
                logical_time=t,
                node_id=nid,
                event_type=EventType.LOCK,
                height=height,
                round=round_,
                details={
                    "block_hash": locked_hash.hex(),
                    "locked_round": states[nid].locked_round,
                    "validator": nid,
                },
            )


def log_precommits(
    runner: ScenarioRunner,
    *,
    node_ids: list[str],
    precommits: list[Vote],
    height: int,
    round_: int,
    logical_time: int,
) -> None:
    """Write one PRECOMMIT event per validator to the canonical log."""
    t = max(logical_time, runner.network.logical_time)
    for nid, vote in zip(node_ids, precommits):
        runner.event_log.write_event(
            event_no=runner._next_event_no(),
            logical_time=t,
            node_id=nid,
            event_type=EventType.PRECOMMIT,
            height=height,
            round=round_,
            details={
                "block_hash": (
                    vote.block_hash_or_nil.hex()
                    if vote.block_hash_or_nil is not None
                    else "nil"
                ),
                "validator": nid,
            },
        )


def log_finalizes(
    runner: ScenarioRunner,
    *,
    node_ids: list[str],
    ledgers: dict,
    block_hash: bytes,
    height: int,
    round_: int,
    logical_time: int,
) -> None:
    """Write one FINALIZE event per validator to the canonical log."""
    t = max(logical_time, runner.network.logical_time)
    for nid in node_ids:
        try:
            state_hash = ledgers[nid].get_state(height).state_hash().hex()
        except KeyError:
            state_hash = ""
        runner.event_log.write_event(
            event_no=runner._next_event_no(),
            logical_time=t,
            node_id=nid,
            event_type=EventType.FINALIZE,
            height=height,
            round=round_,
            details={
                "block_hash": block_hash.hex(),
                "state_hash": state_hash,
                "validator": nid,
            },
        )
