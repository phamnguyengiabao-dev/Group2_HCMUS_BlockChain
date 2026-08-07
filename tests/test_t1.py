"""
T5-01

Scenario T1 — Normal run.

8 validator nodes, no faults, max_height=3: every correct node must
finalize the same height, the same block_hash, and the same state_hash
at every height.

There is no "Node" object yet that turns delivered envelopes into
consensus actions on its own, so this test plays that role directly:
for every height it drives propose() -> prevote -> lock -> precommit ->
try_finalize() once per validator, using ScenarioRunner's shared Network
so SEND/DELIVER events land in the canonical log, then hands every
node's Ledger to ScenarioRunner's safety/liveness assertion engine
(T3-16).
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
from src.executor import ExecutionConfig
from src.identity import load_validator_keys
from src.ledger import Ledger
from src.scenario import ScenarioRunner

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

def test_scenario_t1_config_structure():
    """scenario_t1.json declares a normal, fault-free 8-node run."""
    config = load_config("scenario_t1.json")

    assert config["scenario_id"] == "t1_normal"
    assert isinstance(config["seed"], int)

    assert config["num_validators"] == 8
    assert config["f"] == 2
    assert config["max_height"] == 3
    assert config["byzantine_nodes"] == []

    assert config["topology"] == "full_mesh"
    assert config["message_drop_rate"] == 0
    assert config["message_delay_rate"] == 0
    assert config["node_crash_rate"] == 0


# ---------------------------------------------------------------------
# Full 8-node run
# ---------------------------------------------------------------------

@dataclass
class T1Run:
    runner: ScenarioRunner
    node_ids: list[str]
    ledgers: dict[str, Ledger]
    max_height: int


def _run_t1() -> T1Run:
    scenario_config = {**load_config("scenario_t1.json"), "run_id": "t1_run1"}
    default_config = load_config("default.json")

    chain_id = default_config["chain_id"]
    max_height = scenario_config["max_height"]
    validator_count = scenario_config["num_validators"]

    validators = load_validator_keys()
    assert len(validators) == validator_count

    node_ids = [f"validator_{v.index}" for v in validators]

    runner = ScenarioRunner(scenario_config, default_config)
    runner.load()
    network = runner.network

    exec_config = ExecutionConfig(
        chain_id=chain_id,
        max_key_size=default_config["network"]["max_key_size_bytes"],
        max_value_size=default_config["network"]["max_value_size_bytes"],
    )

    states = {nid: ConsensusState(height=1) for nid in node_ids}
    ledgers = {nid: Ledger(chain_id=chain_id) for nid in node_ids}

    logical_time = 0

    for height in range(1, max_height + 1):
        round_ = 0
        proposer = select_proposer(height, round_)
        proposer_node_id = node_ids[proposer.index]
        broadcast_peers = [nid for nid in node_ids if nid != proposer_node_id]

        # -- Propose: proposer builds + signs the block, broadcasts HEADER
        # then BODY to every peer over the shared Network. --
        result = propose(
            states[proposer_node_id],
            network=network,
            ledger=ledgers[proposer_node_id],
            self_identity=proposer,
            validator_node_ids=node_ids,
            peers=broadcast_peers,
            pending_transactions=[],
            chain_id=chain_id,
            exec_config=exec_config,
            logical_time=logical_time,
        )
        assert result.success, result.reason
        header = result.header
        block_hash = header.block_hash()

        network.run()  # drain HEADER/BODY sends -> DELIVER events in the log
        logical_time += 1

        # No-fault normal run: every node receives header + body.
        for nid in node_ids:
            states[nid].block_store.store_header(header)
            states[nid].block_store.store_body(block_hash, [])

        # -- Prevote: every validator casts its own prevote; full-mesh
        # gossip with no faults means every node observes every vote. --
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
        for nid in node_ids:
            for vote in prevotes:
                states[nid].prevotes.add(vote)

        for nid in node_ids:
            apply_lock(states[nid], round=round_, validator_count=validator_count)

        # -- Precommit: every node broadcasts its own precommit over the
        # network, then every node observes every precommit. --
        precommits = []
        for validator in validators:
            nid = node_ids[validator.index]
            peers_of_nid = [n for n in node_ids if n != nid]
            precommit_result = make_precommit(
                states[nid],
                chain_id=chain_id,
                self_identity=validator,
                validator_count=validator_count,
                network=network,
                validator_node_ids=node_ids,
                peers=peers_of_nid,
                logical_time=logical_time,
            )
            precommits.append(precommit_result.vote)

        network.run()
        logical_time += 1

        for nid in node_ids:
            for vote in precommits:
                states[nid].precommits.add(vote)

        # -- Finalize: every node independently reaches quorum and
        # appends the same block to its own ledger. --
        for nid in node_ids:
            fin = try_finalize(
                states[nid],
                ledger=ledgers[nid],
                chain_id=chain_id,
                exec_config=exec_config,
                validator_count=validator_count,
            )
            assert fin.success, fin.reason
            assert fin.entry.height == height
            assert fin.entry.block_hash == block_hash

    for nid in node_ids:
        runner.register_ledger(nid, ledgers[nid])

    runner.check_assertions()
    return T1Run(
        runner=runner,
        node_ids=node_ids,
        ledgers=ledgers,
        max_height=max_height,
    )


def test_t1_normal_run_safety_and_liveness():
    t1 = _run_t1()
    runner = t1.runner

    assert runner.safety_result.ok
    assert runner.safety_result.violations == []

    assert runner.liveness_result.ok
    assert runner.liveness_result.max_finalized_height == t1.max_height

    runner.shutdown()


def test_t1_normal_run_all_nodes_finalize_same_height_hash_and_state_hash():
    t1 = _run_t1()
    node_ids = t1.node_ids
    ledgers = t1.ledgers
    max_height = t1.max_height

    reference = ledgers[node_ids[0]]
    assert reference.finalized_height == max_height

    for nid in node_ids:
        ledger = ledgers[nid]
        # Same finalized height on every node.
        assert ledger.finalized_height == max_height
        # Same finalized block hash on every node.
        assert ledger.finalized_hash == reference.finalized_hash

        for height in range(1, max_height + 1):
            entry = ledger.get_entry(height)
            reference_entry = reference.get_entry(height)
            assert entry.block_hash == reference_entry.block_hash
            # Same state_hash (from the finalized header) on every node.
            assert entry.header.state_hash == reference_entry.header.state_hash
            assert entry.state.state_hash() == reference_entry.state.state_hash()

    t1.runner.shutdown()
