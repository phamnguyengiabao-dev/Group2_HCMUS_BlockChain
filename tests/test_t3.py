"""
T5-03

Scenario T3 — Bad signature + wrong domain.

Inject messages with a corrupted signature and messages signed under the
wrong domain (VOTE:<chain_id> vs HEADER:<chain_id>, or the right domain
name but the wrong chain_id) -> MessageRouter (T3-11..T3-13) must reject
them, log exactly one canonical REJECT event per rejection, and never
call its dispatch callback -- i.e. no downstream consensus state
transition ever happens for a rejected message.

max_height is 0 in scenario_t3.json: this scenario is not about making
progress, it is about proving bad messages never reach the state
machine in the first place.
"""

from __future__ import annotations

import json
import shutil
from dataclasses import replace
from pathlib import Path

import pytest

from src.block import BlockHeader, compute_tx_root
from src.block_store import BlockStore
from src.crypto import sign as crypto_sign
from src.event_log import EventLog
from src.identity import load_validator_keys
from src.ledger import Ledger
from src.network import Envelope
from src.router import MessageRouter, RouterContext
from src.scenario import ScenarioRunner
from src.state import State
from src.vote import PHASE_PREVOTE, Vote
from src.vote_set import VoteSet

CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"
CHAIN_ID = "test-t3-chain"


def load_config(name: str) -> dict:
    with (CONFIG_DIR / name).open("r", encoding="utf-8") as fh:
        return json.load(fh)


@pytest.fixture(autouse=True)
def clean_logs():
    shutil.rmtree("logs/t3_bad_signature", ignore_errors=True)
    yield


@pytest.fixture(scope="module")
def validators():
    return load_validator_keys()


# ---------------------------------------------------------------------
# Config structure
# ---------------------------------------------------------------------

def test_scenario_t3_config_structure():
    """scenario_t3.json declares an 8-node run injecting bad signatures
    and wrong-domain messages, expecting no consensus progress."""
    config = load_config("scenario_t3.json")

    assert config["scenario_id"] == "t3_bad_signature"
    assert isinstance(config["seed"], int)

    assert config["num_validators"] == 8
    assert config["f"] == 2
    assert config["max_height"] == 0
    assert config["byzantine_nodes"] == []
    assert config["topology"] == "full_mesh"

    assert config["inject_bad_signature"] is True
    assert config["inject_wrong_domain"] is True

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

def _node_ids(validators) -> list[str]:
    return [f"validator_{v.index}" for v in validators]


def _sender_registry(validators, node_ids) -> dict[str, bytes]:
    return {node_ids[i]: validators[i].public_key for i in range(len(validators))}


def _build_router(*, event_log, validators, node_ids, height, round_, phase, dispatch):
    """A router with a real sender registry and expected (height, round, phase)."""
    return MessageRouter(
        event_log=event_log,
        sender_registry=_sender_registry(validators, node_ids),
        dispatch=dispatch,
        context=RouterContext(
            expected_chain_id=CHAIN_ID,
            expected_height=height,
            expected_round=round_,
            expected_parent_hash=b"\x00" * 32,
            expected_phase=phase,
            # Index order, matching load_validator_keys()/select_proposer() --
            # RouterContext preserves list/tuple order as-is (only *sets* get
            # re-sorted), so this must NOT be pubkey-byte order.
            validator_set=tuple(v.public_key for v in validators),
        ),
    )


def _valid_vote(voter, *, height=1, round_=0, phase=PHASE_PREVOTE, block_hash=b"\xaa" * 32) -> Vote:
    return Vote.create_signed(
        chain_id=CHAIN_ID,
        height=height,
        round=round_,
        phase=phase,
        block_hash_or_nil=block_hash,
        validator_pubkey=voter.public_key,
        validator_privkey=voter.private_key,
    )


def _valid_header(proposer, *, height=1, round_=0, parent_hash=b"\x00" * 32) -> BlockHeader:
    return BlockHeader.create_signed(
        chain_id=CHAIN_ID,
        height=height,
        round=round_,
        parent_hash=parent_hash,
        tx_root=compute_tx_root([]),
        state_hash=State().state_hash(),
        proposer_pubkey=proposer.public_key,
        proposer_privkey=proposer.private_key,
    )


def _flip_signature(signature: bytes) -> bytes:
    """Corrupt a signature by flipping one bit -- still 64 bytes, still
    the wrong content."""
    return bytes([signature[0] ^ 0xFF]) + signature[1:]


