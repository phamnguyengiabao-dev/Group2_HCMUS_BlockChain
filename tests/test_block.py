"""
Tests for block validation — T2-05.

Covers:
    - T2-01 BlockHeader: block_hash, signature
    - T2-02 compute_tx_root
    - T2-03 validate_header: parent / proposer / height / round / chain_id /
      signature guards
    - T2-04 validate_block_body: tx_root mismatch / invalid tx / state_hash
      mismatch / happy-path success

Each invalid condition must be caught; a valid block must pass.
"""

from __future__ import annotations

import pytest

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
    PublicFormat,
)

from src.block import (
    BlockHeader,
    BlockValidationResult,
    compute_tx_root,
    compute_tx_root_hex,
    validate_block_body,
)
from src.block_validator import (
    HeaderValidationResult,
    expected_proposer,
    validate_header,
)
from src.crypto import hash_bytes, sign
from src.encoding import encode_uint64
from src.executor import ExecutionConfig
from src.state import State
from src.transaction import Transaction


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------

CHAIN_ID = "test-chain"


def make_key_pair() -> tuple[bytes, bytes]:
    """Return (privkey_bytes, pubkey_bytes) for a fresh Ed25519 key pair."""
    sk_obj = Ed25519PrivateKey.generate()
    privkey = sk_obj.private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption())
    pubkey = sk_obj.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    return privkey, pubkey


def make_validator_set(n: int = 4) -> list[tuple[bytes, bytes]]:
    """Return a sorted list of (privkey, pubkey) pairs, sorted by pubkey."""
    pairs = [make_key_pair() for _ in range(n)]
    return sorted(pairs, key=lambda p: p[1])


def fake_tx_id(seed: int) -> bytes:
    """Deterministic 32-byte stand-in for a real tx_id."""
    return hash_bytes(f"tx-{seed}".encode())


def make_valid_tx(
    *,
    chain_id: str = CHAIN_ID,
    privkey: bytes,
    pubkey: bytes,
    nonce: int = 0,
    key_suffix: str = "k",
    value: bytes = b"v",
) -> Transaction:
    """
    Build and sign a valid Transaction. The key is namespaced under the sender.
    """
    namespace = hash_bytes(pubkey).hex() + "/"
    key = namespace + key_suffix

    unsigned = Transaction(
        chain_id=chain_id,
        nonce=nonce,
        sender_pubkey=pubkey,
        key=key,
        value_bytes=value,
        signature=b"\x00" * 64,
    )
    sig = sign(privkey, f"TX:{chain_id}", unsigned.unsigned_bytes())
    return Transaction(
        chain_id=chain_id,
        nonce=nonce,
        sender_pubkey=pubkey,
        key=key,
        value_bytes=value,
        signature=sig,
    )


def make_valid_header(
    *,
    validator_set: list[tuple[bytes, bytes]] | None = None,
    chain_id: str = CHAIN_ID,
    height: int = 1,
    round_: int = 0,
    parent_hash: bytes = b"\x00" * 32,
    tx_root: bytes | None = None,
    state_hash: bytes | None = None,
) -> tuple[BlockHeader, list[bytes], list[bytes]]:
    """
    Build a correctly signed BlockHeader.

    Returns (header, pubkeys_sorted, privkeys_sorted) so callers can build
    matching validate_header() calls without re-deriving the validator set.
    """
    if validator_set is None:
        validator_set = make_validator_set(4)

    privkeys = [p[0] for p in validator_set]
    pubkeys = [p[1] for p in validator_set]

    proposer_idx = (height + round_) % len(pubkeys)
    proposer_privkey = privkeys[proposer_idx]
    proposer_pubkey = pubkeys[proposer_idx]

    if tx_root is None:
        tx_root = compute_tx_root([])
    if state_hash is None:
        state_hash = State().state_hash()

    header = BlockHeader.create_signed(
        chain_id=chain_id,
        height=height,
        round=round_,
        parent_hash=parent_hash,
        tx_root=tx_root,
        state_hash=state_hash,
        proposer_pubkey=proposer_pubkey,
        proposer_privkey=proposer_privkey,
    )
    return header, pubkeys, privkeys


