"""Focused tests for the T3-11/T3-12/T3-13 message router."""

from __future__ import annotations

import json

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from src.block import BlockHeader, compute_tx_root
from src.crypto import sign
from src.event_log import EventLog
from src.network import Envelope
from src.router import MessageRouter, RouterContext
from src.state import State
from src.vote import PHASE_PREVOTE, Vote


CHAIN_ID = "router-chain"
HEIGHT = 3
ROUND = 1
PARENT_HASH = b"p" * 32
STATE_HASH = State().state_hash()
TX_ROOT = compute_tx_root([])


def _key_pair(seed: int) -> tuple[bytes, bytes]:
    private = bytes([seed]) * 32
    private_key = Ed25519PrivateKey.from_private_bytes(private)
    return private, private_key.public_key().public_bytes_raw()


@pytest.fixture
def keys() -> tuple[bytes, bytes, bytes, bytes]:
    private_a, public_a = _key_pair(1)
    private_b, public_b = _key_pair(2)
    return private_a, public_a, private_b, public_b


def _context(public_key: bytes) -> RouterContext:
    return RouterContext(
        expected_chain_id=CHAIN_ID,
        expected_height=HEIGHT,
        expected_round=ROUND,
        expected_parent_hash=PARENT_HASH,
        expected_phase=PHASE_PREVOTE,
        validator_set=(public_key,),
    )


def _header(private_key: bytes, public_key: bytes, *, chain_id: str = CHAIN_ID) -> BlockHeader:
    return BlockHeader.create_signed(
        chain_id=chain_id,
        height=HEIGHT,
        round=ROUND,
        parent_hash=PARENT_HASH,
        tx_root=TX_ROOT,
        state_hash=STATE_HASH,
        proposer_pubkey=public_key,
        proposer_privkey=private_key,
    )


def _vote(private_key: bytes, public_key: bytes, *, chain_id: str = CHAIN_ID) -> Vote:
    return Vote.create_signed(
        chain_id=chain_id,
        height=HEIGHT,
        round=ROUND,
        phase=PHASE_PREVOTE,
        block_hash_or_nil=b"b" * 32,
        validator_pubkey=public_key,
        validator_privkey=private_key,
    )


def _envelope(message: object, *, sender: str = "node-a") -> Envelope:
    payload = message.signed_bytes()  # type: ignore[attr-defined]
    return Envelope(
        sender=sender,
        receiver="node-b",
        payload=payload,
        logical_time=7,
        insertion_seq=0,
    )


def _router(
    tmp_path,
    monkeypatch,
    registry: dict[str, bytes],
    context: RouterContext,
    callback,
) -> tuple[MessageRouter, EventLog]:
    monkeypatch.chdir(tmp_path)
    log = EventLog("router", "run")
    return MessageRouter(log, registry, callback, context), log


def test_accepts_signed_header_and_dispatches_once(tmp_path, monkeypatch, keys):
    private_a, public_a, _, _ = keys
    header = _header(private_a, public_a)
    dispatched: list[object] = []
    router, log = _router(tmp_path, monkeypatch, {"node-a": public_a}, _context(public_a), dispatched.append)

    result = router.route(_envelope(header), header)

    assert result.accepted is True
    assert result.rejection_code is None
    assert dispatched == [header]
    assert log.event_count == 0
    log.close()


def test_accepts_signed_vote_and_dispatches_once(tmp_path, monkeypatch, keys):
    private_a, public_a, _, _ = keys
    vote = _vote(private_a, public_a)
    dispatched: list[object] = []
    router, log = _router(tmp_path, monkeypatch, {"node-a": public_a}, _context(public_a), dispatched.append)

    result = router.route(_envelope(vote), vote)

    assert result.accepted is True
    assert dispatched == [vote]
    assert log.event_count == 0
    log.close()


def test_rejects_payload_mismatch_and_does_not_dispatch(tmp_path, monkeypatch, keys):
    private_a, public_a, _, _ = keys
    header = _header(private_a, public_a)
    dispatched: list[object] = []
    router, log = _router(tmp_path, monkeypatch, {"node-a": public_a}, _context(public_a), dispatched.append)
    envelope = Envelope("node-a", "node-b", b"not-the-header", 7, 0)

    result = router.route(envelope, header)

    assert result.accepted is False
    assert result.rejection_code == "PAYLOAD_MISMATCH"
    assert dispatched == []
    assert log.event_count == 1
    log.close()


def test_rejects_unsupported_message_type(tmp_path, monkeypatch, keys):
    _, public_a, _, _ = keys
    dispatched: list[object] = []
    router, log = _router(tmp_path, monkeypatch, {"node-a": public_a}, _context(public_a), dispatched.append)
    envelope = Envelope("node-a", "node-b", b"unsupported", 7, 0)

    result = router.route(envelope, object())

    assert result.rejection_code == "UNSUPPORTED_MESSAGE_TYPE"
    assert dispatched == []
    assert log.event_count == 1
    log.close()


