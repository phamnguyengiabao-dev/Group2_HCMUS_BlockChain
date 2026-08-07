"""
T5-04

Scenario T4 — Replay + duplicate tx.

Submitting the same `tx_id` twice must never apply it twice, in either
of the two ways a duplicate can reach the pipeline:

    1. Same block, submitted twice: the SAME Transaction object appears
       twice in one block's pending_transactions. Caught by the
       executor's P3 guard (DUPLICATE_TX_ID) -> the whole candidate
       block is rejected by propose(), nothing is ever finalized.

    2. Replay across heights: a transaction that was already finalized
       at an earlier height is resubmitted as a pending transaction at
       a later height. The sender's nonce already advanced when it was
       first applied, so the replay's nonce is stale -> the executor
       rejects it (INVALID_NONCE) and propose() fails -> the ledger's
       history still reflects exactly one application of that tx_id.

This builds on the same manual 8-node driver as test_t1.py.
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path

import pytest

from src.consensus import (
    ConsensusState,
    apply_lock,
    make_precommit,
    make_prevote,
    propose,
    select_proposer,
    try_finalize,
)
from src.crypto import hash_bytes, sign
from src.executor import ExecutionConfig, execute_block
from src.identity import load_validator_keys
from src.ledger import Ledger
from src.scenario import ScenarioRunner
from src.transaction import Transaction

CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"


def load_config(name: str) -> dict:
    with (CONFIG_DIR / name).open("r", encoding="utf-8") as fh:
        return json.load(fh)


@pytest.fixture(autouse=True)
def clean_logs():
    yield
    shutil.rmtree("logs", ignore_errors=True)


# ---------------------------------------------------------------------
# Config structure
# ---------------------------------------------------------------------

def test_scenario_t4_config_structure():
    """scenario_t4.json declares an 8-node run submitting one tx, with
    replay of that same tx expected to be exercised."""
    config = load_config("scenario_t4.json")

    assert config["scenario_id"] == "t4_replay_duplicate_tx"
    assert isinstance(config["seed"], int)

    assert config["num_validators"] == 8
    assert config["f"] == 2
    assert config["max_height"] == 1
    assert config["byzantine_nodes"] == []
    assert config["topology"] == "full_mesh"

    assert config["transactions"] == [{"sender_index": 0}]
    assert config["replay_transactions"] is True

    faults = config["faults"]
    for key in (
        "drop_probability",
        "delay_probability",
        "duplicate_probability",
        "reorder_probability",
    ):
        assert faults[key] == 0.0


# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------

def _make_tx(sender, *, chain_id: str, nonce: int, key_suffix: str = "t4", value: bytes = b"replay-me") -> Transaction:
    namespace = hash_bytes(sender.public_key).hex() + "/"
    key = namespace + key_suffix

    unsigned = Transaction(
        chain_id=chain_id, nonce=nonce, sender_pubkey=sender.public_key,
        key=key, value_bytes=value, signature=b"",
    )
    signature = sign(sender.private_key, f"TX:{chain_id}", unsigned.unsigned_bytes())
    return Transaction(
        chain_id=chain_id, nonce=nonce, sender_pubkey=sender.public_key,
        key=key, value_bytes=value, signature=signature,
    )


@dataclass
class Harness:
    chain_id: str
    validators: list
    node_ids: list[str]
    states: dict
    ledgers: dict
    network: object
    exec_config: ExecutionConfig
    validator_count: int


def _build_harness(scenario_config: dict, default_config: dict, runner: ScenarioRunner) -> Harness:
    chain_id = default_config["chain_id"]
    validators = load_validator_keys()
    node_ids = [f"validator_{v.index}" for v in validators]

    return Harness(
        chain_id=chain_id,
        validators=validators,
        node_ids=node_ids,
        states={nid: ConsensusState(height=1) for nid in node_ids},
        ledgers={nid: Ledger(chain_id=chain_id) for nid in node_ids},
        network=runner.network,
        exec_config=ExecutionConfig(
            chain_id=chain_id,
            max_key_size=default_config["network"]["max_key_size_bytes"],
            max_value_size=default_config["network"]["max_value_size_bytes"],
        ),
        validator_count=scenario_config["num_validators"],
    )


def _propose_prevote_precommit_finalize(h: Harness, *, height: int, pending_transactions: list[Transaction], logical_time: int) -> tuple:
    """Run one full successful height through the 8-node pipeline.
    Returns (header, block_hash, next_logical_time)."""
    round_ = 0
    proposer = select_proposer(height, round_)
    proposer_node_id = h.node_ids[proposer.index]
    broadcast_peers = [nid for nid in h.node_ids if nid != proposer_node_id]

    result = propose(
        h.states[proposer_node_id],
        network=h.network,
        ledger=h.ledgers[proposer_node_id],
        self_identity=proposer,
        validator_node_ids=h.node_ids,
        peers=broadcast_peers,
        pending_transactions=pending_transactions,
        chain_id=h.chain_id,
        exec_config=h.exec_config,
        logical_time=logical_time,
    )
    assert result.success, result.reason
    header = result.header
    block_hash = header.block_hash()

    h.network.run()
    logical_time += 1

    for nid in h.node_ids:
        h.states[nid].block_store.store_header(header)
        h.states[nid].block_store.store_body(block_hash, pending_transactions)

    prevotes = [
        make_prevote(
            h.states[h.node_ids[v.index]],
            chain_id=h.chain_id,
            self_identity=v,
            proposed_block_hash=block_hash,
            validator_count=h.validator_count,
        )
        for v in h.validators
    ]
    for nid in h.node_ids:
        for vote in prevotes:
            h.states[nid].prevotes.add(vote)
    for nid in h.node_ids:
        apply_lock(h.states[nid], round=round_, validator_count=h.validator_count)

    precommits = []
    for v in h.validators:
        nid = h.node_ids[v.index]
        peers_of_nid = [n for n in h.node_ids if n != nid]
        precommit_result = make_precommit(
            h.states[nid], chain_id=h.chain_id, self_identity=v,
            validator_count=h.validator_count, network=h.network,
            validator_node_ids=h.node_ids, peers=peers_of_nid,
            logical_time=logical_time,
        )
        precommits.append(precommit_result.vote)

    h.network.run()
    logical_time += 1

    for nid in h.node_ids:
        for vote in precommits:
            h.states[nid].precommits.add(vote)

    for nid in h.node_ids:
        fin = try_finalize(
            h.states[nid], ledger=h.ledgers[nid], chain_id=h.chain_id,
            exec_config=h.exec_config, validator_count=h.validator_count,
        )
        assert fin.success, fin.reason
        assert fin.entry.height == height
        assert fin.entry.block_hash == block_hash

    return header, block_hash, logical_time


# ---------------------------------------------------------------------
# Case 1: same tx_id submitted twice in the SAME block
# ---------------------------------------------------------------------

def test_t4_duplicate_tx_in_same_block_rejected_and_nothing_finalizes():
    scenario_config = {**load_config("scenario_t4.json"), "run_id": "t4_dup_block"}
    default_config = load_config("default.json")

    runner = ScenarioRunner(scenario_config, default_config)
    runner.load()
    h = _build_harness(scenario_config, default_config, runner)

    sender = h.validators[0]
    tx = _make_tx(sender, chain_id=h.chain_id, nonce=0)

    proposer = select_proposer(1, 0)
    proposer_node_id = h.node_ids[proposer.index]
    broadcast_peers = [nid for nid in h.node_ids if nid != proposer_node_id]

    result = propose(
        h.states[proposer_node_id],
        network=h.network,
        ledger=h.ledgers[proposer_node_id],
        self_identity=proposer,
        validator_node_ids=h.node_ids,
        peers=broadcast_peers,
        pending_transactions=[tx, tx],  # same tx_id submitted twice
        chain_id=h.chain_id,
        exec_config=h.exec_config,
        logical_time=0,
    )

    assert result.success is False
    assert result.header is None
    assert "EXECUTION_REJECTED" in result.reason
    assert "DUPLICATE_TX_ID" in result.reason

    # Nothing was ever proposed, so nothing can have finalized.
    assert h.ledgers[proposer_node_id].finalized_height == 0
    assert h.network.run() == []  # propose() sent nothing

    runner.shutdown()


# ---------------------------------------------------------------------
# Case 2: replay across heights -- resubmitting an already-finalized tx
# ---------------------------------------------------------------------

def _run_t4_replay_scenario():
    scenario_config = {**load_config("scenario_t4.json"), "run_id": "t4_replay"}
    default_config = load_config("default.json")

    runner = ScenarioRunner(scenario_config, default_config)
    runner.load()
    h = _build_harness(scenario_config, default_config, runner)

    sender = h.validators[0]
    tx = _make_tx(sender, chain_id=h.chain_id, nonce=0)

    # Height 1: the tx is submitted and finalized normally -- exactly one
    # honest application.
    header1, block_hash1, logical_time = _propose_prevote_precommit_finalize(
        h, height=1, pending_transactions=[tx], logical_time=0,
    )

    for nid in h.node_ids:
        assert h.ledgers[nid].finalized_height == 1
        assert h.ledgers[nid].finalized_hash == block_hash1
        assert h.ledgers[nid].get_nonces(1).get(sender.public_key) == 1
        assert h.ledgers[nid].get_state(1).get(tx.key) == tx.value_bytes

    # Height 2, pipeline level: the actual height-2 proposer refuses to
    # build a block that replays the exact same tx (nonce already
    # advanced by height 1 -> stale replay).
    proposer2 = select_proposer(2, 0)
    proposer2_node_id = h.node_ids[proposer2.index]
    propose_result = propose(
        h.states[proposer2_node_id],
        network=h.network,
        ledger=h.ledgers[proposer2_node_id],
        self_identity=proposer2,
        validator_node_ids=h.node_ids,
        peers=[n for n in h.node_ids if n != proposer2_node_id],
        pending_transactions=[tx],  # replay of the height-1 tx
        chain_id=h.chain_id,
        exec_config=h.exec_config,
        logical_time=logical_time,
    )

    # Executor level: every correct node's own view of finalized history
    # independently rejects the replay too, not just the proposer's.
    executor_results = {
        nid: execute_block(
            [tx],
            h.ledgers[nid].get_state(1),
            h.ledgers[nid].get_nonces(1),
            h.exec_config,
        )
        for nid in h.node_ids
    }

    runner.shutdown()
    return h, tx, header1, block_hash1, propose_result, executor_results


def test_t4_replay_at_later_height_rejected_on_second_submission():
    h, tx, header1, block_hash1, propose_result, executor_results = _run_t4_replay_scenario()

    # Pipeline level: the height-2 proposer refuses to build the replay.
    assert propose_result.success is False, "replay of an already-applied tx must be rejected"
    assert propose_result.header is None
    assert "EXECUTION_REJECTED" in propose_result.reason
    assert "INVALID_NONCE" in propose_result.reason

    # Executor level: every node's own history independently rejects it.
    for nid, exec_result in executor_results.items():
        assert exec_result.success is False, nid
        assert "INVALID_NONCE" in (exec_result.error_reason or "")
        # Rejected execution must never mutate state/nonces (P1 atomicity).
        assert exec_result.post_state == h.ledgers[nid].get_state(1)
        assert exec_result.nonces == h.ledgers[nid].get_nonces(1)

    assert h.network.run() == []  # nothing was ever sent by a failed proposal


def test_t4_state_reflects_exactly_one_application():
    h, tx, header1, block_hash1, propose_result, executor_results = _run_t4_replay_scenario()

    for nid in h.node_ids:
        ledger = h.ledgers[nid]

        # The replay attempt never finalized anything past height 1.
        assert ledger.finalized_height == 1
        assert not ledger.is_finalized(2)

        # The write happened exactly once: one entry, the original value,
        # and the sender's nonce advanced exactly once (not twice).
        state = ledger.get_state(1)
        assert state.get(tx.key) == tx.value_bytes
        assert len(state) == 1
        assert ledger.get_nonces(1).get(tx.sender_pubkey) == 1


def test_t4_scenario_assertions_hold_after_replay_attempt():
    h, tx, header1, block_hash1, propose_result, executor_results = _run_t4_replay_scenario()

    scenario_config = {**load_config("scenario_t4.json"), "run_id": "t4_assertions"}
    default_config = load_config("default.json")
    runner = ScenarioRunner(scenario_config, default_config)
    runner.load()

    for nid in h.node_ids:
        runner.register_ledger(nid, h.ledgers[nid])

    runner.check_assertions()

    assert runner.safety_result.ok
    assert runner.safety_result.violations == []
    assert runner.liveness_result.ok
    assert runner.liveness_result.max_finalized_height == 1  # scenario max_height

    runner.shutdown()
