"""
Unit tests for the deterministic executor (T1-14).

Correctness properties tested
-------------------------------
P1 — Atomicity:   A single invalid tx in a block invalidates the whole block.
P2 — Determinism: Same inputs → identical post-state hash and result flag.
P3 — No double-apply: Duplicate tx_id in one block → block invalid.
P4 — Canonical order: State reflects the write order exactly.

Additional cases
----------------
* Empty block — valid, post-state == parent-state.
* Multi-sender block — each sender's nonce tracked independently.
* tx with wrong chain_id, wrong nonce, wrong namespace, bad signature — each
  invalidates the whole block (P1).
* Nonce advances after a successful block and is used as input to the next.
"""

from __future__ import annotations

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from src.crypto import hash_bytes, sign
from src.executor import ExecutionConfig, ExecutionResult, execute_block
from src.state import State
from src.transaction import Transaction


# ─────────────────────────────────────────────────────────────
# Shared fixtures / helpers
# ─────────────────────────────────────────────────────────────

CHAIN_ID = "lab01-testnet"
MAX_KEY = 256
MAX_VAL = 4096

DEFAULT_CONFIG = ExecutionConfig(
    chain_id=CHAIN_ID,
    max_key_size=MAX_KEY,
    max_value_size=MAX_VAL,
)


def _keypair() -> tuple[bytes, bytes]:
    """Return (privkey_seed: 32 bytes, pubkey: 32 bytes)."""
    sk = Ed25519PrivateKey.generate()
    priv = sk.private_bytes_raw()
    pub = sk.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    return priv, pub


def _make_tx(
    priv: bytes,
    pub: bytes,
    nonce: int,
    key_suffix: str,
    value: bytes = b"v",
    chain_id: str = CHAIN_ID,
) -> Transaction:
    """Build a correctly signed Transaction."""
    namespace = hash_bytes(pub).hex() + "/"
    key = namespace + key_suffix

    unsigned = Transaction(
        chain_id=chain_id,
        nonce=nonce,
        sender_pubkey=pub,
        key=key,
        value_bytes=value,
        signature=b"",
    )
    sig = sign(priv, f"TX:{chain_id}", unsigned.unsigned_bytes())
    return Transaction(
        chain_id=chain_id,
        nonce=nonce,
        sender_pubkey=pub,
        key=key,
        value_bytes=value,
        signature=sig,
    )


# ─────────────────────────────────────────────────────────────
# Empty block
# ─────────────────────────────────────────────────────────────


def test_empty_block_is_valid():
    """An empty transaction list succeeds and leaves state unchanged."""
    parent = State()
    parent.insert("seed/k", b"seed_val")

    result = execute_block([], parent, {}, DEFAULT_CONFIG)

    assert result.success is True
    assert result.error_tx_index is None
    assert result.error_reason is None
    assert result.post_state.state_hash() == parent.state_hash()
    assert result.applied_tx_ids == []


def test_empty_block_does_not_mutate_parent():
    parent = State()
    parent.insert("seed/k", b"before")
    original_hash = parent.state_hash()

    execute_block([], parent, {}, DEFAULT_CONFIG)

    assert parent.state_hash() == original_hash


# ─────────────────────────────────────────────────────────────
# P2 — Determinism
# ─────────────────────────────────────────────────────────────


def test_determinism_same_block_twice_produces_identical_state_hash():
    """
    Executing the same block twice from the same parent must yield
    byte-identical post_state hashes and the same success flag.  This is the
    core PBT property for T1-14.
    """
    priv, pub = _keypair()
    tx = _make_tx(priv, pub, nonce=0, key_suffix="balance", value=b"100")

    parent = State()
    nonces: dict[bytes, int] = {}

    result_a = execute_block([tx], parent, nonces, DEFAULT_CONFIG)
    result_b = execute_block([tx], parent, nonces, DEFAULT_CONFIG)

    assert result_a.success is True
    assert result_b.success is True
    assert result_a.post_state.state_hash() == result_b.post_state.state_hash()