@pytest.mark.parametrize("factory", [_header, _vote])
def test_rejects_wrong_chain_before_identity(tmp_path, monkeypatch, keys, factory):
    private_a, public_a, _, _ = keys
    message = factory(private_a, public_a, chain_id="other-chain")
    dispatched: list[object] = []
    router, log = _router(tmp_path, monkeypatch, {"unknown": public_a}, _context(public_a), dispatched.append)

    result = router.route(_envelope(message), message)

    assert result.accepted is False
    assert result.rejection_code == "CHAIN_ID_MISMATCH"
    assert dispatched == []
    assert log.event_count == 1
    log.close()


def test_rejects_unknown_sender(tmp_path, monkeypatch, keys):
    private_a, public_a, _, _ = keys
    header = _header(private_a, public_a)
    dispatched: list[object] = []
    router, log = _router(tmp_path, monkeypatch, {}, _context(public_a), dispatched.append)

    result = router.route(_envelope(header, sender="unknown"), header)

    assert result.rejection_code == "UNKNOWN_SENDER"
    assert dispatched == []
    assert log.event_count == 1
    log.close()


def test_rejects_spoofed_sender_metadata(tmp_path, monkeypatch, keys):
    private_a, public_a, private_b, public_b = keys
    header = _header(private_b, public_b)
    dispatched: list[object] = []
    router, log = _router(tmp_path, monkeypatch, {"node-a": public_a}, _context(public_b), dispatched.append)

    result = router.route(_envelope(header), header)

    assert result.rejection_code == "SENDER_SIGNER_MISMATCH"
    assert dispatched == []
    assert log.event_count == 1
    log.close()


def test_rejects_invalid_signature_and_logs_one_reject(tmp_path, monkeypatch, keys):
    private_a, public_a, _, _ = keys
    valid = _header(private_a, public_a)
    invalid = BlockHeader(
        chain_id=valid.chain_id,
        height=valid.height,
        round=valid.round,
        parent_hash=valid.parent_hash,
        tx_root=valid.tx_root,
        state_hash=valid.state_hash,
        proposer_pubkey=valid.proposer_pubkey,
        signature=valid.signature[:-1] + bytes([valid.signature[-1] ^ 1]),
    )
    dispatched: list[object] = []
    router, log = _router(tmp_path, monkeypatch, {"node-a": public_a}, _context(public_a), dispatched.append)

    result = router.route(_envelope(invalid), invalid)

    assert result.rejection_code == "INVALID_HEADER_SIGNATURE"
    assert dispatched == []
    assert log.event_count == 1
    log.close()


def test_invalid_vote_domain_is_rejected_and_not_relayed(tmp_path, monkeypatch, keys):
    private_a, public_a, _, _ = keys
    valid = _vote(private_a, public_a)
    # Sign the exact vote bytes under TX rather than VOTE.  The payload still
    # binds to the typed object, so this reaches the signature-domain guard.
    invalid = Vote(
        chain_id=valid.chain_id,
        height=valid.height,
        round=valid.round,
        phase=valid.phase,
        block_hash_or_nil=valid.block_hash_or_nil,
        validator_pubkey=valid.validator_pubkey,
        signature=sign(
            private_a,
            f"TX:{CHAIN_ID}",
            valid.unsigned_bytes(),
        ),
    )
    dispatched: list[object] = []
    router, log = _router(tmp_path, monkeypatch, {"node-a": public_a}, _context(public_a), dispatched.append)

    result = router.route(_envelope(invalid), invalid)

    assert result.rejection_code == "INVALID_SIGNATURE"
    assert dispatched == []
    assert log.event_count == 1
    log.close()


def test_tampered_vote_signature_is_rejected_and_not_relayed(tmp_path, monkeypatch, keys):
    private_a, public_a, _, _ = keys
    valid = _vote(private_a, public_a)
    invalid = Vote(
        chain_id=valid.chain_id,
        height=valid.height,
        round=valid.round,
        phase=valid.phase,
        block_hash_or_nil=valid.block_hash_or_nil,
        validator_pubkey=valid.validator_pubkey,
        signature=valid.signature[:-1] + bytes([valid.signature[-1] ^ 1]),
    )
    dispatched: list[object] = []
    router, log = _router(tmp_path, monkeypatch, {"node-a": public_a}, _context(public_a), dispatched.append)

    result = router.route(_envelope(invalid), invalid)

    assert result.rejection_code == "INVALID_SIGNATURE"
    assert dispatched == []
    assert log.event_count == 1
    log.close()


def test_reject_log_is_deterministic_for_identical_input(tmp_path, monkeypatch, keys):
    private_a, public_a, _, _ = keys
    header = _header(private_a, public_a)
    raw_logs: list[bytes] = []
    for run_id in ("a", "b"):
        monkeypatch.chdir(tmp_path)
        log = EventLog("determinism", run_id)
        router = MessageRouter(log, {"node-a": public_a}, lambda _: None, _context(public_a))
        envelope = Envelope("node-a", "node-b", b"mismatch", 7, 0)
        result = router.route(envelope, header)
        assert result.rejection_code == "PAYLOAD_MISMATCH"
        log.close()
        raw_logs.append(log.log_path.read_bytes())

    assert raw_logs[0] == raw_logs[1]
    record = json.loads(raw_logs[0])
    assert record["event_type"] == "REJECT"
    assert record["details"]["code"] == "PAYLOAD_MISMATCH"
