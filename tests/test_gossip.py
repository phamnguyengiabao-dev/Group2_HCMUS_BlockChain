"""
Tests for src/gossip.py (T4-10) — GossipService.
"""

from __future__ import annotations

import shutil
import pytest

from src.block import BlockHeader, compute_tx_root
from src.event_log import EventLog
from src.gossip import GossipService, GossipResult
from src.identity import load_validator_keys
from src.network import Network
from src.scheduler import Scheduler
from src.state import State
from src.transaction import Transaction, encode_transaction_list
from src.vote import PHASE_PRECOMMIT, PHASE_PREVOTE, Vote
from src.vote_set import VoteSet

CHAIN_ID = "test-gossip"


# ================================================================
# Helpers
# ================================================================

def build_network(scenario_id: str) -> tuple[Network, EventLog]:
    event_log = EventLog(scenario_id=scenario_id, run_id="run1")
    scheduler = Scheduler(seed=42)
    network = Network(event_log=event_log, scheduler=scheduler)
    return network, event_log


def make_header_and_hash(validators, height=1, round_=0, parent_hash=None):
    if parent_hash is None:
        parent_hash = b"\x00" * 32
    tx_root = compute_tx_root([])
    state_hash = State().state_hash()
    proposer_idx = (height + round_) % len(validators)
    proposer = validators[proposer_idx]
    header = BlockHeader.create_signed(
        chain_id=CHAIN_ID,
        height=height,
        round=round_,
        parent_hash=parent_hash,
        tx_root=tx_root,
        state_hash=state_hash,
        proposer_pubkey=proposer.public_key,
        proposer_privkey=proposer.private_key,
    )
    return header, header.block_hash()


def make_precommit_vote(validator, header, chain_id=CHAIN_ID):
    block_hash = header.block_hash()
    return Vote.create_signed(
        chain_id=chain_id,
        height=header.height,
        round=header.round,
        phase=PHASE_PRECOMMIT,
        block_hash_or_nil=block_hash,
        validator_pubkey=validator.public_key,
        validator_privkey=validator.private_key,
    )


@pytest.fixture(scope="module")
def validators():
    return load_validator_keys()


def teardown_function():
    shutil.rmtree("logs", ignore_errors=True)


# ================================================================
# GossipService construction
# ================================================================

def test_gossip_service_construction(validators):
    network, event_log = build_network("gossip_construct")
    gs = GossipService(network=network, self_node_id="validator_0")
    assert gs.node_id == "validator_0"
    assert gs.network is network

def test_gossip_service_invalid_network():
    with pytest.raises(TypeError):
        GossipService(network="not-a-network", self_node_id="v0")


def test_gossip_service_empty_node_id(validators):
    network, _ = build_network("gossip_empty_id")
    with pytest.raises(ValueError):
        GossipService(network=network, self_node_id="")


# ================================================================
# gossip_finalized — basic broadcast
# ================================================================

def test_gossip_finalized_sends_header_body_votes(validators):
    """Each peer receives: header + body + all quorum votes."""
    network, event_log = build_network("gossip_basic")
    gs = GossipService(network=network, self_node_id="validator_0")

    header, block_hash = make_header_and_hash(validators)
    transactions: list[Transaction] = []

    vote_set = VoteSet()
    quorum_votes = []
    for v in validators[:5]:
        vote = make_precommit_vote(v, header)
        vote_set.add(vote)
        quorum_votes.append(vote)

    peers = ["validator_1", "validator_2", "validator_3"]

    result = gs.gossip_finalized(
        header=header,
        transactions=transactions,
        vote_set=vote_set,
        peers=peers,
        logical_time=10,
    )

    assert isinstance(result, GossipResult)
    assert result.height == 1
    assert result.round == 0
    assert result.peers_notified == len(peers)
    assert result.header_sends == len(peers)
    assert result.body_sends == len(peers)
    assert result.vote_sends == len(peers) * 5  # 5 votes × 3 peers

    delivered = network.run()
    # Per peer: 1 header + 1 body + 5 votes = 7
    assert len(delivered) == len(peers) * (1 + 1 + 5)


def test_gossip_finalized_excludes_self(validators):
    """Self node_id in peers list is silently skipped."""
    network, _ = build_network("gossip_exclude_self")
    gs = GossipService(network=network, self_node_id="validator_0")

    header, block_hash = make_header_and_hash(validators)
    vote_set = VoteSet()

    # peers includes self
    peers = ["validator_0", "validator_1", "validator_2"]

    result = gs.gossip_finalized(
        header=header,
        transactions=[],
        vote_set=vote_set,
        peers=peers,
        logical_time=5,
    )

    # Only 2 peers were actually sent to (validator_1, validator_2)
    assert result.peers_notified == 2
    assert result.header_sends == 2