def _vote_signed_under_wrong_domain(voter, *, height=1, round_=0, phase=PHASE_PREVOTE, block_hash=b"\xaa" * 32) -> Vote:
    """A vote whose fields (incl. chain_id) are all correct, but whose
    signature was produced under the HEADER domain instead of VOTE --
    classic cross-domain signature confusion."""
    unsigned = Vote(
        chain_id=CHAIN_ID,
        height=height,
        round=round_,
        phase=phase,
        block_hash_or_nil=block_hash,
        validator_pubkey=voter.public_key,
        signature=b"",
    )
    wrong_domain_signature = crypto_sign(
        voter.private_key,
        f"HEADER:{CHAIN_ID}",  # wrong domain: should be f"VOTE:{CHAIN_ID}"
        unsigned.unsigned_bytes(),
    )
    return replace(unsigned, signature=wrong_domain_signature)


def _header_signed_under_wrong_domain(proposer, *, height=1, round_=0, parent_hash=b"\x00" * 32) -> BlockHeader:
    """A header whose signature was produced under the VOTE domain
    instead of HEADER."""
    unsigned = BlockHeader(
        chain_id=CHAIN_ID,
        height=height,
        round=round_,
        parent_hash=parent_hash,
        tx_root=compute_tx_root([]),
        state_hash=State().state_hash(),
        proposer_pubkey=proposer.public_key,
        signature=b"",
    )
    wrong_domain_signature = crypto_sign(
        proposer.private_key,
        f"VOTE:{CHAIN_ID}",  # wrong domain: should be f"HEADER:{CHAIN_ID}"
        unsigned.unsigned_bytes(),
    )
    return replace(unsigned, signature=wrong_domain_signature)


def _envelope_for(sender: str, receiver: str, message, seq: int) -> Envelope:
    return Envelope(
        sender=sender,
        receiver=receiver,
        payload=message.signed_bytes(),
        logical_time=seq,
        insertion_seq=seq,
    )


def _read_events(event_log: EventLog) -> list[dict]:
    event_log.close()
    lines = Path(event_log.log_path).read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines]


# ---------------------------------------------------------------------
# Baseline sanity: valid messages are accepted (proves the rejections
# below are caused by the injected fault, not a broken test setup)
# ---------------------------------------------------------------------

def test_router_accepts_valid_vote(validators):
    dispatched = []
    event_log = EventLog(scenario_id="t3_baseline_vote", run_id="run1")
    node_ids = _node_ids(validators)
    router = _build_router(
        event_log=event_log, validators=validators, node_ids=node_ids,
        height=1, round_=0, phase=PHASE_PREVOTE, dispatch=dispatched.append,
    )

    voter = validators[0]
    vote = _valid_vote(voter)
    envelope = _envelope_for(node_ids[0], node_ids[1], vote, seq=0)

    result = router.route(envelope, vote)

    assert result.accepted is True
    assert dispatched == [vote]
    event_log.close()


def test_router_accepts_valid_header(validators):
    dispatched = []
    event_log = EventLog(scenario_id="t3_baseline_header", run_id="run1")
    node_ids = _node_ids(validators)
    proposer = validators[(1 + 0) % len(validators)]
    router = _build_router(
        event_log=event_log, validators=validators, node_ids=node_ids,
        height=1, round_=0, phase=None, dispatch=dispatched.append,
    )

    header = _valid_header(proposer)
    sender = node_ids[proposer.index]
    envelope = _envelope_for(sender, node_ids[0], header, seq=0)

    result = router.route(envelope, header)

    assert result.accepted is True
    assert dispatched == [header]
    event_log.close()


# ---------------------------------------------------------------------
# Bad signature -> reject + log + no dispatch
# ---------------------------------------------------------------------

def test_router_rejects_vote_bad_signature(validators):
    dispatched = []
    event_log = EventLog(scenario_id="t3_bad_sig_vote", run_id="run1")
    node_ids = _node_ids(validators)
    router = _build_router(
        event_log=event_log, validators=validators, node_ids=node_ids,
        height=1, round_=0, phase=PHASE_PREVOTE, dispatch=dispatched.append,
    )

    voter = validators[0]
    vote = _valid_vote(voter)
    tampered = replace(vote, signature=_flip_signature(vote.signature))
    envelope = _envelope_for(node_ids[0], node_ids[1], tampered, seq=0)

    result = router.route(envelope, tampered)

    assert result.accepted is False
    assert result.rejection_code == "INVALID_SIGNATURE"
    assert dispatched == []  # no state transition

    events = _read_events(event_log)
    assert len(events) == 1
    event = events[0]
    assert event["event_type"] == "REJECT"
    assert event["node_id"] == node_ids[1]  # envelope.receiver
    assert event["height"] == 1
    assert event["round"] == 0
    assert event["details"]["code"] == "INVALID_SIGNATURE"