def test_determinism_multi_tx_block():
    """Multi-tx block run twice → identical post-state hash."""
    priv1, pub1 = _keypair()
    priv2, pub2 = _keypair()

    txs = [
        _make_tx(priv1, pub1, nonce=0, key_suffix="a", value=b"1"),
        _make_tx(priv2, pub2, nonce=0, key_suffix="b", value=b"2"),
        _make_tx(priv1, pub1, nonce=1, key_suffix="c", value=b"3"),
    ]

    parent = State()
    nonces: dict[bytes, int] = {}

    r1 = execute_block(txs, parent, nonces, DEFAULT_CONFIG)
    r2 = execute_block(txs, parent, nonces, DEFAULT_CONFIG)

    assert r1.success and r2.success
    assert r1.post_state.state_hash() == r2.post_state.state_hash()


# ─────────────────────────────────────────────────────────────
# P1 — Atomicity
# ─────────────────────────────────────────────────────────────


def test_invalid_tx_anywhere_invalidates_whole_block():
    """
    One bad tx (wrong nonce) in the middle of a block causes the whole
    block to be rejected; the parent state must not be mutated.
    """
    priv, pub = _keypair()
    good1 = _make_tx(priv, pub, nonce=0, key_suffix="x")
    bad = _make_tx(priv, pub, nonce=99, key_suffix="y")  # wrong nonce
    good2 = _make_tx(priv, pub, nonce=1, key_suffix="z")

    parent = State()
    parent.insert("seed/k", b"original")
    original_hash = parent.state_hash()

    # bad tx is at index 1
    result = execute_block([good1, bad, good2], parent, {}, DEFAULT_CONFIG)

    assert result.success is False
    assert result.error_tx_index == 1
    assert "INVALID_NONCE" in (result.error_reason or "")
    # parent state must be unchanged
    assert parent.state_hash() == original_hash
    # post_state returned is the unmodified parent
    assert result.post_state.state_hash() == original_hash


def test_atomicity_first_tx_invalid():
    """Block where the very first tx is invalid → block rejected."""
    priv, pub = _keypair()
    bad = _make_tx(priv, pub, nonce=5, key_suffix="k")  # nonce 5 ≠ expected 0

    parent = State()
    result = execute_block([bad], parent, {}, DEFAULT_CONFIG)

    assert result.success is False
    assert result.error_tx_index == 0


def test_atomicity_last_tx_invalid():
    """Block where only the last tx is invalid → whole block rejected."""
    priv, pub = _keypair()
    good = _make_tx(priv, pub, nonce=0, key_suffix="ok")
    bad = _make_tx(priv, pub, nonce=99, key_suffix="bad")

    parent = State()
    result = execute_block([good, bad], parent, {}, DEFAULT_CONFIG)

    assert result.success is False
    assert result.error_tx_index == 1


# ─────────────────────────────────────────────────────────────
# P3 — No double-apply (duplicate tx_id within a block)
# ─────────────────────────────────────────────────────────────


def test_duplicate_tx_in_block_is_rejected():
    """
    Submitting the same signed tx twice in one block must be rejected.
    The tx_id is a hash of (unsigned_bytes || signature), so two identical
    Transaction objects have the same tx_id.
    """
    priv, pub = _keypair()
    tx = _make_tx(priv, pub, nonce=0, key_suffix="dup")

    parent = State()
    result = execute_block([tx, tx], parent, {}, DEFAULT_CONFIG)

    assert result.success is False
    assert "DUPLICATE_TX_ID" in (result.error_reason or "")


# ─────────────────────────────────────────────────────────────
# Invalid field checks (all trigger P1 atomicity)
# ─────────────────────────────────────────────────────────────


def test_wrong_chain_id_rejected():
    priv, pub = _keypair()
    tx = _make_tx(priv, pub, nonce=0, key_suffix="k", chain_id="wrong-chain")

    result = execute_block([tx], State(), {}, DEFAULT_CONFIG)

    assert result.success is False
    assert "INVALID_CHAIN_ID" in (result.error_reason or "")


def test_wrong_nonce_rejected():
    priv, pub = _keypair()
    tx = _make_tx(priv, pub, nonce=5, key_suffix="k")  # expected is 0

    result = execute_block([tx], State(), {}, DEFAULT_CONFIG)

    assert result.success is False
    assert "INVALID_NONCE" in (result.error_reason or "")


