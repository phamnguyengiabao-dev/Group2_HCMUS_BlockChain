"""
Tests for T2-01 BlockHeader and T2-02 tx_root computation.
"""

import pytest

from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
)
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
    PublicFormat,
)

from src.block import BlockHeader, compute_tx_root, compute_tx_root_hex
from src.crypto import hash_bytes, verify
from src.encoding import encode_uint64


def make_key_pair() -> tuple[bytes, bytes]:
    """
    Generate an Ed25519 private key seed and public key.
    """

    private_key_object = (
        Ed25519PrivateKey.generate()
    )

    private_key = (
        private_key_object.private_bytes(
            Encoding.Raw,
            PrivateFormat.Raw,
            NoEncryption(),
        )
    )

    public_key = (
        private_key_object
        .public_key()
        .public_bytes(
            Encoding.Raw,
            PublicFormat.Raw,
        )
    )

    return private_key, public_key


def make_header() -> BlockHeader:
    """
    Create a valid signed header for testing.
    """

    private_key, public_key = (
        make_key_pair()
    )

    return BlockHeader.create_signed(
        chain_id="test-chain",
        height=1,
        round=0,
        parent_hash=b"\x00" * 32,
        tx_root=hash_bytes(b"empty transactions"),
        state_hash=hash_bytes(b"empty state"),
        proposer_pubkey=public_key,
        proposer_privkey=private_key,
    )


def test_block_hash_returns_bytes():
    header = make_header()

    assert isinstance(
        header.block_hash(),
        bytes,
    )


def test_block_hash_is_32_bytes():
    header = make_header()

    assert len(
        header.block_hash()
    ) == 32


def test_block_hash_is_deterministic():
    header = make_header()

    hash_a = header.block_hash()
    hash_b = header.block_hash()

    assert hash_a == hash_b


def test_block_hash_matches_signed_header():
    header = make_header()

    expected = hash_bytes(
        header.signed_bytes()
    )

    assert (
        header.block_hash()
        == expected
    )


def test_header_signature_is_valid():
    header = make_header()

    is_valid = verify(
        header.proposer_pubkey,
        f"HEADER:{header.chain_id}",
        header.unsigned_bytes(),
        header.signature,
    )

    assert is_valid


def test_signed_bytes_change_when_signature_changes():
    header = make_header()

    modified_signature = (
        header.signature[:-1]
        + bytes([
            header.signature[-1] ^ 1
        ])
    )

    modified_header = BlockHeader(
        chain_id=header.chain_id,
        height=header.height,
        round=header.round,
        parent_hash=header.parent_hash,
        tx_root=header.tx_root,
        state_hash=header.state_hash,
        proposer_pubkey=header.proposer_pubkey,
        signature=modified_signature,
    )

    assert (
        header.signed_bytes()
        != modified_header.signed_bytes()
    )

    assert (
        header.block_hash()
        != modified_header.block_hash()
    )


def test_block_hash_hex_is_lowercase():
    header = make_header()

    result = (
        header.block_hash_hex()
    )

    assert len(result) == 64
    assert result == result.lower()


def fake_tx_id(seed: int) -> bytes:
    """A deterministic 32-byte stand-in for a real tx_id."""
    return hash_bytes(f"tx-{seed}".encode("utf-8"))


def test_tx_root_empty_block_is_hash_of_count_zero():
    assert (
        compute_tx_root([])
        == hash_bytes(encode_uint64(0))
    )


def test_tx_root_returns_32_bytes():
    tx_ids = [fake_tx_id(0), fake_tx_id(1)]

    assert len(compute_tx_root(tx_ids)) == 32


def test_tx_root_matches_manual_concatenation():
    tx_ids = [fake_tx_id(0), fake_tx_id(1), fake_tx_id(2)]

    expected = hash_bytes(
        encode_uint64(len(tx_ids))
        + tx_ids[0]
        + tx_ids[1]
        + tx_ids[2]
    )

    assert compute_tx_root(tx_ids) == expected


def test_tx_root_is_deterministic():
    tx_ids = [fake_tx_id(0), fake_tx_id(1)]

    assert (
        compute_tx_root(tx_ids)
        == compute_tx_root(tx_ids)
    )


def test_tx_root_is_sensitive_to_order():
    tx_ids = [fake_tx_id(0), fake_tx_id(1)]
    reordered = [fake_tx_id(1), fake_tx_id(0)]

    assert (
        compute_tx_root(tx_ids)
        != compute_tx_root(reordered)
    )


def test_tx_root_is_sensitive_to_count():
    tx_ids = [fake_tx_id(0), fake_tx_id(0)]

    assert (
        compute_tx_root(tx_ids[:1])
        != compute_tx_root(tx_ids)
    )


def test_tx_root_differs_from_empty_when_nonempty():
    assert (
        compute_tx_root([fake_tx_id(0)])
        != compute_tx_root([])
    )


def test_tx_root_rejects_wrong_length_tx_id():
    with pytest.raises(ValueError):
        compute_tx_root([b"\x00" * 31])


def test_tx_root_hex_matches_raw_digest():
    tx_ids = [fake_tx_id(0)]

    assert (
        compute_tx_root_hex(tx_ids)
        == compute_tx_root(tx_ids).hex()
    )