"""T5-08: same seed produces byte-identical logs and state hashes."""

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
from src.event_log import EventType
from src.executor import ExecutionConfig
from src.identity import load_validator_keys
from src.ledger import Ledger
from src.scenario import ScenarioRunner
from src.transaction import Transaction, encode_transaction_list
from src.vote import Vote

CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"


def _load_config(name: str) -> dict:
    with (CONFIG_DIR / name).open("r", encoding="utf-8") as file:
        return json.load(file)


@pytest.fixture(autouse=True)
def clean_logs():
    yield
    shutil.rmtree("logs", ignore_errors=True)


@dataclass
class FaultTrace:
    delayed: int = 0
    duplicated: int = 0
    reordered: int = 0


@dataclass
class T8Run:
    log_bytes: bytes
    log_sha256: str
    state_hashes: dict[str, bytes]
    finalized_heads: dict[str, tuple[int, bytes]]
    fault_trace: FaultTrace


def _signed_transaction(sender, *, chain_id: str) -> Transaction:
    key = f"{hash_bytes(sender.public_key).hex()}/t8-determinism"
    unsigned = Transaction(
        chain_id=chain_id,
        nonce=0,
        sender_pubkey=sender.public_key,
        key=key,
        value_bytes=b"same-seed-same-state",
        signature=b"",
    )
    signature = sign(sender.private_key, f"TX:{chain_id}", unsigned.unsigned_bytes())
    return Transaction(
        chain_id=unsigned.chain_id,
        nonce=unsigned.nonce,
        sender_pubkey=unsigned.sender_pubkey,
        key=unsigned.key,
        value_bytes=unsigned.value_bytes,
        signature=signature,
    )


def _schedule_faulted_copy(
    runner: ScenarioRunner,
    *,
    sender: str,
    receiver: str,
    payload: bytes,
    logical_time: int,
    trace: FaultTrace,
) -> tuple[int, bool]:
    fault = runner.fault_injector.apply()
    assert not fault.dropped, "T8 config must retain every message"
    if fault.delay:
        trace.delayed += 1
    if fault.duplicate_count:
        trace.duplicated += fault.duplicate_count
    if fault.reorder:
        trace.reordered += 1

    copies = 1 + fault.duplicate_count
    for _ in range(copies):
        runner.network.send(
            sender=sender,
            receiver=receiver,
            payload=payload,
            logical_time=logical_time + fault.delay,
            height=1,
            round=0,
        )
    return copies, fault.reorder


def _distribute_votes(
    runner: ScenarioRunner,
    *,
    votes: list[Vote],
    node_ids: list[str],
    states: dict[str, ConsensusState],
    vote_set_name: str,
    logical_time: int,
    trace: FaultTrace,
) -> None:
    for receiver_index, receiver in enumerate(node_ids):
        plan: list[Vote] = []
        should_reorder = False
        for sender_index, sender in enumerate(node_ids):
            if sender_index == receiver_index:
                continue  # make_prevote/make_precommit already stored own vote
            vote = votes[sender_index]
            copies, reorder = _schedule_faulted_copy(
                runner,
                sender=sender,
                receiver=receiver,
                payload=vote.signed_bytes(),
                logical_time=logical_time,
                trace=trace,
            )
            plan.extend([vote] * copies)
            should_reorder = should_reorder or reorder

        if should_reorder and len(plan) > 1:
            plan = runner.scheduler.rng_shuffle_copy(plan)
        vote_set = getattr(states[receiver], vote_set_name)
        for vote in plan:
            vote_set.add(vote)
    runner.network.run()