def default_exec_config() -> ExecutionConfig:
    return ExecutionConfig(
        chain_id=CHAIN_ID,
        max_key_size=256,
        max_value_size=1024,
    )


# ===========================================================================
# T2-01 — BlockHeader: block_hash and signature
# ===========================================================================

def test_block_hash_returns_bytes():
    header, _, _ = make_valid_header()
    assert isinstance(header.block_hash(), bytes)


def test_block_hash_is_32_bytes():
    header, _, _ = make_valid_header()
    assert len(header.block_hash()) == 32


def test_block_hash_is_deterministic():
    header, _, _ = make_valid_header()
    assert header.block_hash() == header.block_hash()


def test_block_hash_matches_signed_header():
    header, _, _ = make_valid_header()
    assert header.block_hash() == hash_bytes(header.signed_bytes())


def test_header_signature_is_valid():
    from src.crypto import verify
    header, _, _ = make_valid_header()
    assert verify(
        header.proposer_pubkey,
        f"HEADER:{header.chain_id}",
        header.unsigned_bytes(),
        header.signature,
    )


def test_signed_bytes_differ_when_signature_tampered():
    header, _, _ = make_valid_header()
    bad_sig = header.signature[:-1] + bytes([header.signature[-1] ^ 0xFF])
    tampered = BlockHeader(
        chain_id=header.chain_id,
        height=header.height,
        round=header.round,
        parent_hash=header.parent_hash,
        tx_root=header.tx_root,
        state_hash=header.state_hash,
        proposer_pubkey=header.proposer_pubkey,
        signature=bad_sig,
    )
    assert header.signed_bytes() != tampered.signed_bytes()
    assert header.block_hash() != tampered.block_hash()


def test_block_hash_hex_is_lowercase_64_chars():
    header, _, _ = make_valid_header()
    result = header.block_hash_hex()
    assert len(result) == 64
    assert result == result.lower()


# ===========================================================================
# T2-02 — compute_tx_root
# ===========================================================================

def test_tx_root_empty_block_is_hash_of_count_zero():
    assert compute_tx_root([]) == hash_bytes(encode_uint64(0))


def test_tx_root_returns_32_bytes():
    assert len(compute_tx_root([fake_tx_id(0), fake_tx_id(1)])) == 32


def test_tx_root_matches_manual_concatenation():
    tx_ids = [fake_tx_id(0), fake_tx_id(1), fake_tx_id(2)]
    expected = hash_bytes(
        encode_uint64(3) + tx_ids[0] + tx_ids[1] + tx_ids[2]
    )
    assert compute_tx_root(tx_ids) == expected


def test_tx_root_is_deterministic():
    tx_ids = [fake_tx_id(0), fake_tx_id(1)]
    assert compute_tx_root(tx_ids) == compute_tx_root(tx_ids)


def test_tx_root_sensitive_to_order():
    assert compute_tx_root([fake_tx_id(0), fake_tx_id(1)]) != \
           compute_tx_root([fake_tx_id(1), fake_tx_id(0)])


def test_tx_root_sensitive_to_count():
    single = [fake_tx_id(0)]
    double = [fake_tx_id(0), fake_tx_id(0)]
    assert compute_tx_root(single) != compute_tx_root(double)


def test_tx_root_differs_from_empty_when_nonempty():
    assert compute_tx_root([fake_tx_id(0)]) != compute_tx_root([])


def test_tx_root_rejects_wrong_length_tx_id():
    with pytest.raises(ValueError):
        compute_tx_root([b"\x00" * 31])


def test_tx_root_hex_matches_raw():
    tx_ids = [fake_tx_id(0)]
    assert compute_tx_root_hex(tx_ids) == compute_tx_root(tx_ids).hex()


# ===========================================================================
# T2-03 — validate_header: all rejection guards (F-26)
# ===========================================================================

