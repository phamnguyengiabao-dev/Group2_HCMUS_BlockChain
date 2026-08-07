"""
T5-02

Scenario T2 — Duplicate messages + reorder.

8 validator nodes, `faults` from scenario_t2.json (duplicate_probability
0.2, reorder_probability 0.2, delay_probability 0.3, drop_probability
0.0), max_height=2: network duplication and reordering must not corrupt
vote counting or cause conflicting finalization.

Builds on the same manual driver as test_t1.py (there is no wired-up
per-node message dispatcher yet), but every header/body/vote broadcast
is routed through FaultInjector (T3-07) instead of being delivered
straight to every peer:

    - each outgoing leg rolls one FaultInjector.apply() decision
    - a rolled `duplicate_count` sends (and applies) extra copies of the
      exact same message
    - a rolled `reorder` shuffles the order votes are applied to that
      receiver's VoteSet (using the scenario's seeded PRNG)

VoteSet (T2-08) is expected to dedupe by (height, round, phase,
validator_pubkey), so the extra copies must show up as
DUPLICATE_IGNORED, never inflate the quorum count, and never change
which block gets finalized.
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from src.consensus import (
    ConsensusState,
    apply_lock,
    propose,
    select_proposer,
    try_finalize,
)
from src.executor import ExecutionConfig
from src.identity import load_validator_keys
from src.ledger import Ledger
from src.scenario import ScenarioRunner
from src.transaction import encode_transaction_list
from src.vote import PHASE_PRECOMMIT, PHASE_PREVOTE, Vote
from src.vote_set import VoteOutcome
from tests.consensus_log_helper import log_finalizes, log_locks, log_precommits, log_prevotes, log_propose

CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"


def load_config(name: str) -> dict:
    with (CONFIG_DIR / name).open("r", encoding="utf-8") as fh:
        return json.load(fh)


@pytest.fixture(autouse=True)
def clean_logs():
    shutil.rmtree("logs/t2_duplicate_reorder", ignore_errors=True)
    yield


# ---------------------------------------------------------------------
# Config structure
# ---------------------------------------------------------------------

def test_scenario_t2_config_structure():
    """scenario_t2.json declares an 8-node run with duplicate + reorder faults."""
    config = load_config("scenario_t2.json")

    assert config["scenario_id"] == "t2_duplicate_reorder"
    assert isinstance(config["seed"], int)

    assert config["num_validators"] == 8
    assert config["f"] == 2
    assert config["max_height"] >= 1
    assert config["byzantine_nodes"] == []
    assert config["topology"] == "full_mesh"

    faults = config["faults"]
    assert faults["duplicate_probability"] > 0.0
    assert faults["max_duplicates"] >= 1
    assert faults["reorder_probability"] > 0.0
    # T2 only exercises duplicate/reorder; no drops.
    assert faults["drop_probability"] == 0.0


# ---------------------------------------------------------------------
# Fault-injected broadcast helpers
# ---------------------------------------------------------------------

@dataclass
class FaultStats:
    """Tally of what the fault injector actually did over the whole run."""

    dropped: int = 0
    duplicated_legs: int = 0       # legs where duplicate_count > 0
    reordered_receivers: int = 0   # receivers whose vote application order was shuffled
    extra_copies_sent: int = 0     # total duplicate copies actually sent/applied
    accepted: int = 0              # VoteSet.add() -> ACCEPTED
    duplicate_ignored: int = 0     # VoteSet.add() -> DUPLICATE_IGNORED
    equivocations: int = 0         # VoteSet.add() -> EQUIVOCATION_DETECTED (should never happen here)


def _broadcast_payload_with_faults(
    *,
    fault_injector,
    network,
    sender_node_id: str,
    payload: bytes,
    receiver_node_ids: list[str],
    logical_time: int,
    height: int,
    round_: int,
    on_deliver,
    stats: FaultStats,
) -> None:
    """Send `payload` to every receiver, subject to injected faults.

    Every copy that is actually sent (1 + duplicate_count, unless
    dropped) is also applied via `on_deliver(receiver)` once per copy,
    so a duplicated network message means `on_deliver` runs twice.
    """
    for receiver in receiver_node_ids:
        fault = fault_injector.apply()
        if fault.dropped:
            stats.dropped += 1
            continue

        copies = 1 + fault.duplicate_count
        if fault.duplicate_count > 0:
            stats.duplicated_legs += 1
            stats.extra_copies_sent += fault.duplicate_count
        deliver_time = logical_time + fault.delay

        for _ in range(copies):
            network.send(
                sender=sender_node_id,
                receiver=receiver,
                payload=payload,
                logical_time=deliver_time,
                height=height,
                round=round_,
            )
            on_deliver(receiver)


def _distribute_votes_with_faults(
    *,
    fault_injector,
    scheduler,
    network,
    votes: list[Vote],
    voter_node_ids: list[str],
    receiver_node_ids: list[str],
    states: dict[str, ConsensusState],
    vote_set_attr: str,
    logical_time: int,
    height: int,
    round_: int,
    stats: FaultStats,
) -> None:
    """Gossip every vote in `votes` to every receiver, subject to faults.

    Each voter already applied its own vote directly to its own VoteSet
    (see make_prevote/make_precommit), so a voter is skipped as its own
    receiver here. For each receiver, faults are rolled independently
    per incoming vote; if any of them rolled `reorder`, the order the
    votes are *applied* to that receiver's VoteSet (not the order they
    were sent) is shuffled with the scenario's seeded PRNG.
    """
    vote_by_voter = dict(zip(voter_node_ids, votes))

    for receiver in receiver_node_ids:
        plan: list[Vote] = []
        any_reorder = False

        for voter_node_id, vote in vote_by_voter.items():
            if voter_node_id == receiver:
                continue  # already applied locally, no network hop needed

            fault = fault_injector.apply()
            if fault.dropped:
                stats.dropped += 1
                continue

            copies = 1 + fault.duplicate_count
            if fault.duplicate_count > 0:
                stats.duplicated_legs += 1
                stats.extra_copies_sent += fault.duplicate_count
            if fault.reorder:
                any_reorder = True
                stats.reordered_receivers += 1
            deliver_time = logical_time + fault.delay

            for _ in range(copies):
                network.send(
                    sender=voter_node_id,
                    receiver=receiver,
                    payload=vote.signed_bytes(),
                    logical_time=deliver_time,
                    height=height,
                    round=round_,
                )

            plan.extend([vote] * copies)

        if any_reorder and len(plan) > 1:
            plan = scheduler.rng_shuffle_copy(plan)

        vote_set = getattr(states[receiver], vote_set_attr)
        for vote in plan:
            result = vote_set.add(vote)
            if result.outcome is VoteOutcome.ACCEPTED:
                stats.accepted += 1
            elif result.outcome is VoteOutcome.DUPLICATE_IGNORED:
                stats.duplicate_ignored += 1
            else:
                stats.equivocations += 1


# ---------------------------------------------------------------------
# Full 8-node run under duplicate + reorder faults
# ---------------------------------------------------------------------

@dataclass
class T2Run:
    runner: ScenarioRunner
    node_ids: list[str]
    ledgers: dict[str, Ledger]
    max_height: int
    stats: FaultStats
    vote_counts: dict = field(default_factory=dict)  # (height, phase) -> {node_id: distinct voter count}


def _run_t2() -> T2Run:
    scenario_config = {**load_config("scenario_t2.json"), "run_id": "t2_run1"}
    default_config = load_config("default.json")

    chain_id = default_config["chain_id"]
    max_height = scenario_config["max_height"]
    validator_count = scenario_config["num_validators"]
    max_delay = scenario_config["faults"]["max_delay"]

    validators = load_validator_keys()
    assert len(validators) == validator_count

    node_ids = [f"validator_{v.index}" for v in validators]

    runner = ScenarioRunner(scenario_config, default_config)
    runner.load()
    network = runner.network
    fault_injector = runner.fault_injector
    scheduler = runner.scheduler

    exec_config = ExecutionConfig(
        chain_id=chain_id,
        max_key_size=default_config["network"]["max_key_size_bytes"],
        max_value_size=default_config["network"]["max_value_size_bytes"],
    )

    states = {nid: ConsensusState(height=1) for nid in node_ids}
    ledgers = {nid: Ledger(chain_id=chain_id) for nid in node_ids}
    stats = FaultStats()
    vote_counts: dict = {}

    logical_time = 0
    time_step = max_delay + 1  # keep every phase's baseline ahead of any injected delay

    for height in range(1, max_height + 1):
        round_ = 0
        proposer = select_proposer(height, round_)
        proposer_node_id = node_ids[proposer.index]

        # -- Propose: build + sign the block locally (no direct network
        # broadcast here -- header/body are distributed below, through
        # the fault-injected path, to every node including the proposer). --
        result = propose(
            states[proposer_node_id],
            network=network,
            ledger=ledgers[proposer_node_id],
            self_identity=proposer,
            validator_node_ids=node_ids,
            peers=[],
            pending_transactions=[],
            chain_id=chain_id,
            exec_config=exec_config,
            logical_time=logical_time,
        )
        assert result.success, result.reason
        header = result.header
        block_hash = header.block_hash()
        log_propose(
            runner,
            proposer_node_id=proposer_node_id,
            block_hash=block_hash,
            tx_count=0,
            height=height,
            round_=round_,
            logical_time=logical_time,
        )

        # The proposer already holds its own block -- no network hop needed.
        states[proposer_node_id].block_store.store_header(header)
        states[proposer_node_id].block_store.store_body(block_hash, [])
        broadcast_peers = [nid for nid in node_ids if nid != proposer_node_id]

        def _store_header(receiver: str) -> None:
            store_result = states[receiver].block_store.store_header(header)
            assert store_result.success

        _broadcast_payload_with_faults(
            fault_injector=fault_injector,
            network=network,
            sender_node_id=proposer_node_id,
            payload=header.signed_bytes(),
            receiver_node_ids=broadcast_peers,
            logical_time=logical_time,
            height=height,
            round_=round_,
            on_deliver=_store_header,
            stats=stats,
        )

        def _store_body(receiver: str) -> None:
            store_result = states[receiver].block_store.store_body(block_hash, [])
            assert store_result.success

        _broadcast_payload_with_faults(
            fault_injector=fault_injector,
            network=network,
            sender_node_id=proposer_node_id,
            payload=encode_transaction_list([]),
            receiver_node_ids=broadcast_peers,
            logical_time=logical_time,
            height=height,
            round_=round_,
            on_deliver=_store_body,
            stats=stats,
        )

        network.run()
        logical_time += time_step

        # -- Prevote: every validator signs its own prevote locally, then
        # it is gossiped to every other node under injected faults. --
        prevotes = []
        for validator in validators:
            nid = node_ids[validator.index]
            vote = Vote.create_signed(
                chain_id=chain_id,
                height=height,
                round=round_,
                phase=PHASE_PREVOTE,
                block_hash_or_nil=block_hash,
                validator_pubkey=validator.public_key,
                validator_privkey=validator.private_key,
            )
            states[nid].prevotes.add(vote)
            prevotes.append(vote)

        log_prevotes(
            runner,
            node_ids=node_ids,
            prevotes=prevotes,
            height=height,
            round_=round_,
            logical_time=logical_time,
        )

        _distribute_votes_with_faults(
            fault_injector=fault_injector,
            scheduler=scheduler,
            network=network,
            votes=prevotes,
            voter_node_ids=node_ids,
            receiver_node_ids=node_ids,
            states=states,
            vote_set_attr="prevotes",
            logical_time=logical_time,
            height=height,
            round_=round_,
            stats=stats,
        )

        network.run()
        logical_time += time_step

        for nid in node_ids:
            distinct = {
                v.validator_pubkey
                for v in states[nid].prevotes.votes(height, round_, PHASE_PREVOTE)
            }
            vote_counts.setdefault((height, PHASE_PREVOTE), {})[nid] = len(distinct)
            apply_lock(states[nid], round=round_, validator_count=validator_count)

        log_locks(
            runner,
            node_ids=node_ids,
            states=states,
            height=height,
            round_=round_,
            logical_time=logical_time,
        )

        # -- Precommit: same pattern as prevote. --
        precommits = []
        for validator in validators:
            nid = node_ids[validator.index]
            state = states[nid]
            target = (
                state.locked_block_hash
                if state.locked_block_hash is not None
                and state.prevotes.has_quorum(
                    height=height, round=round_, phase=PHASE_PREVOTE,
                    n=validator_count, block_hash=state.locked_block_hash,
                )
                else None
            )
            vote = Vote.create_signed(
                chain_id=chain_id,
                height=height,
                round=round_,
                phase=PHASE_PRECOMMIT,
                block_hash_or_nil=target,
                validator_pubkey=validator.public_key,
                validator_privkey=validator.private_key,
            )
            state.precommits.add(vote)
            precommits.append(vote)

        log_precommits(
            runner,
            node_ids=node_ids,
            precommits=precommits,
            height=height,
            round_=round_,
            logical_time=logical_time,
        )

        _distribute_votes_with_faults(
            fault_injector=fault_injector,
            scheduler=scheduler,
            network=network,
            votes=precommits,
            voter_node_ids=node_ids,
            receiver_node_ids=node_ids,
            states=states,
            vote_set_attr="precommits",
            logical_time=logical_time,
            height=height,
            round_=round_,
            stats=stats,
        )

        network.run()
        logical_time += time_step

        for nid in node_ids:
            distinct = {
                v.validator_pubkey
                for v in states[nid].precommits.votes(height, round_, PHASE_PRECOMMIT)
            }
            vote_counts.setdefault((height, PHASE_PRECOMMIT), {})[nid] = len(distinct)

        # -- Finalize: every node independently reaches quorum. --
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

        log_finalizes(
            runner,
            node_ids=node_ids,
            ledgers=ledgers,
            block_hash=block_hash,
            height=height,
            round_=round_,
            logical_time=logical_time,
        )

    for nid in node_ids:
        runner.register_ledger(nid, ledgers[nid])

    runner.check_assertions()
    return T2Run(
        runner=runner,
        node_ids=node_ids,
        ledgers=ledgers,
        max_height=max_height,
        stats=stats,
        vote_counts=vote_counts,
    )


# ---------------------------------------------------------------------
# Assertions
# ---------------------------------------------------------------------

def test_t2_faults_actually_injected_duplicates_and_reorders():
    """Sanity check: the seeded run actually exercised duplicate + reorder."""
    t2 = _run_t2()

    assert t2.stats.duplicated_legs > 0
    assert t2.stats.extra_copies_sent > 0
    assert t2.stats.reordered_receivers > 0
    # T2 has drop_probability == 0.0: nothing should ever be dropped.
    assert t2.stats.dropped == 0
    # duplicates must show up as ignored, never as equivocation.
    assert t2.stats.duplicate_ignored > 0
    assert t2.stats.equivocations == 0

    t2.runner.shutdown()


def test_t2_vote_count_correct_despite_duplicates():
    """Every node counts exactly `num_validators` distinct voters per
    (height, phase), regardless of how many duplicate copies of each
    vote were delivered."""
    t2 = _run_t2()
    validator_count = 8

    assert t2.vote_counts  # sanity: something was recorded
    for (_height, _phase), per_node in t2.vote_counts.items():
        for nid, distinct_count in per_node.items():
            assert distinct_count == validator_count, (nid, distinct_count)

    # Total ACCEPTED votes across the whole run must equal exactly
    # num_validators distinct senders per (height, phase, receiver) --
    # i.e. duplicates never get double-counted as new acceptances.
    expected_accepted = t2.max_height * 2 * validator_count * (validator_count - 1)
    assert t2.stats.accepted == expected_accepted

    t2.runner.shutdown()


def test_t2_no_conflicting_finalization():
    """Safety must hold: no two nodes finalize a different hash at the
    same height, despite duplicate/reordered message delivery."""
    t2 = _run_t2()
    runner = t2.runner

    assert runner.safety_result.ok
    assert runner.safety_result.violations == []

    assert runner.liveness_result.ok
    assert runner.liveness_result.max_finalized_height == t2.max_height

    reference = t2.ledgers[t2.node_ids[0]]
    assert reference.finalized_height == t2.max_height

    for nid in t2.node_ids:
        ledger = t2.ledgers[nid]
        assert ledger.finalized_height == t2.max_height
        assert ledger.finalized_hash == reference.finalized_hash

        for height in range(1, t2.max_height + 1):
            entry = ledger.get_entry(height)
            reference_entry = reference.get_entry(height)
            assert entry.block_hash == reference_entry.block_hash
            assert entry.header.state_hash == reference_entry.header.state_hash

    runner.shutdown()