def test_bad_signature_rejected():
    priv, pub = _keypair()
    tx = _make_tx(priv, pub, nonce=0, key_suffix="k")
    # Flip one bit in the signature.
    bad_sig = bytes([tx.signature[0] ^ 0xFF]) + tx.signature[1:]
    bad_tx = Transaction(
        chain_id=tx.chain_id,
        nonce=tx.nonce,
        sender_pubkey=tx.sender_pubkey,
        key=tx.key,
        value_bytes=tx.value_bytes,
        signature=bad_sig,
    )
    result = execute_block([bad_tx], State(), {}, DEFAULT_CONFIG)

    assert result.success is False
    assert "INVALID_SIGNATURE" in (result.error_reason or "")


def test_wrong_namespace_rejected():
    priv, pub = _keypair()
    # Build a tx whose key doesn't start with the correct namespace.
    unsigned = Transaction(
        chain_id=CHAIN_ID,
        nonce=0,
        sender_pubkey=pub,
        key="bad-ns/key",
        value_bytes=b"v",
        signature=b"",
    )
    sig = sign(priv, f"TX:{CHAIN_ID}", unsigned.unsigned_bytes())
    bad_tx = Transaction(
        chain_id=CHAIN_ID,
        nonce=0,
        sender_pubkey=pub,
        key="bad-ns/key",
        value_bytes=b"v",
        signature=sig,
    )
    result = execute_block([bad_tx], State(), {}, DEFAULT_CONFIG)

    assert result.success is False
    assert "INVALID_NAMESPACE" in (result.error_reason or "")


# ─────────────────────────────────────────────────────────────
# Nonce management
# ─────────────────────────────────────────────────────────────


def test_nonce_advances_after_successful_block():
    """
    After a successful block, the returned nonce map must reflect the
    incremented nonce for each sender.
    """
    priv, pub = _keypair()
    tx0 = _make_tx(priv, pub, nonce=0, key_suffix="a")
    tx1 = _make_tx(priv, pub, nonce=1, key_suffix="b")

    result = execute_block([tx0, tx1], State(), {}, DEFAULT_CONFIG)

    assert result.success is True
    assert result.nonces[pub] == 2


def test_nonce_not_mutated_on_failure():
    """
    On a failed block the original nonce map must be returned intact.
    """
    priv, pub = _keypair()
    good = _make_tx(priv, pub, nonce=0, key_suffix="a")
    bad = _make_tx(priv, pub, nonce=99, key_suffix="b")

    original_nonces: dict[bytes, int] = {pub: 0}
    result = execute_block([good, bad], State(), original_nonces, DEFAULT_CONFIG)

    assert result.success is False
    # The returned nonce map is the unmodified original.
    assert result.nonces is original_nonces


def test_multi_sender_nonces_are_independent():
    """
    Each sender's nonce is tracked separately; advancing one must not
    affect another.
    """
    priv1, pub1 = _keypair()
    priv2, pub2 = _keypair()

    txs = [
        _make_tx(priv1, pub1, nonce=0, key_suffix="a"),
        _make_tx(priv2, pub2, nonce=0, key_suffix="b"),
        _make_tx(priv1, pub1, nonce=1, key_suffix="c"),
    ]

    result = execute_block(txs, State(), {}, DEFAULT_CONFIG)

    assert result.success is True
    assert result.nonces[pub1] == 2
    assert result.nonces[pub2] == 1


# ─────────────────────────────────────────────────────────────
# Sequential blocks (nonce continuity)
# ─────────────────────────────────────────────────────────────


def test_sequential_blocks_use_updated_nonces():
    """
    Nonces from block N must be used as the starting nonces for block N+1.
    """
    priv, pub = _keypair()

    block1 = [_make_tx(priv, pub, nonce=0, key_suffix="k1")]
    r1 = execute_block(block1, State(), {}, DEFAULT_CONFIG)
    assert r1.success is True

    block2 = [_make_tx(priv, pub, nonce=1, key_suffix="k2")]
    r2 = execute_block(block2, r1.post_state, r1.nonces, DEFAULT_CONFIG)
    assert r2.success is True

    # State hash must differ from r1 (new key written).
    assert r2.post_state.state_hash() != r1.post_state.state_hash()