def test_validate_header_happy_path():
    header, pubkeys, _ = make_valid_header(height=1, round_=0)
    result = validate_header(
        header,
        expected_chain_id=CHAIN_ID,
        expected_height=1,
        expected_round=0,
        expected_parent_hash=b"\x00" * 32,
        validator_set=pubkeys,
    )
    assert result.success
    assert result.rejection is None


def test_validate_header_wrong_chain_id():
    header, pubkeys, _ = make_valid_header()
    result = validate_header(
        header,
        expected_chain_id="other-chain",
        expected_height=1,
        expected_round=0,
        expected_parent_hash=b"\x00" * 32,
        validator_set=pubkeys,
    )
    assert not result.success
    assert result.rejection.code == "CHAIN_ID_MISMATCH"


def test_validate_header_wrong_height():
    header, pubkeys, _ = make_valid_header(height=1)
    result = validate_header(
        header,
        expected_chain_id=CHAIN_ID,
        expected_height=2,          # ← wrong
        expected_round=0,
        expected_parent_hash=b"\x00" * 32,
        validator_set=pubkeys,
    )
    assert not result.success
    assert result.rejection.code == "HEIGHT_MISMATCH"


def test_validate_header_wrong_round():
    header, pubkeys, _ = make_valid_header(height=1, round_=0)
    result = validate_header(
        header,
        expected_chain_id=CHAIN_ID,
        expected_height=1,
        expected_round=1,           # ← wrong
        expected_parent_hash=b"\x00" * 32,
        validator_set=pubkeys,
    )
    assert not result.success
    assert result.rejection.code == "ROUND_MISMATCH"


def test_validate_header_wrong_parent_hash():
    header, pubkeys, _ = make_valid_header(height=1)
    result = validate_header(
        header,
        expected_chain_id=CHAIN_ID,
        expected_height=1,
        expected_round=0,
        expected_parent_hash=b"\xff" * 32,  # ← wrong
        validator_set=pubkeys,
    )
    assert not result.success
    assert result.rejection.code == "PARENT_HASH_MISMATCH"


def test_validate_header_wrong_proposer():
    """A header signed by validator[0] but the expected proposer is validator[1]."""
    validator_set = make_validator_set(4)
    privkeys = [p[0] for p in validator_set]
    pubkeys = [p[1] for p in validator_set]

    # Sign with validator[0] but height=1, round=1 → expected proposer index = (1+1)%4 = 2
    wrong_privkey = privkeys[0]
    wrong_pubkey = pubkeys[0]

    header = BlockHeader.create_signed(
        chain_id=CHAIN_ID,
        height=1,
        round=1,
        parent_hash=b"\x00" * 32,
        tx_root=compute_tx_root([]),
        state_hash=State().state_hash(),
        proposer_pubkey=wrong_pubkey,
        proposer_privkey=wrong_privkey,
    )

    result = validate_header(
        header,
        expected_chain_id=CHAIN_ID,
        expected_height=1,
        expected_round=1,
        expected_parent_hash=b"\x00" * 32,
        validator_set=pubkeys,
    )
    assert not result.success
    assert result.rejection.code == "UNEXPECTED_PROPOSER"


def test_validate_header_invalid_signature():
    """A header where the signature bytes have been tampered with."""
    header, pubkeys, _ = make_valid_header(height=1, round_=0)

    bad_sig = header.signature[:-1] + bytes([header.signature[-1] ^ 0xFF])
    tampered = BlockHeader(
        chain_id=header.chain_id,
        height=header.height,
        round=header.round,
        parent_hash=header.parent_hash,
        tx_root=header.tx_root,
        state_hash=header.state_hash,
        proposer_pubkey=header.proposer_pubkey,
        signature=bad_sig,
    )

    result = validate_header(
        tampered,
        expected_chain_id=CHAIN_ID,
        expected_height=1,
        expected_round=0,
        expected_parent_hash=b"\x00" * 32,
        validator_set=pubkeys,
    )
    assert not result.success
    assert result.rejection.code == "INVALID_HEADER_SIGNATURE"


