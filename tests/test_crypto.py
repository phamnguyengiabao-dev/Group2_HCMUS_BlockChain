"""
Unit tests for src.crypto.

T1-05:
- Verify SHA-256 output
- Verify output length is exactly 32 bytes
- Verify deterministic behavior
"""

import pytest

from src.crypto import hash_bytes


def test_hash_bytes_returns_bytes():
    result = hash_bytes(b"hello")

    assert isinstance(result, bytes)


def test_hash_bytes_returns_32_bytes():
    result = hash_bytes(b"hello")

    assert len(result) == 32


def test_hash_bytes_empty_input():
    result = hash_bytes(b"")

    expected = bytes.fromhex(
        "e3b0c44298fc1c149afbf4c8996fb924"
        "27ae41e4649b934ca495991b7852b855"
    )

    assert result == expected


def test_hash_bytes_known_sha256_value():
    result = hash_bytes(b"abc")

    expected = bytes.fromhex(
        "ba7816bf8f01cfea414140de5dae2223"
        "b00361a396177a9cb410ff61f20015ad"
    )

    assert result == expected


def test_hash_bytes_is_deterministic():
    data = b"blockchain simulator"

    hash_a = hash_bytes(data)
    hash_b = hash_bytes(data)

    assert hash_a == hash_b


def test_hash_bytes_changes_for_different_input():
    hash_a = hash_bytes(b"transaction-1")
    hash_b = hash_bytes(b"transaction-2")

    assert hash_a != hash_b


def test_hash_bytes_rejects_string():
    with pytest.raises(TypeError):
        hash_bytes("hello")


def test_hash_bytes_rejects_integer():
    with pytest.raises(TypeError):
        hash_bytes(123)