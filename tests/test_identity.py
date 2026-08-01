"""
Tests for src/identity.py — validator identity loading and validation.

Covers:
- Successful load of all 8 validators
- Public/private key byte lengths
- Sign-then-verify round trip (same validator)
- Cross-validator signature rejection
- get_validator() happy path
- get_validator() IndexError
"""

import pytest

from src.identity import ValidatorIdentity, load_validator_keys, get_validator
from src.crypto import sign, verify

DOMAIN = "test"
PAYLOAD = b"hello blockchain"
NUM_VALIDATORS = 8


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def validators() -> list[ValidatorIdentity]:
    """Load all validators once for the test module."""
    return load_validator_keys()


# ---------------------------------------------------------------------------
# Loading tests
# ---------------------------------------------------------------------------

def test_load_returns_eight_validators(validators):
    """load_validator_keys() must return exactly 8 entries."""
    assert len(validators) == NUM_VALIDATORS


def test_validators_are_ordered_by_index(validators):
    """Validators must be sorted by their index field."""
    indices = [v.index for v in validators]
    assert indices == list(range(NUM_VALIDATORS))


# ---------------------------------------------------------------------------
# Key format tests
# ---------------------------------------------------------------------------

def test_all_public_keys_are_32_bytes(validators):
    """Every public key must be exactly 32 bytes."""
    for v in validators:
        assert isinstance(v.public_key, bytes), f"Validator {v.index}: public_key not bytes"
        assert len(v.public_key) == 32, (
            f"Validator {v.index}: public_key is {len(v.public_key)} bytes, expected 32"
        )


def test_all_private_keys_are_32_bytes(validators):
    """Every private key (seed) must be exactly 32 bytes."""
    for v in validators:
        assert isinstance(v.private_key, bytes), f"Validator {v.index}: private_key not bytes"
        assert len(v.private_key) == 32, (
            f"Validator {v.index}: private_key is {len(v.private_key)} bytes, expected 32"
        )


# ---------------------------------------------------------------------------
# Cryptographic round-trip tests
# ---------------------------------------------------------------------------

def test_sign_and_verify_same_validator(validators):
    """Signing with privkey[i] and verifying with pubkey[i] must succeed for all validators."""
    for v in validators:
        sig = sign(v.private_key, DOMAIN, PAYLOAD)
        assert verify(v.public_key, DOMAIN, PAYLOAD, sig), (
            f"Validator {v.index}: sign/verify round-trip failed"
        )


def test_cross_validator_signature_rejected(validators):
    """Signature from validator 0's private key must NOT verify against validator 1's public key."""
    v0 = validators[0]
    v1 = validators[1]

    sig = sign(v0.private_key, DOMAIN, PAYLOAD)
    result = verify(v1.public_key, DOMAIN, PAYLOAD, sig)

    assert result is False, (
        "Cross-validator signature should be rejected but verify() returned True"
    )


# ---------------------------------------------------------------------------
# get_validator() tests
# ---------------------------------------------------------------------------

def test_get_validator_index_zero():
    """get_validator(0) must return a ValidatorIdentity with index == 0."""
    v = get_validator(0)
    assert isinstance(v, ValidatorIdentity)
    assert v.index == 0


def test_get_validator_returns_correct_index():
    """get_validator(i) must always return a ValidatorIdentity whose index == i."""
    for i in range(NUM_VALIDATORS):
        v = get_validator(i)
        assert v.index == i


def test_get_validator_out_of_range_raises_index_error():
    """get_validator(99) must raise IndexError."""
    with pytest.raises(IndexError):
        get_validator(99)


def test_get_validator_negative_raises_index_error():
    """get_validator(-1) must raise IndexError."""
    with pytest.raises(IndexError):
        get_validator(-1)