def test_validate_header_wrong_domain_signature():
    """Header signed under a wrong domain — must fail signature check."""
    validator_set = make_validator_set(4)
    privkeys = [p[0] for p in validator_set]
    pubkeys = [p[1] for p in validator_set]

    proposer_idx = (1 + 0) % 4
    proposer_privkey = privkeys[proposer_idx]
    proposer_pubkey = pubkeys[proposer_idx]

    # Build unsigned header bytes but sign under wrong domain "VOTE:test-chain"
    dummy = BlockHeader(
        chain_id=CHAIN_ID,
        height=1,
        round=0,
        parent_hash=b"\x00" * 32,
        tx_root=compute_tx_root([]),
        state_hash=State().state_hash(),
        proposer_pubkey=proposer_pubkey,
        signature=b"\x00" * 64,
    )
    wrong_domain_sig = sign(proposer_privkey, f"VOTE:{CHAIN_ID}", dummy.unsigned_bytes())

    bad_header = BlockHeader(
        chain_id=CHAIN_ID,
        height=1,
        round=0,
        parent_hash=b"\x00" * 32,
        tx_root=compute_tx_root([]),
        state_hash=State().state_hash(),
        proposer_pubkey=proposer_pubkey,
        signature=wrong_domain_sig,
    )

    result = validate_header(
        bad_header,
        expected_chain_id=CHAIN_ID,
        expected_height=1,
        expected_round=0,
        expected_parent_hash=b"\x00" * 32,
        validator_set=pubkeys,
    )
    assert not result.success
    assert result.rejection.code == "INVALID_HEADER_SIGNATURE"


def test_validate_header_guard_order_chain_id_before_height():
    """chain_id guard fires before height guard when both are wrong."""
    header, pubkeys, _ = make_valid_header(height=1)
    result = validate_header(
        header,
        expected_chain_id="wrong-chain",
        expected_height=99,
        expected_round=0,
        expected_parent_hash=b"\x00" * 32,
        validator_set=pubkeys,
    )
    assert not result.success
    assert result.rejection.code == "CHAIN_ID_MISMATCH"


def test_expected_proposer_formula():
    """Proposer index = (height + round) % n for various inputs."""
    pubkeys = [make_key_pair()[1] for _ in range(4)]
    assert expected_proposer(0, 0, pubkeys) == pubkeys[0]
    assert expected_proposer(1, 0, pubkeys) == pubkeys[1]
    assert expected_proposer(0, 1, pubkeys) == pubkeys[1]
    assert expected_proposer(3, 1, pubkeys) == pubkeys[0]   # (3+1)%4 == 0


def test_expected_proposer_empty_set_raises():
    with pytest.raises(ValueError):
        expected_proposer(0, 0, [])


# ===========================================================================
# T2-04 / T2-05 — validate_block_body: F-27, F-28, F-29
# ===========================================================================

def _build_valid_block(
    *,
    chain_id: str = CHAIN_ID,
    height: int = 1,
    round_: int = 0,
    parent_hash: bytes = b"\x00" * 32,
    transactions: list[Transaction] | None = None,
    parent_state: State | None = None,
    parent_nonces: dict | None = None,
) -> tuple[BlockHeader, list[Transaction], State, dict]:
    """
    Build a fully-valid (header + body) block.

    Returns (header, txs, parent_state, parent_nonces).
    The header encodes the *correct* tx_root and state_hash for the given txs.
    """
    if transactions is None:
        transactions = []
    if parent_state is None:
        parent_state = State()
    if parent_nonces is None:
        parent_nonces = {}

    config = default_exec_config()

    from src.executor import execute_block
    exec_result = execute_block(transactions, parent_state, parent_nonces, config)
    assert exec_result.success, f"fixture txs failed: {exec_result.error_reason}"

    tx_ids = [tx.tx_id() for tx in transactions]
    tx_root = compute_tx_root(tx_ids)
    state_hash = exec_result.post_state.state_hash()

    validator_set = make_validator_set(4)
    privkeys = [p[0] for p in validator_set]
    pubkeys = [p[1] for p in validator_set]
    proposer_idx = (height + round_) % len(pubkeys)

    header = BlockHeader.create_signed(
        chain_id=chain_id,
        height=height,
        round=round_,
        parent_hash=parent_hash,
        tx_root=tx_root,
        state_hash=state_hash,
        proposer_pubkey=pubkeys[proposer_idx],
        proposer_privkey=privkeys[proposer_idx],
    )
    return header, transactions, parent_state, parent_nonces


