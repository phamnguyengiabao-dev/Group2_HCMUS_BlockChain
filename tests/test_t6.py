"""T5-06: a silent/crashed proposer triggers a round change and recovery."""

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
    handle_proposal_timeout,
    make_precommit,
    make_prevote,
    propose,
    schedule_proposal_timeout,
    select_proposer,
    try_finalize,
)
from src.event_log import EventType
from src.executor import ExecutionConfig
from src.identity import load_validator_keys
from src.ledger import Ledger
from src.scenario import ScenarioRunner, simulate_crash

CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"


def _load_config(name: str) -> dict:
    with (CONFIG_DIR / name).open("r", encoding="utf-8") as file:
        return json.load(file)


@pytest.fixture(autouse=True)
def clean_logs():
    yield
    shutil.rmtree("logs", ignore_errors=True)


@dataclass
class T6Result:
    runner: ScenarioRunner
    crashed_node: str
    honest_node_ids: list[str]
    ledgers: dict[str, Ledger]
    timeout_votes: int
    recovered_proposer: str


def _run_t6() -> T6Result:
    scenario = {**_load_config("scenario_t6.json"), "run_id": "t6_run"}
    defaults = _load_config("default.json")
    chain_id = defaults["chain_id"]
    validators = load_validator_keys()
    node_ids = [f"validator_{validator.index}" for validator in validators]
    validator_by_node = dict(zip(node_ids, validators))
    validator_count = len(validators)

    runner = ScenarioRunner(scenario, defaults)
    runner.load()
    network = runner.network

    states = {node_id: ConsensusState(height=1) for node_id in node_ids}
    ledgers = {node_id: Ledger(chain_id=chain_id) for node_id in node_ids}
    execution_config = ExecutionConfig(
        chain_id=chain_id,
        max_key_size=defaults["network"]["max_key_size_bytes"],
        max_value_size=defaults["network"]["max_value_size_bytes"],
    )

    expected_round0_proposer = select_proposer(1, 0)
    crashed_node = scenario["crash"]["node_id"]
    assert crashed_node == node_ids[expected_round0_proposer.index]
    honest_node_ids = [node_id for node_id in node_ids if node_id != crashed_node]

    volatile_cache = {crashed_node: {"pending_proposal": object()}}
    crash_state = simulate_crash(
        node_id=crashed_node,
        logical_time=scenario["crash"]["logical_time"],
        event_log=runner.event_log,
        event_no=runner._next_event_no(),
        in_memory_caches=volatile_cache,
        snapshot_path=None,
    )
    assert crash_state.node_id == crashed_node
    assert volatile_cache[crashed_node] == {}

    # The round-0 proposer emits nothing.  Every correct validator schedules a
    # deterministic self-timeout and prevotes NIL when it fires.
    proposal_timeout = scenario["timeout_schedule"]["proposal_timeout"]
    for node_id in honest_node_ids:
        schedule_proposal_timeout(
            states[node_id],
            network=network,
            self_identity=validator_by_node[node_id],
            validator_node_ids=node_ids,
            current_logical_time=0,
            proposal_timeout=proposal_timeout,
        )
    delivered_timeouts = network.run()
    assert delivered_timeouts == [b"TIMEOUT:PROPOSAL"] * len(honest_node_ids)

    timeout_votes = []
    for node_id in honest_node_ids:
        runner.event_log.write_event(
            event_no=runner._next_event_no(),
            logical_time=proposal_timeout,
            node_id=node_id,
            event_type=EventType.TIMEOUT,
            height=1,
            round=0,
            details={"phase": "PROPOSAL"},
        )
        vote = handle_proposal_timeout(
            states[node_id],
            network=network,
            self_identity=validator_by_node[node_id],
            validator_node_ids=node_ids,
            peers=[peer for peer in honest_node_ids if peer != node_id],
            chain_id=chain_id,
            logical_time=proposal_timeout,
            has_valid_proposal=False,
        )
        assert vote is not None
        assert vote.block_hash_or_nil is None
        timeout_votes.append(vote)
    network.run()

    for node_id in honest_node_ids:
        for vote in timeout_votes:
            states[node_id].prevotes.add(vote)
        assert ledgers[node_id].finalized_height == 0

    round_change_time = network.logical_time + 1
    for node_id in honest_node_ids:
        transition = do_round_change(
            states[node_id],
            network=network,
            self_identity=validator_by_node[node_id],
            validator_node_ids=node_ids,
            peers=[peer for peer in honest_node_ids if peer != node_id],
            chain_id=chain_id,
            logical_time=round_change_time,
            precommit_timeout=scenario["timeout_schedule"]["precommit_timeout"],
        )
        assert transition.new_round == 1
        runner.event_log.write_event(
            event_no=runner._next_event_no(),
            logical_time=round_change_time,
            node_id=node_id,
            event_type=EventType.ROUND_CHANGE,
            height=1,
            round=1,
            details={"from_round": 0, "to_round": 1},
        )

    # Round 1 selects validator_2, which is correct and can make progress with
    # the seven remaining validators (quorum for n=8 is five).
    proposer1 = select_proposer(1, 1)
    proposer1_id = node_ids[proposer1.index]
    assert proposer1_id in honest_node_ids
    proposal = propose(
        states[proposer1_id],
        network=network,
        ledger=ledgers[proposer1_id],
        self_identity=proposer1,
        validator_node_ids=node_ids,
        peers=[node_id for node_id in honest_node_ids if node_id != proposer1_id],
        pending_transactions=[],
        chain_id=chain_id,
        exec_config=execution_config,
        logical_time=round_change_time,
    )
    assert proposal.success, proposal.reason
    header = proposal.header
    block_hash = header.block_hash()
    network.run()

    for node_id in honest_node_ids:
        assert states[node_id].block_store.store_header(header).success
        assert states[node_id].block_store.store_body(block_hash, []).success

    prevotes = [
        make_prevote(
            states[node_id],
            chain_id=chain_id,
            self_identity=validator_by_node[node_id],
            proposed_block_hash=block_hash,
            validator_count=validator_count,
        )
        for node_id in honest_node_ids
    ]
    for node_id in honest_node_ids:
        for vote in prevotes:
            states[node_id].prevotes.add(vote)
        assert apply_lock(states[node_id], round=1, validator_count=validator_count) == block_hash

    precommit_time = network.logical_time + 1
    precommits = []
    for node_id in honest_node_ids:
        result = make_precommit(
            states[node_id],
            chain_id=chain_id,
            self_identity=validator_by_node[node_id],
            validator_count=validator_count,
            network=network,
            validator_node_ids=node_ids,
            peers=[peer for peer in honest_node_ids if peer != node_id],
            logical_time=precommit_time,
        )
        assert result.block_hash_or_nil == block_hash
        precommits.append(result.vote)
    network.run()

    for node_id in honest_node_ids:
        for vote in precommits:
            states[node_id].precommits.add(vote)
        finalized = try_finalize(
            states[node_id],
            ledger=ledgers[node_id],
            chain_id=chain_id,
            exec_config=execution_config,
            validator_count=validator_count,
        )
        assert finalized.success, finalized.reason
        assert finalized.entry.block_hash == block_hash
        runner.register_ledger(node_id, ledgers[node_id])

    runner.check_assertions()
    runner.shutdown()
    return T6Result(
        runner=runner,
        crashed_node=crashed_node,
        honest_node_ids=honest_node_ids,
        ledgers=ledgers,
        timeout_votes=len(timeout_votes),
        recovered_proposer=proposer1_id,
    )


