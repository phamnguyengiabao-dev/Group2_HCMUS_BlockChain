"""
Tests for T2-01 BlockHeader.
"""

from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
)
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
    PublicFormat,
)

from src.block import BlockHeader
from src.crypto import hash_bytes, verify


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