def test_validate_block_body_empty_block_success():
    header, txs, pstate, pnonces = _build_valid_block()
    result = validate_block_body(
        header, txs, pstate, pnonces, default_exec_config()
    )
    assert result.success
    assert result.rejection is None
    assert result.applied_tx_ids == []


def test_validate_block_body_with_transactions_success():
    privkey, pubkey = make_key_pair()
    tx = make_valid_tx(privkey=privkey, pubkey=pubkey, nonce=0)

    header, txs, pstate, pnonces = _build_valid_block(transactions=[tx])
    result = validate_block_body(
        header, txs, pstate, pnonces, default_exec_config()
    )
    assert result.success
    assert len(result.applied_tx_ids) == 1
    assert result.applied_tx_ids[0] == tx.tx_id()


def test_validate_block_body_tx_root_mismatch():
    """Header encodes a tx_root that does not match the actual transactions."""
    privkey, pubkey = make_key_pair()
    tx = make_valid_tx(privkey=privkey, pubkey=pubkey, nonce=0)

    # Build header claiming tx_root = hash of a *different* tx list
    wrong_tx_root = compute_tx_root([fake_tx_id(999)])

    from src.executor import execute_block
    exec_result = execute_block([tx], State(), {}, default_exec_config())
    state_hash = exec_result.post_state.state_hash()

    validator_set = make_validator_set(4)
    privkeys = [p[0] for p in validator_set]
    pubkeys = [p[1] for p in validator_set]

    header = BlockHeader.create_signed(
        chain_id=CHAIN_ID,
        height=1,
        round=0,
        parent_hash=b"\x00" * 32,
        tx_root=wrong_tx_root,
        state_hash=state_hash,
        proposer_pubkey=pubkeys[1],
        proposer_privkey=privkeys[1],
    )

    result = validate_block_body(
        header, [tx], State(), {}, default_exec_config()
    )
    assert not result.success
    assert result.rejection.code == "TX_ROOT_MISMATCH"


def test_validate_block_body_invalid_tx_invalidates_whole_block():
    """A transaction with a wrong nonce causes the entire block to be rejected."""
    privkey, pubkey = make_key_pair()
    # nonce=0 is correct for a fresh sender; but parent_nonces expects nonce=1
    tx = make_valid_tx(privkey=privkey, pubkey=pubkey, nonce=0)

    # Build a header that correctly encodes the *wrong* tx_root & state_hash
    # (so tx_root passes) but parent_nonces says sender already has nonce=1
    parent_nonces = {pubkey: 1}   # next expected nonce is 1, tx has nonce=0

    # Build a "consistent" header — but execution will fail due to nonce
    tx_ids = [tx.tx_id()]
    tx_root = compute_tx_root(tx_ids)

    validator_set = make_validator_set(4)
    privkeys = [p[0] for p in validator_set]
    pubkeys_list = [p[1] for p in validator_set]

    header = BlockHeader.create_signed(
        chain_id=CHAIN_ID,
        height=1,
        round=0,
        parent_hash=b"\x00" * 32,
        tx_root=tx_root,
        state_hash=State().state_hash(),  # irrelevant — will fail before state check
        proposer_pubkey=pubkeys_list[1],
        proposer_privkey=privkeys[1],
    )

    result = validate_block_body(
        header, [tx], State(), parent_nonces, default_exec_config()
    )
    assert not result.success
    assert result.rejection is not None
    # rejection code will contain nonce error (not TX_ROOT or STATE_HASH)
    assert "NONCE" in result.rejection.code or result.rejection.error_tx_index == 0