def test_gossip_finalized_empty_peers(validators):
    """Empty peers list → nothing sent."""
    network, _ = build_network("gossip_empty_peers")
    gs = GossipService(network=network, self_node_id="validator_0")

    header, _ = make_header_and_hash(validators)
    vote_set = VoteSet()

    result = gs.gossip_finalized(
        header=header,
        transactions=[],
        vote_set=vote_set,
        peers=[],
        logical_time=1,
    )

    assert result.peers_notified == 0
    assert result.header_sends == 0
    assert result.body_sends == 0
    assert result.vote_sends == 0
    assert network.run() == []


def test_gossip_finalized_nil_votes_excluded(validators):
    """NIL precommit votes are not relayed."""
    network, _ = build_network("gossip_nil_votes")
    gs = GossipService(network=network, self_node_id="validator_0")

    header, block_hash = make_header_and_hash(validators)
    vote_set = VoteSet()

    # 3 non-NIL votes
    for v in validators[:3]:
        vote = make_precommit_vote(v, header)
        vote_set.add(vote)

    # 2 NIL votes
    for v in validators[3:5]:
        nil_vote = Vote.create_signed(
            chain_id=CHAIN_ID,
            height=1,
            round=0,
            phase=PHASE_PRECOMMIT,
            block_hash_or_nil=None,
            validator_pubkey=v.public_key,
            validator_privkey=v.private_key,
        )
        vote_set.add(nil_vote)

    peers = ["validator_5"]
    result = gs.gossip_finalized(
        header=header,
        transactions=[],
        vote_set=vote_set,
        peers=peers,
        logical_time=1,
    )

    # Only 3 non-NIL votes sent
    assert result.vote_sends == 3


def test_gossip_finalized_deterministic_vote_order(validators):
    """Votes are sent in sorted validator_pubkey order (deterministic)."""
    network, _ = build_network("gossip_vote_order")
    gs = GossipService(network=network, self_node_id="validator_0")

    header, block_hash = make_header_and_hash(validators)
    vote_set = VoteSet()

    # Add votes in reverse order to verify sorting
    chosen = validators[:3]
    for v in reversed(chosen):
        vote = make_precommit_vote(v, header)
        vote_set.add(vote)

    peers = ["validator_5"]
    gs.gossip_finalized(
        header=header,
        transactions=[],
        vote_set=vote_set,
        peers=peers,
        logical_time=1,
    )

    delivered = network.run()
    # delivered: [header, body, vote0, vote1, vote2]
    # votes should be in ascending validator_pubkey order
    vote_payloads = delivered[2:]
    expected_order = sorted(
        [make_precommit_vote(v, header).signed_bytes() for v in chosen],
        key=lambda b: b,
    )
    # The actual sort is by validator_pubkey bytes, which determines the order
    pubkeys_in_order = sorted(v.public_key for v in chosen)
    for i, pk in enumerate(pubkeys_in_order):
        v = next(v for v in chosen if v.public_key == pk)
        assert vote_payloads[i] == make_precommit_vote(v, header).signed_bytes()


def test_gossip_finalized_header_payload_correct(validators):
    """Header payload matches header.signed_bytes()."""
    network, _ = build_network("gossip_header_payload")
    gs = GossipService(network=network, self_node_id="validator_0")

    header, _ = make_header_and_hash(validators)
    vote_set = VoteSet()

    gs.gossip_finalized(
        header=header,
        transactions=[],
        vote_set=vote_set,
        peers=["validator_1"],
        logical_time=1,
    )

    delivered = network.run()
    assert delivered[0] == header.signed_bytes()


def test_gossip_finalized_body_payload_correct(validators):
    """Body payload matches encode_transaction_list(transactions)."""
    network, _ = build_network("gossip_body_payload")
    gs = GossipService(network=network, self_node_id="validator_0")

    header, _ = make_header_and_hash(validators)
    vote_set = VoteSet()

    gs.gossip_finalized(
        header=header,
        transactions=[],
        vote_set=vote_set,
        peers=["validator_1"],
        logical_time=1,
    )

    delivered = network.run()
    assert delivered[1] == encode_transaction_list([])
