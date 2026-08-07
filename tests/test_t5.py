"""T5-05: drop/delay before synchrony preserves safety.

The repository does not yet have a node dispatcher that drives consensus from
delivered envelopes, so this scenario uses the same explicit eight-node driver
as T1/T2.  Round 0 is scheduled adversarially before the configured
stabilization time: messages are dropped or held long enough that no node can
collect the five-vote quorum.  After stabilization, round 1 is fault-free and
all correct nodes finalize the same block.
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
    do_round_change,
    make_precommit,
    make_prevote,
    propose,
    select_proposer,
    try_finalize,
)
from src.event_log import EventType
from src.executor import ExecutionConfig
from src.identity import load_validator_keys
from src.ledger import Ledger
from src.scenario import ScenarioRunner
from src.vote import PHASE_PREVOTE, Vote

CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"


def _load_config(name: str) -> dict:
    with (CONFIG_DIR / name).open("r", encoding="utf-8") as file:
        return json.load(file)


@pytest.fixture(autouse=True)
def clean_logs():
    yield
    shutil.rmtree("logs", ignore_errors=True)


@dataclass
class T5Result:
    runner: ScenarioRunner
    node_ids: list[str]
    ledgers: dict[str, Ledger]
    dropped: int
    delayed: int
    pre_synchrony_vote_counts: dict[str, int]


def _write_fault_event(
    runner: ScenarioRunner,
    *,
    event_type: EventType,
    sender: str,
    receiver: str,
    delay: int = 0,
) -> None:
    details = {"receiver": receiver, "sender": sender}
    if event_type is EventType.DELAY:
        details["delay"] = delay
    runner.event_log.write_event(
        event_no=runner._next_event_no(),
        logical_time=0,
        node_id=receiver,
        event_type=event_type,
        height=1,
        round=0,
        details=details,
    )


def _run_t5() -> T5Result:
    scenario = {**_load_config("scenario_t5.json"), "run_id": "t5_run"}
    defaults = _load_config("default.json")
    chain_id = defaults["chain_id"]
    validators = load_validator_keys()
    node_ids = [f"validator_{validator.index}" for validator in validators]
    validator_count = len(validators)
    quorum = 2 * ((validator_count - 1) // 3) + 1

    runner = ScenarioRunner(scenario, defaults)
    runner.load()
    network = runner.network
    fault_injector = runner.fault_injector

    execution_config = ExecutionConfig(
        chain_id=chain_id,
        max_key_size=defaults["network"]["max_key_size_bytes"],
        max_value_size=defaults["network"]["max_value_size_bytes"],
    )
    states = {node_id: ConsensusState(height=1) for node_id in node_ids}
    ledgers = {node_id: Ledger(chain_id=chain_id) for node_id in node_ids}

    # Build a valid round-0 candidate.  The adverse pre-synchrony schedule is
    # applied to its votes; every correct node knows the candidate, but no one
    # can gather a quorum before its round timeout.
    proposer0 = select_proposer(1, 0)
    proposer0_id = node_ids[proposer0.index]
    proposal0 = propose(
        states[proposer0_id],
        network=network,
        ledger=ledgers[proposer0_id],
        self_identity=proposer0,
        validator_node_ids=node_ids,
        peers=[],
        pending_transactions=[],
        chain_id=chain_id,
        exec_config=execution_config,
        logical_time=0,
    )
    assert proposal0.success, proposal0.reason
    header0 = proposal0.header
    hash0 = header0.block_hash()
    for state in states.values():
        assert state.block_store.store_header(header0).success
        assert state.block_store.store_body(hash0, []).success

    round0_votes = [
        Vote.create_signed(
            chain_id=chain_id,
            height=1,
            round=0,
            phase=PHASE_PREVOTE,
            block_hash_or_nil=hash0,
            validator_pubkey=validator.public_key,
            validator_privkey=validator.private_key,
        )
        for validator in validators
    ]

    stabilization_time = scenario["stabilization_time"]
    delivery_cap = scenario["pre_synchrony_delivery_cap_per_receiver"]
    dropped = 0
    delayed = 0

    for receiver_index, receiver in enumerate(node_ids):
        # A node always sees its own vote immediately.
        states[receiver].prevotes.add(round0_votes[receiver_index])
        accepted_before_synchrony = 1

        for sender_index, sender in enumerate(node_ids):
            if sender == receiver:
                continue
            vote = round0_votes[sender_index]
            fault = fault_injector.apply()

            if fault.dropped:
                dropped += 1
                _write_fault_event(
                    runner,
                    event_type=EventType.DROP,
                    sender=sender,
                    receiver=receiver,
                )
                continue

            # Before GST, the adversarial scheduler may hold any message.  The
            # cap guarantees fewer than 2f+1 votes at every receiver; the
            # seeded FaultInjector determines which legs are additionally
            # delayed or dropped.
            held = fault.delay > 0 or accepted_before_synchrony >= delivery_cap
            delivery_time = fault.delay
            if held:
                delivery_time = stabilization_time + max(1, fault.delay)
                delayed += 1
                _write_fault_event(
                    runner,
                    event_type=EventType.DELAY,
                    sender=sender,
                    receiver=receiver,
                    delay=delivery_time,
                )
            else:
                states[receiver].prevotes.add(vote)
                accepted_before_synchrony += 1

            network.send(
                sender=sender,
                receiver=receiver,
                payload=vote.signed_bytes(),
                logical_time=delivery_time,
                height=1,
                round=0,
            )

    network.run()

    pre_synchrony_vote_counts: dict[str, int] = {}
    for node_id in node_ids:
        votes = states[node_id].prevotes.votes(1, 0, PHASE_PREVOTE)
        pre_synchrony_vote_counts[node_id] = len(votes)
        assert len(votes) < quorum
        assert apply_lock(states[node_id], round=0, validator_count=validator_count) is None
        assert not try_finalize(
            states[node_id],
            ledger=ledgers[node_id],
            chain_id=chain_id,
            exec_config=execution_config,
            validator_count=validator_count,
        ).success

    # GST: advance every correct node to round 1, discard stale round-0 vote
    # sets, then run a fault-free round with the next proposer.
    stable_time = max(stabilization_time, network.logical_time) + 1
    for validator, node_id in zip(validators, node_ids):
        transition = do_round_change(
            states[node_id],
            network=network,
            self_identity=validator,
            validator_node_ids=node_ids,
            peers=[],
            chain_id=chain_id,
            logical_time=stable_time,
            precommit_timeout=defaults["timeout_schedule"]["precommit_timeout"],
        )
        assert transition.new_round == 1
        runner.event_log.write_event(
            event_no=runner._next_event_no(),
            logical_time=stable_time,
            node_id=node_id,
            event_type=EventType.ROUND_CHANGE,
            height=1,
            round=1,
            details={"from_round": 0, "to_round": 1},
        )

    proposer1 = select_proposer(1, 1)
    proposer1_id = node_ids[proposer1.index]
    proposal1 = propose(
        states[proposer1_id],
        network=network,
        ledger=ledgers[proposer1_id],
        self_identity=proposer1,
        validator_node_ids=node_ids,
        peers=[node_id for node_id in node_ids if node_id != proposer1_id],
        pending_transactions=[],
        chain_id=chain_id,
        exec_config=execution_config,
        logical_time=stable_time,
    )
    assert proposal1.success, proposal1.reason
    header1 = proposal1.header
    hash1 = header1.block_hash()
    network.run()

    for state in states.values():
        assert state.block_store.store_header(header1).success
        assert state.block_store.store_body(hash1, []).success

    stable_prevotes = [
        make_prevote(
            states[node_ids[validator.index]],
            chain_id=chain_id,
            self_identity=validator,
            proposed_block_hash=hash1,
            validator_count=validator_count,
        )
        for validator in validators
    ]
    for state in states.values():
        for vote in stable_prevotes:
            state.prevotes.add(vote)
        assert apply_lock(state, round=1, validator_count=validator_count) == hash1

    stable_precommits = []
    precommit_time = network.logical_time + 1
    for validator, node_id in zip(validators, node_ids):
        result = make_precommit(
            states[node_id],
            chain_id=chain_id,
            self_identity=validator,
            validator_count=validator_count,
            network=network,
            validator_node_ids=node_ids,
            peers=[peer for peer in node_ids if peer != node_id],
            logical_time=precommit_time,
        )
        assert result.block_hash_or_nil == hash1
        stable_precommits.append(result.vote)
    network.run()

    for state in states.values():
        for vote in stable_precommits:
            state.precommits.add(vote)

    finalize_time = network.logical_time
    for node_id in node_ids:
        finalized = try_finalize(
            states[node_id],
            ledger=ledgers[node_id],
            chain_id=chain_id,
            exec_config=execution_config,
            validator_count=validator_count,
        )
        assert finalized.success, finalized.reason
        assert finalized.entry.block_hash == hash1
        runner.event_log.write_event(
            event_no=runner._next_event_no(),
            logical_time=finalize_time,
            node_id=node_id,
            event_type=EventType.FINALIZE,
            height=1,
            round=1,
            details={"block_hash": hash1.hex()},
        )

    # Liveness continues at the next height once the network is synchronous.
    # Height 2 uses its normal round-0 proposer and the same fault-free path.
    height2_time = finalize_time + 1
    proposer2 = select_proposer(2, 0)
    proposer2_id = node_ids[proposer2.index]
    proposal2 = propose(
        states[proposer2_id],
        network=network,
        ledger=ledgers[proposer2_id],
        self_identity=proposer2,
        validator_node_ids=node_ids,
        peers=[node_id for node_id in node_ids if node_id != proposer2_id],
        pending_transactions=[],
        chain_id=chain_id,
        exec_config=execution_config,
        logical_time=height2_time,
    )
    assert proposal2.success, proposal2.reason
    header2 = proposal2.header
    hash2 = header2.block_hash()
    network.run()

    for state in states.values():
        assert state.block_store.store_header(header2).success
        assert state.block_store.store_body(hash2, []).success

    height2_prevotes = [
        make_prevote(
            states[node_ids[validator.index]],
            chain_id=chain_id,
            self_identity=validator,
            proposed_block_hash=hash2,
            validator_count=validator_count,
        )
        for validator in validators
    ]
    for state in states.values():
        for vote in height2_prevotes:
            state.prevotes.add(vote)
        assert apply_lock(state, round=0, validator_count=validator_count) == hash2

    height2_precommits = []
    for validator, node_id in zip(validators, node_ids):
        result = make_precommit(
            states[node_id],
            chain_id=chain_id,
            self_identity=validator,
            validator_count=validator_count,
            network=network,
            validator_node_ids=node_ids,
            peers=[peer for peer in node_ids if peer != node_id],
            logical_time=network.logical_time + 1,
        )
        assert result.block_hash_or_nil == hash2
        height2_precommits.append(result.vote)
    network.run()

    for state in states.values():
        for vote in height2_precommits:
            state.precommits.add(vote)

    for node_id in node_ids:
        finalized = try_finalize(
            states[node_id],
            ledger=ledgers[node_id],
            chain_id=chain_id,
            exec_config=execution_config,
            validator_count=validator_count,
        )
        assert finalized.success, finalized.reason
        assert finalized.entry.block_hash == hash2
        runner.event_log.write_event(
            event_no=runner._next_event_no(),
            logical_time=network.logical_time,
            node_id=node_id,
            event_type=EventType.FINALIZE,
            height=2,
            round=0,
            details={"block_hash": hash2.hex()},
        )
        runner.register_ledger(node_id, ledgers[node_id])

    runner.check_assertions()
    runner.shutdown()
    return T5Result(
        runner=runner,
        node_ids=node_ids,
        ledgers=ledgers,
        dropped=dropped,
        delayed=delayed,
        pre_synchrony_vote_counts=pre_synchrony_vote_counts,
    )


def test_scenario_t5_config_structure():
    config = _load_config("scenario_t5.json")
    assert config["scenario_id"] == "t5_drop_delay"
    assert config["num_validators"] == 8
    assert config["f"] == 2
    assert config["stabilization_time"] > 0
    assert config["pre_synchrony_delivery_cap_per_receiver"] < 2 * config["f"] + 1
    assert config["faults"]["drop_probability"] > 0
    assert config["faults"]["delay_probability"] > 0
    assert config["post_synchrony_faults"]["drop_probability"] == 0
    assert config["post_synchrony_faults"]["delay_probability"] == 0


def test_t5_drop_delay_preserves_safety_then_progresses_after_synchrony():
    result = _run_t5()
    assert result.dropped > 0
    assert result.delayed > 0
    assert max(result.pre_synchrony_vote_counts.values()) < 5

    assert result.runner.safety_result.ok
    assert result.runner.safety_result.violations == []
    assert result.runner.liveness_result.ok

    finalized = {
        (ledger.finalized_height, ledger.finalized_hash)
        for ledger in result.ledgers.values()
    }
    assert len(finalized) == 1
    assert next(iter(finalized))[0] == 2

    events = [
        json.loads(line)
        for line in Path(result.runner.event_log.log_path)
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    event_types = {event["event_type"] for event in events}
    assert {"DROP", "DELAY", "ROUND_CHANGE", "FINALIZE"} <= event_types
