"""T5-07: two Byzantine validators equivocate without breaking safety."""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path

import pytest

from src.block import BlockHeader, compute_tx_root, validate_block_body
from src.consensus import ConsensusState, apply_lock, propose, select_proposer, try_finalize
from src.crypto import hash_bytes, sign
from src.event_log import EventType
from src.executor import ExecutionConfig, execute_block
from src.identity import load_validator_keys
from src.ledger import Ledger
from src.scenario import ScenarioRunner
from src.state import State
from src.transaction import Transaction
from src.vote import PHASE_PRECOMMIT, PHASE_PREVOTE, Vote
from src.vote_set import VoteOutcome

CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"


def _load_config(name: str) -> dict:
    with (CONFIG_DIR / name).open("r", encoding="utf-8") as file:
        return json.load(file)


@pytest.fixture(autouse=True)
def clean_logs():
    yield
    shutil.rmtree("logs", ignore_errors=True)


@dataclass
class T7Result:
    runner: ScenarioRunner
    honest_node_ids: list[str]
    ledgers: dict[str, Ledger]
    finalized_hash: bytes
    conflicting_hash: bytes
    equivocations: int


def _signed_transaction(sender, *, chain_id: str) -> Transaction:
    key = f"{hash_bytes(sender.public_key).hex()}/t7-conflict"
    unsigned = Transaction(
        chain_id=chain_id,
        nonce=0,
        sender_pubkey=sender.public_key,
        key=key,
        value_bytes=b"conflicting-valid-candidate",
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


def _vote(validator, *, chain_id: str, phase: str, block_hash: bytes) -> Vote:
    return Vote.create_signed(
        chain_id=chain_id,
        height=1,
        round=0,
        phase=phase,
        block_hash_or_nil=block_hash,
        validator_pubkey=validator.public_key,
        validator_privkey=validator.private_key,
    )


def _log_equivocation(
    runner: ScenarioRunner,
    *,
    node_id: str,
    phase: str,
    validator_node_id: str,
    first_hash: bytes,
    conflicting_hash: bytes,
    logical_time: int,
) -> None:
    runner.event_log.write_event(
        event_no=runner._next_event_no(),
        logical_time=logical_time,
        node_id=node_id,
        event_type=EventType.EQUIVOCATION,
        height=1,
        round=0,
        details={
            "conflicting_block_hash": conflicting_hash.hex(),
            "first_block_hash": first_hash.hex(),
            "phase": phase,
            "validator": validator_node_id,
        },
    )


def _run_t7() -> T7Result:
    scenario = {**_load_config("scenario_t7.json"), "run_id": "t7_run"}
    defaults = _load_config("default.json")
    chain_id = defaults["chain_id"]
    validators = load_validator_keys()
    node_ids = [f"validator_{validator.index}" for validator in validators]
    validator_count = len(validators)
    byzantine_node_ids = scenario["byzantine_nodes"]
    byzantine_indexes = [node_ids.index(node_id) for node_id in byzantine_node_ids]
    honest_node_ids = [node_id for node_id in node_ids if node_id not in byzantine_node_ids]

    runner = ScenarioRunner(scenario, defaults)
    runner.load()
    network = runner.network
    execution_config = ExecutionConfig(
        chain_id=chain_id,
        max_key_size=defaults["network"]["max_key_size_bytes"],
        max_value_size=defaults["network"]["max_value_size_bytes"],
    )
    states = {node_id: ConsensusState(height=1) for node_id in node_ids}
    ledgers = {node_id: Ledger(chain_id=chain_id) for node_id in node_ids}

    # Candidate A is empty.  Candidate B contains one valid transaction.  Both
    # are correctly signed by the round-0 proposer (validator_1), so the test
    # is about conflicting votes rather than malformed data.
    proposer = select_proposer(1, 0)
    proposer_node_id = node_ids[proposer.index]
    assert proposer_node_id in byzantine_node_ids
    proposal_a = propose(
        states[proposer_node_id],
        network=network,
        ledger=ledgers[proposer_node_id],
        self_identity=proposer,
        validator_node_ids=node_ids,
        peers=honest_node_ids,
        pending_transactions=[],
        chain_id=chain_id,
        exec_config=execution_config,
        logical_time=0,
    )
    assert proposal_a.success, proposal_a.reason
    header_a = proposal_a.header
    hash_a = header_a.block_hash()
    network.run()

    transaction_b = _signed_transaction(validators[2], chain_id=chain_id)
    execution_b = execute_block([transaction_b], State(), {}, execution_config)
    assert execution_b.success
    header_b = BlockHeader.create_signed(
        chain_id=chain_id,
        height=1,
        round=0,
        parent_hash=b"\x00" * 32,
        tx_root=compute_tx_root([transaction_b.tx_id()]),
        state_hash=execution_b.post_state.state_hash(),
        proposer_pubkey=proposer.public_key,
        proposer_privkey=proposer.private_key,
    )
    hash_b = header_b.block_hash()
    assert hash_a != hash_b
    assert validate_block_body(
        header_b, [transaction_b], State(), {}, execution_config
    ).success

    for node_id in honest_node_ids:
        for header, block_hash, transactions in (
            (header_a, hash_a, []),
            (header_b, hash_b, [transaction_b]),
        ):
            assert states[node_id].block_store.store_header(header).success
            assert states[node_id].block_store.store_body(block_hash, transactions).success

    equivocations = 0
    for phase, logical_time, vote_set_name in (
        (PHASE_PREVOTE, 1, "prevotes"),
        (PHASE_PRECOMMIT, 2, "precommits"),
    ):
        votes_a = [
            _vote(validator, chain_id=chain_id, phase=phase, block_hash=hash_a)
            for validator in validators
        ]
        conflicting_votes = {
            index: _vote(
                validators[index],
                chain_id=chain_id,
                phase=phase,
                block_hash=hash_b,
            )
            for index in byzantine_indexes
        }

        # Put both statements on the simulated wire.  A is received first;
        # the contradictory B statement is therefore evidence, never a second
        # counted vote for the same validator/slot.
        for index in byzantine_indexes:
            sender = node_ids[index]
            for receiver in honest_node_ids:
                network.send(
                    sender=sender,
                    receiver=receiver,
                    payload=votes_a[index].signed_bytes(),
                    logical_time=logical_time,
                    height=1,
                    round=0,
                )
                network.send(
                    sender=sender,
                    receiver=receiver,
                    payload=conflicting_votes[index].signed_bytes(),
                    logical_time=logical_time,
                    height=1,
                    round=0,
                )
        network.run()

        for node_id in honest_node_ids:
            vote_set = getattr(states[node_id], vote_set_name)
            for vote in votes_a:
                assert vote_set.add(vote).outcome in {
                    VoteOutcome.ACCEPTED,
                    VoteOutcome.DUPLICATE_IGNORED,
                }
            for index in byzantine_indexes:
                result = vote_set.add(conflicting_votes[index])
                assert result.outcome is VoteOutcome.EQUIVOCATION_DETECTED
                assert result.stored_vote.block_hash_or_nil == hash_a
                equivocations += 1
                _log_equivocation(
                    runner,
                    node_id=node_id,
                    phase=phase,
                    validator_node_id=node_ids[index],
                    first_hash=hash_a,
                    conflicting_hash=hash_b,
                    logical_time=logical_time,
                )

            assert vote_set.has_quorum(
                1, 0, phase, validator_count, block_hash=hash_a
            )
            assert not vote_set.has_quorum(
                1, 0, phase, validator_count, block_hash=hash_b
            )

        if phase == PHASE_PREVOTE:
            for node_id in honest_node_ids:
                assert apply_lock(
                    states[node_id], round=0, validator_count=validator_count
                ) == hash_a

    for node_id in honest_node_ids:
        finalized = try_finalize(
            states[node_id],
            ledger=ledgers[node_id],
            chain_id=chain_id,
            exec_config=execution_config,
            validator_count=validator_count,
        )
        assert finalized.success, finalized.reason
        assert finalized.entry.block_hash == hash_a
        assert finalized.entry.block_hash != hash_b
        runner.register_ledger(node_id, ledgers[node_id])

    runner.check_assertions()
    runner.shutdown()
    return T7Result(
        runner=runner,
        honest_node_ids=honest_node_ids,
        ledgers=ledgers,
        finalized_hash=hash_a,
        conflicting_hash=hash_b,
        equivocations=equivocations,
    )


def test_scenario_t7_config_structure():
    config = _load_config("scenario_t7.json")
    assert config["scenario_id"] == "t7_equivocation"
    assert config["num_validators"] == 8
    assert config["f"] == 2
    assert len(config["byzantine_nodes"]) == config["f"]
    assert len(set(config["byzantine_nodes"])) == config["f"]
    assert config["equivocation"]["phases"] == ["PREVOTE", "PRECOMMIT"]


def test_t7_f_equivocators_are_logged_and_cannot_finalize_a_conflict():
    result = _run_t7()
    expected_evidence = 2 * len(result.honest_node_ids) * 2
    assert result.equivocations == expected_evidence
    assert result.finalized_hash != result.conflicting_hash
    assert result.runner.safety_result.ok
    assert result.runner.safety_result.violations == []
    assert result.runner.liveness_result.ok

    honest_heads = {
        result.ledgers[node_id].finalized_hash for node_id in result.honest_node_ids
    }
    assert honest_heads == {result.finalized_hash}

    events = [
        json.loads(line)
        for line in Path(result.runner.event_log.log_path)
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    equivocation_events = [
        event for event in events if event["event_type"] == "EQUIVOCATION"
    ]
    assert len(equivocation_events) == expected_evidence
    assert {
        event["details"]["validator"] for event in equivocation_events
    } == {"validator_0", "validator_1"}
