import os
from src.block import BlockHeader
from src.block_store import BlockStore
from src.transaction import Transaction

CHAIN_ID = "lab01-testnet"


def make_pubkey_and_privkey():
    """
    Generate an unrelated (privkey, pubkey) pair for test purposes.
    """
    privkey = os.urandom(32)
    pubkey = os.urandom(32)
    return privkey, pubkey


def make_header(height=1, round=0):
    sk, pk = make_pubkey_and_privkey()
    return BlockHeader.create_signed(
        chain_id=CHAIN_ID,
        height=height,
        round=round,
        parent_hash=b"\x00" * 32,
        tx_root=b"\x11" * 32,
        state_hash=b"\x22" * 32,
        proposer_pubkey=pk,
        proposer_privkey=sk,
    )


def make_fake_tx():
    return Transaction(
        chain_id=CHAIN_ID,
        nonce=0,
        sender_pubkey=b"\x01" * 32,
        key="00" * 32 + "/x",
        value_bytes=b"y",
        signature=b"\x00" * 64,
    )


def test_body_before_header_is_rejected():
    """A body must never be accepted before its header."""
    store = BlockStore()
    header = make_header()
    block_hash = header.block_hash()

    result = store.store_body(block_hash, [])

    assert not result.success
    assert result.rejection.code == "HEADER_NOT_FOUND"
    assert not store.has_body(block_hash)
    assert not store.is_complete(block_hash)


def test_store_header_then_body_becomes_complete():
    store = BlockStore()
    header = make_header()
    block_hash = header.block_hash()

    header_result = store.store_header(header)
    assert header_result.success
    assert store.has_header(block_hash)
    assert not store.has_body(block_hash)
    assert not store.is_complete(block_hash)

    body_result = store.store_body(block_hash, [])
    assert body_result.success
    assert store.has_body(block_hash)
    assert store.is_complete(block_hash)


def test_reobserving_identical_header_is_idempotent():
    store = BlockStore()
    header = make_header()

    first = store.store_header(header)
    second = store.store_header(header)

    assert first.success
    assert second.success


def test_reobserving_identical_body_is_idempotent():
    store = BlockStore()
    header = make_header()
    block_hash = header.block_hash()
    store.store_header(header)

    first = store.store_body(block_hash, [])
    second = store.store_body(block_hash, [])

    assert first.success
    assert second.success


def test_conflicting_body_for_same_block_hash_is_rejected():
    """Once a body is stored for a block_hash, a different body must not
    silently overwrite it (append-only / no rollback)."""
    store = BlockStore()
    header = make_header()
    block_hash = header.block_hash()
    store.store_header(header)
    store.store_body(block_hash, [])

    conflicting_result = store.store_body(block_hash, [make_fake_tx()])

    assert not conflicting_result.success
    assert conflicting_result.rejection.code == "BODY_CONFLICT"
    # original (empty) body must still be what's stored
    assert store.get_body(block_hash) == ()


def test_get_header_and_get_body_round_trip():
    store = BlockStore()
    header = make_header()
    block_hash = header.block_hash()
    tx = make_fake_tx()

    store.store_header(header)
    store.store_body(block_hash, [tx])

    assert store.get_header(block_hash) == header
    assert store.get_body(block_hash) == (tx,)


def test_unknown_block_hash_returns_none():
    store = BlockStore()
    unknown_hash = b"\xff" * 32

    assert store.get_header(unknown_hash) is None
    assert store.get_body(unknown_hash) is None
    assert not store.has_header(unknown_hash)
    assert not store.has_body(unknown_hash)
    assert not store.is_complete(unknown_hash)