def test_validate_block_body_state_hash_mismatch():
    """Header claims a state_hash that does not match post-execution state."""
    privkey, pubkey = make_key_pair()
    tx = make_valid_tx(privkey=privkey, pubkey=pubkey, nonce=0)

    tx_root = compute_tx_root([tx.tx_id()])
    wrong_state_hash = b"\xde\xad\xbe\xef" * 8  # 32 bytes of garbage

    validator_set = make_validator_set(4)
    privkeys = [p[0] for p in validator_set]
    pubkeys_list = [p[1] for p in validator_set]

    header = BlockHeader.create_signed(
        chain_id=CHAIN_ID,
        height=1,
        round=0,
        parent_hash=b"\x00" * 32,
        tx_root=tx_root,
        state_hash=wrong_state_hash,
        proposer_pubkey=pubkeys_list[1],
        proposer_privkey=privkeys[1],
    )

    result = validate_block_body(
        header, [tx], State(), {}, default_exec_config()
    )
    assert not result.success
    assert result.rejection.code == "STATE_HASH_MISMATCH"


def test_validate_block_body_duplicate_tx_rejected():
    """Submitting the same tx twice in one block must be rejected (P3)."""
    privkey, pubkey = make_key_pair()
    tx = make_valid_tx(privkey=privkey, pubkey=pubkey, nonce=0)

    # A block with [tx, tx] — executor will catch the duplicate
    two_txs = [tx, tx]
    tx_root = compute_tx_root([tx.tx_id(), tx.tx_id()])

    validator_set = make_validator_set(4)
    privkeys = [p[0] for p in validator_set]
    pubkeys_list = [p[1] for p in validator_set]

    header = BlockHeader.create_signed(
        chain_id=CHAIN_ID,
        height=1,
        round=0,
        parent_hash=b"\x00" * 32,
        tx_root=tx_root,
        state_hash=State().state_hash(),
        proposer_pubkey=pubkeys_list[1],
        proposer_privkey=privkeys[1],
    )

    result = validate_block_body(
        header, two_txs, State(), {}, default_exec_config()
    )
    assert not result.success
    assert "DUPLICATE" in result.rejection.code


def test_validate_block_body_success_returns_state_and_nonces():
    """Happy path: result carries the post-state and updated nonces."""
    privkey, pubkey = make_key_pair()
    tx = make_valid_tx(privkey=privkey, pubkey=pubkey, nonce=0)

    header, txs, pstate, pnonces = _build_valid_block(transactions=[tx])
    result = validate_block_body(
        header, txs, pstate, pnonces, default_exec_config()
    )
    assert result.success
    assert result.state is not None
    assert result.nonces is not None
    # Nonce must have been advanced for the sender
    assert result.nonces.get(pubkey) == 1


def test_validate_block_body_empty_block_state_hash_correct():
    """An empty block's state_hash must equal the parent state's hash."""
    parent_state = State()
    parent_state.insert("some-prefix-whatever/k", b"preexisting")

    # Recalculate what the header should declare
    tx_root = compute_tx_root([])
    state_hash = parent_state.state_hash()   # no txs → state unchanged

    validator_set = make_validator_set(4)
    privkeys = [p[0] for p in validator_set]
    pubkeys_list = [p[1] for p in validator_set]

    header = BlockHeader.create_signed(
        chain_id=CHAIN_ID,
        height=2,
        round=0,
        parent_hash=b"\xaa" * 32,
        tx_root=tx_root,
        state_hash=state_hash,
        proposer_pubkey=pubkeys_list[2],
        proposer_privkey=privkeys[2],
    )

    result = validate_block_body(
        header, [], parent_state, {}, default_exec_config()
    )
    assert result.success