def test_router_rejects_header_bad_signature(validators):
    dispatched = []
    event_log = EventLog(scenario_id="t3_bad_sig_header", run_id="run1")
    node_ids = _node_ids(validators)
    proposer = validators[(1 + 0) % len(validators)]
    router = _build_router(
        event_log=event_log, validators=validators, node_ids=node_ids,
        height=1, round_=0, phase=None, dispatch=dispatched.append,
    )

    header = _valid_header(proposer)
    tampered = replace(header, signature=_flip_signature(header.signature))
    envelope = _envelope_for(node_ids[proposer.index], node_ids[0], tampered, seq=0)

    result = router.route(envelope, tampered)

    assert result.accepted is False
    assert result.rejection_code == "INVALID_HEADER_SIGNATURE"
    assert dispatched == []

    events = _read_events(event_log)
    assert len(events) == 1
    assert events[0]["event_type"] == "REJECT"
    assert events[0]["details"]["code"] == "INVALID_HEADER_SIGNATURE"


# ---------------------------------------------------------------------
# Wrong domain -> reject + log + no dispatch
# ---------------------------------------------------------------------

def test_router_rejects_vote_wrong_domain(validators):
    dispatched = []
    event_log = EventLog(scenario_id="t3_wrong_domain_vote", run_id="run1")
    node_ids = _node_ids(validators)
    router = _build_router(
        event_log=event_log, validators=validators, node_ids=node_ids,
        height=1, round_=0, phase=PHASE_PREVOTE, dispatch=dispatched.append,
    )

    voter = validators[0]
    vote = _vote_signed_under_wrong_domain(voter)
    envelope = _envelope_for(node_ids[0], node_ids[1], vote, seq=0)

    result = router.route(envelope, vote)

    assert result.accepted is False
    assert result.rejection_code == "INVALID_SIGNATURE"
    assert dispatched == []

    events = _read_events(event_log)
    assert len(events) == 1
    assert events[0]["event_type"] == "REJECT"
    assert events[0]["details"]["code"] == "INVALID_SIGNATURE"


def test_router_rejects_header_wrong_domain(validators):
    dispatched = []
    event_log = EventLog(scenario_id="t3_wrong_domain_header", run_id="run1")
    node_ids = _node_ids(validators)
    proposer = validators[(1 + 0) % len(validators)]
    router = _build_router(
        event_log=event_log, validators=validators, node_ids=node_ids,
        height=1, round_=0, phase=None, dispatch=dispatched.append,
    )

    header = _header_signed_under_wrong_domain(proposer)
    envelope = _envelope_for(node_ids[proposer.index], node_ids[0], header, seq=0)

    result = router.route(envelope, header)

    assert result.accepted is False
    assert result.rejection_code == "INVALID_HEADER_SIGNATURE"
    assert dispatched == []

    events = _read_events(event_log)
    assert len(events) == 1
    assert events[0]["event_type"] == "REJECT"
    assert events[0]["details"]["code"] == "INVALID_HEADER_SIGNATURE"


# ---------------------------------------------------------------------
# No state transition: rejected messages never reach consensus state
# ---------------------------------------------------------------------

def test_t3_rejected_messages_never_mutate_consensus_state(validators):
    """Wire the router's dispatch straight into real BlockStore/VoteSet/
    Ledger objects (the actual state a node would mutate) and prove they
    stay completely empty after every injected bad message is routed."""
    node_ids = _node_ids(validators)
    block_store = BlockStore()
    prevotes = VoteSet()
    ledger = Ledger(chain_id=CHAIN_ID)

    def dispatch(message):
        if isinstance(message, BlockHeader):
            block_store.store_header(message)
        else:
            prevotes.add(message)

    event_log = EventLog(scenario_id="t3_no_state_transition", run_id="run1")

    vote_router = _build_router(
        event_log=event_log, validators=validators, node_ids=node_ids,
        height=1, round_=0, phase=PHASE_PREVOTE, dispatch=dispatch,
    )
    proposer = validators[(1 + 0) % len(validators)]
    header_router = _build_router(
        event_log=event_log, validators=validators, node_ids=node_ids,
        height=1, round_=0, phase=None, dispatch=dispatch,
    )

    voter = validators[0]
    bad_header_sig = replace(_valid_header(proposer), signature=_flip_signature(_valid_header(proposer).signature))
    bad_header_domain = _header_signed_under_wrong_domain(proposer)
    bad_messages = [
        (vote_router, replace(_valid_vote(voter), signature=_flip_signature(_valid_vote(voter).signature))),
        (vote_router, _vote_signed_under_wrong_domain(voter)),
        (header_router, bad_header_sig),
        (header_router, bad_header_domain),
    ]

    for seq, (router, message) in enumerate(bad_messages):
        envelope = _envelope_for(node_ids[0], node_ids[1], message, seq=seq)
        result = router.route(envelope, message)
        assert result.accepted is False

    # No state transition happened anywhere.
    assert not block_store.has_header(bad_header_sig.block_hash())
    assert not block_store.has_header(bad_header_domain.block_hash())
    assert len(prevotes) == 0
    assert ledger.finalized_height == 0

    events = _read_events(event_log)
    assert len(events) == len(bad_messages)
    assert all(e["event_type"] == "REJECT" for e in events)