def test_scenario_t6_config_structure():
    config = _load_config("scenario_t6.json")
    assert config["scenario_id"] == "t6_proposer_crash"
    assert config["num_validators"] == 8
    assert config["f"] == 2
    assert config["crash"] == {
        "height": 1,
        "round": 0,
        "node_id": "validator_1",
        "logical_time": 0,
        "restart": False,
    }
    assert config["timeout_schedule"]["proposal_timeout"] > 0


def test_t6_silent_proposer_times_out_round_changes_and_next_proposer_finalizes():
    result = _run_t6()
    assert result.timeout_votes == 7
    assert result.recovered_proposer != result.crashed_node
    assert result.ledgers[result.crashed_node].finalized_height == 0

    honest_heads = {
        (result.ledgers[node_id].finalized_height, result.ledgers[node_id].finalized_hash)
        for node_id in result.honest_node_ids
    }
    assert len(honest_heads) == 1
    assert next(iter(honest_heads))[0] == 1
    assert result.runner.safety_result.ok
    assert result.runner.liveness_result.ok

    events = [
        json.loads(line)
        for line in Path(result.runner.event_log.log_path)
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    event_types = [event["event_type"] for event in events]
    assert event_types.count("CRASH") == 1
    assert event_types.count("TIMEOUT") == 7
    assert event_types.count("ROUND_CHANGE") == 7