def test_reusing_block1_nonces_for_block2_fails():
    """
    Using the wrong (stale) nonce map for block 2 must fail.
    """
    priv, pub = _keypair()

    block1 = [_make_tx(priv, pub, nonce=0, key_suffix="k1")]
    r1 = execute_block(block1, State(), {}, DEFAULT_CONFIG)
    assert r1.success is True

    # Deliberately pass empty nonces instead of r1.nonces → tx at nonce=1 will fail.
    block2 = [_make_tx(priv, pub, nonce=1, key_suffix="k2")]
    r2 = execute_block(block2, r1.post_state, {}, DEFAULT_CONFIG)
    assert r2.success is False
    assert "INVALID_NONCE" in (r2.error_reason or "")


# ─────────────────────────────────────────────────────────────
# P4 — Canonical order (last write wins)
# ─────────────────────────────────────────────────────────────


def test_last_write_wins_for_same_key():
    """
    Two transactions writing to the same key must leave the last value in
    the post-state.
    """
    priv, pub = _keypair()
    ns = hash_bytes(pub).hex() + "/"
    key = ns + "counter"

    def signed(nonce: int, value: bytes) -> Transaction:
        unsigned = Transaction(
            chain_id=CHAIN_ID, nonce=nonce,
            sender_pubkey=pub, key=key,
            value_bytes=value, signature=b"",
        )
        sig = sign(priv, f"TX:{CHAIN_ID}", unsigned.unsigned_bytes())
        return Transaction(
            chain_id=CHAIN_ID, nonce=nonce,
            sender_pubkey=pub, key=key,
            value_bytes=value, signature=sig,
        )

    txs = [signed(0, b"first"), signed(1, b"second")]
    result = execute_block(txs, State(), {}, DEFAULT_CONFIG)

    assert result.success is True
    assert result.post_state.get(key) == b"second"


# ─────────────────────────────────────────────────────────────
# applied_tx_ids tracking
# ─────────────────────────────────────────────────────────────


def test_applied_tx_ids_populated_on_success():
    priv, pub = _keypair()
    tx0 = _make_tx(priv, pub, nonce=0, key_suffix="a")
    tx1 = _make_tx(priv, pub, nonce=1, key_suffix="b")

    result = execute_block([tx0, tx1], State(), {}, DEFAULT_CONFIG)

    assert result.success is True
    assert len(result.applied_tx_ids) == 2
    assert result.applied_tx_ids[0] == tx0.tx_id()
    assert result.applied_tx_ids[1] == tx1.tx_id()


def test_applied_tx_ids_empty_on_failure():
    priv, pub = _keypair()
    bad_tx = _make_tx(priv, pub, nonce=5, key_suffix="k")

    result = execute_block([bad_tx], State(), {}, DEFAULT_CONFIG)

    assert result.success is False
    assert result.applied_tx_ids == []


# ─────────────────────────────────────────────────────────────
# Parent immutability
# ─────────────────────────────────────────────────────────────


def test_parent_state_not_mutated_on_success():
    priv, pub = _keypair()
    tx = _make_tx(priv, pub, nonce=0, key_suffix="new_key")

    parent = State()
    parent.insert("seed/existing", b"original_value")
    hash_before = parent.state_hash()

    result = execute_block([tx], parent, {}, DEFAULT_CONFIG)

    assert result.success is True
    # The parent must be unchanged regardless of the execution outcome.
    assert parent.state_hash() == hash_before


def test_parent_state_not_mutated_on_failure():
    priv, pub = _keypair()
    bad_tx = _make_tx(priv, pub, nonce=7, key_suffix="k")  # wrong nonce

    parent = State()
    parent.insert("seed/existing", b"original_value")
    hash_before = parent.state_hash()

    execute_block([bad_tx], parent, {}, DEFAULT_CONFIG)

    assert parent.state_hash() == hash_before