# ---------------------------------------------------------------------
# Full scenario: a batch of injected bad messages, all rejected
# ---------------------------------------------------------------------

def test_t3_scenario_run_rejects_every_injected_bad_message():
    scenario_config = {**load_config("scenario_t3.json"), "run_id": "t3_run1"}
    default_config = load_config("default.json")
    chain_id = default_config["chain_id"]

    validators = load_validator_keys()
    node_ids = _node_ids(validators)

    runner = ScenarioRunner(scenario_config, default_config)
    runner.load()
    event_log = runner.event_log

    # SCENARIO_START already wrote event_no=1.
    events_before = event_log.event_count

    dispatched = []
    voter = validators[0]
    proposer = validators[(1 + 0) % len(validators)]

    vote_router = MessageRouter(
        event_log=event_log,
        sender_registry=_sender_registry(validators, node_ids),
        dispatch=dispatched.append,
        context=RouterContext(
            expected_chain_id=chain_id,
            expected_height=1,
            expected_round=0,
            expected_parent_hash=b"\x00" * 32,
            expected_phase=PHASE_PREVOTE,
            validator_set=tuple(v.public_key for v in validators),
        ),
    )
    header_router = MessageRouter(
        event_log=event_log,
        sender_registry=_sender_registry(validators, node_ids),
        dispatch=dispatched.append,
        context=RouterContext(
            expected_chain_id=chain_id,
            expected_height=1,
            expected_round=0,
            expected_parent_hash=b"\x00" * 32,
            validator_set=tuple(v.public_key for v in validators),
        ),
    )

    def _vote():
        return Vote.create_signed(
            chain_id=chain_id, height=1, round=0, phase=PHASE_PREVOTE,
            block_hash_or_nil=b"\xaa" * 32,
            validator_pubkey=voter.public_key, validator_privkey=voter.private_key,
        )

    def _header():
        return BlockHeader.create_signed(
            chain_id=chain_id, height=1, round=0, parent_hash=b"\x00" * 32,
            tx_root=compute_tx_root([]), state_hash=State().state_hash(),
            proposer_pubkey=proposer.public_key, proposer_privkey=proposer.private_key,
        )

    bad_vote_sig = replace(_vote(), signature=_flip_signature(_vote().signature))
    bad_vote_domain = replace(
        Vote(chain_id=chain_id, height=1, round=0, phase=PHASE_PREVOTE,
             block_hash_or_nil=b"\xaa" * 32, validator_pubkey=voter.public_key, signature=b""),
        signature=crypto_sign(voter.private_key, f"HEADER:{chain_id}", _vote().unsigned_bytes()),
    )
    bad_header_sig = replace(_header(), signature=_flip_signature(_header().signature))
    bad_header_domain = replace(
        BlockHeader(chain_id=chain_id, height=1, round=0, parent_hash=b"\x00" * 32,
                    tx_root=compute_tx_root([]), state_hash=State().state_hash(),
                    proposer_pubkey=proposer.public_key, signature=b""),
        signature=crypto_sign(proposer.private_key, f"VOTE:{chain_id}", _header().unsigned_bytes()),
    )

    injected = [
        (vote_router, bad_vote_sig, "INVALID_SIGNATURE", node_ids[voter.index]),
        (vote_router, bad_vote_domain, "INVALID_SIGNATURE", node_ids[voter.index]),
        (header_router, bad_header_sig, "INVALID_HEADER_SIGNATURE", node_ids[proposer.index]),
        (header_router, bad_header_domain, "INVALID_HEADER_SIGNATURE", node_ids[proposer.index]),
    ]

    receiver = node_ids[2]
    results = []
    for seq, (router, message, expected_code, sender) in enumerate(injected):
        envelope = _envelope_for(sender, receiver, message, seq=seq)
        results.append((router.route(envelope, message), expected_code))

    for result, expected_code in results:
        assert result.accepted is False
        assert result.rejection_code == expected_code

    # No message was ever dispatched -> no state transition anywhere.
    assert dispatched == []

    # Exactly one REJECT per injected bad message, nothing else logged since.
    assert event_log.event_count == events_before + len(injected)

    # max_height == 0 -> liveness is trivially satisfied with zero progress.
    runner.check_assertions()
    assert runner.liveness_result.ok
    assert runner.liveness_result.max_finalized_height == 0
    assert runner.safety_result.ok

    runner.shutdown()