def _run_t8_once() -> T8Run:
    # The run ID is deliberately identical on both executions: it is part of
    # the canonical SCENARIO_START event and therefore part of replay input.
    scenario = {**_load_config("scenario_t8.json"), "run_id": "t8_same_seed"}
    defaults = _load_config("default.json")
    chain_id = defaults["chain_id"]
    validators = load_validator_keys()
    node_ids = [f"validator_{validator.index}" for validator in validators]
    validator_count = len(validators)

    runner = ScenarioRunner(scenario, defaults)
    runner.load()
    states = {node_id: ConsensusState(height=1) for node_id in node_ids}
    ledgers = {node_id: Ledger(chain_id=chain_id) for node_id in node_ids}
    execution_config = ExecutionConfig(
        chain_id=chain_id,
        max_key_size=defaults["network"]["max_key_size_bytes"],
        max_value_size=defaults["network"]["max_value_size_bytes"],
    )
    trace = FaultTrace()
    transaction = _signed_transaction(validators[0], chain_id=chain_id)

    proposer = select_proposer(1, 0)
    proposer_node_id = node_ids[proposer.index]
    proposal = propose(
        states[proposer_node_id],
        network=runner.network,
        ledger=ledgers[proposer_node_id],
        self_identity=proposer,
        validator_node_ids=node_ids,
        peers=[],
        pending_transactions=[transaction],
        chain_id=chain_id,
        exec_config=execution_config,
        logical_time=0,
    )
    assert proposal.success, proposal.reason
    header = proposal.header
    block_hash = header.block_hash()

    for receiver in node_ids:
        if receiver == proposer_node_id:
            continue
        _schedule_faulted_copy(
            runner,
            sender=proposer_node_id,
            receiver=receiver,
            payload=header.signed_bytes(),
            logical_time=0,
            trace=trace,
        )
        _schedule_faulted_copy(
            runner,
            sender=proposer_node_id,
            receiver=receiver,
            payload=encode_transaction_list([transaction]),
            logical_time=0,
            trace=trace,
        )
    runner.network.run()

    # The node layer applies header before body even if the network reordered
    # their arrivals, preserving the protocol's header-first store rule.
    for state in states.values():
        assert state.block_store.store_header(header).success
        assert state.block_store.store_body(block_hash, [transaction]).success

    prevotes = [
        make_prevote(
            states[node_ids[validator.index]],
            chain_id=chain_id,
            self_identity=validator,
            proposed_block_hash=block_hash,
            validator_count=validator_count,
        )
        for validator in validators
    ]
    _distribute_votes(
        runner,
        votes=prevotes,
        node_ids=node_ids,
        states=states,
        vote_set_name="prevotes",
        logical_time=runner.network.logical_time + 1,
        trace=trace,
    )
    for state in states.values():
        assert apply_lock(state, round=0, validator_count=validator_count) == block_hash

    precommits = []
    for validator, node_id in zip(validators, node_ids):
        result = make_precommit(
            states[node_id],
            chain_id=chain_id,
            self_identity=validator,
            validator_count=validator_count,
            network=runner.network,
            validator_node_ids=node_ids,
            peers=[],
            logical_time=runner.network.logical_time + 1,
        )
        assert result.block_hash_or_nil == block_hash
        precommits.append(result.vote)
    _distribute_votes(
        runner,
        votes=precommits,
        node_ids=node_ids,
        states=states,
        vote_set_name="precommits",
        logical_time=runner.network.logical_time + 1,
        trace=trace,
    )

    finalize_time = runner.network.logical_time
    for node_id in node_ids:
        finalized = try_finalize(
            states[node_id],
            ledger=ledgers[node_id],
            chain_id=chain_id,
            exec_config=execution_config,
            validator_count=validator_count,
        )
        assert finalized.success, finalized.reason
        runner.event_log.write_event(
            event_no=runner._next_event_no(),
            logical_time=finalize_time,
            node_id=node_id,
            event_type=EventType.FINALIZE,
            height=1,
            round=0,
            details={
                "block_hash": block_hash.hex(),
                "state_hash": finalized.entry.state.state_hash().hex(),
            },
        )
        runner.register_ledger(node_id, ledgers[node_id])

    runner.check_assertions()
    assert runner.safety_result.ok
    assert runner.liveness_result.ok
    runner.shutdown()

    log_path = Path(runner.event_log.log_path)
    return T8Run(
        log_bytes=log_path.read_bytes(),
        log_sha256=runner.event_log.get_sha256(),
        state_hashes={
            node_id: ledgers[node_id].get_state(1).state_hash()
            for node_id in node_ids
        },
        finalized_heads={
            node_id: (ledgers[node_id].finalized_height, ledgers[node_id].finalized_hash)
            for node_id in node_ids
        },
        fault_trace=trace,
    )


def test_scenario_t8_config_structure():
    config = _load_config("scenario_t8.json")
    assert config["scenario_id"] == "t8_determinism"
    assert config["num_validators"] == 8
    assert config["f"] == 2
    assert isinstance(config["seed"], int)
    assert config["faults"]["drop_probability"] == 0
    assert config["faults"]["delay_probability"] > 0
    assert config["faults"]["duplicate_probability"] > 0
    assert config["faults"]["reorder_probability"] > 0


def test_t8_same_seed_has_byte_identical_log_and_state_hash():
    first = _run_t8_once()
    second = _run_t8_once()

    assert first.log_bytes == second.log_bytes
    assert first.log_sha256 == second.log_sha256
    assert first.state_hashes == second.state_hashes
    assert first.finalized_heads == second.finalized_heads

    # The deterministic run genuinely exercised every configured non-drop
    # fault instead of comparing two trivial no-op logs.
    assert first.fault_trace.delayed > 0
    assert first.fault_trace.duplicated > 0
    assert first.fault_trace.reordered > 0
    assert first.fault_trace == second.fault_trace

    assert len(set(first.state_hashes.values())) == 1
    assert len(set(first.finalized_heads.values())) == 1
    assert next(iter(first.finalized_heads.values()))[0] == 1
