"""
Unit tests for src.crypto.

Full test:
python -m pytest tests/ -v

T1-05:
python -m pytest tests/ -v -m hash

- Verify SHA-256 output
- Verify output length is exactly 32 bytes
- Verify deterministic behavior

T1-08:
python -m pytest tests/ -v -m sign_verify

Ed25519 sign/verify with domain separation tests
"""

import pytest

from src.crypto import hash_bytes, SIGNATURE_LEN, sign, verify

import json
from pathlib import Path
FIXTURE_PATH = Path(__file__).resolve().parents[1] / "config" / "validator_keys.json"

@pytest.fixture(scope="session")
def fixture():
    with open(FIXTURE_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

def hx(h: str) -> bytes:
    return bytes.fromhex(h)


# ===================================================
# T1-05: hash_bytes tests
# ===================================================
@pytest.mark.hash
def test_hash_bytes_returns_bytes():
    result = hash_bytes(b"hello")

    assert isinstance(result, bytes)

@pytest.mark.hash
def test_hash_bytes_returns_32_bytes():
    result = hash_bytes(b"hello")

    assert len(result) == 32

@pytest.mark.hash
def test_hash_bytes_empty_input():
    result = hash_bytes(b"")

    expected = bytes.fromhex(
        "e3b0c44298fc1c149afbf4c8996fb924"
        "27ae41e4649b934ca495991b7852b855"
    )

    assert result == expected

@pytest.mark.hash
def test_hash_bytes_known_sha256_value():
    result = hash_bytes(b"abc")

    expected = bytes.fromhex(
        "ba7816bf8f01cfea414140de5dae2223"
        "b00361a396177a9cb410ff61f20015ad"
    )

    assert result == expected

@pytest.mark.hash
def test_hash_bytes_is_deterministic():
    data = b"blockchain simulator"

    hash_a = hash_bytes(data)
    hash_b = hash_bytes(data)

    assert hash_a == hash_b

@pytest.mark.hash
def test_hash_bytes_changes_for_different_input():
    hash_a = hash_bytes(b"transaction-1")
    hash_b = hash_bytes(b"transaction-2")

    assert hash_a != hash_b

@pytest.mark.hash
def test_hash_bytes_rejects_string():
    with pytest.raises(TypeError):
        hash_bytes("hello")

@pytest.mark.hash
def test_hash_bytes_rejects_integer():
    with pytest.raises(TypeError):
        hash_bytes(123)


# ===================================================
# Sign / Verify tests
# ===================================================
@pytest.mark.sign_verify
def test_sign_verify_success(fixture):
    # Correct key + correct domain + correct payload -> PASS
    chain_id = fixture["chain_id"]
    validator = fixture["validator_keys"][0]
    sk = hx(validator["private_key_hex"])
    pk = hx(validator["public_key_hex"])

    payload = b"canonical-payload"
    domain = f"VOTE:{chain_id}"
    signature = sign(sk, domain, payload)

    assert len(signature) == SIGNATURE_LEN
    assert verify(pk, domain, payload, signature) is True


@pytest.mark.sign_verify
def test_verify_fail_wrong_domain(fixture):
    # Correct key + wrong domain -> FAIL
    chain_id = fixture["chain_id"]
    validator = fixture["validator_keys"][0]
    sk = hx(validator["private_key_hex"])
    pk = hx(validator["public_key_hex"])

    payload = b"canonical-payload"
    signature = sign(sk, f"VOTE:{chain_id}", payload)

    assert verify(
        pk, f"HEADER:{chain_id}", payload, signature,
    ) is False


@pytest.mark.sign_verify
def test_verify_fail_wrong_key(fixture):
    # Wrong public key -> FAIL
    chain_id = fixture["chain_id"]
    signer = fixture["validator_keys"][0]
    other = fixture["validator_keys"][1]
    
    sk = hx(signer["private_key_hex"])
    wrong_pk = hx(other["public_key_hex"])

    payload = b"canonical-payload"
    domain = f"VOTE:{chain_id}"

    signature = sign(sk, domain, payload)

    assert verify(
        wrong_pk, domain, payload, signature,
    ) is False


@pytest.mark.sign_verify
def test_verify_fail_wrong_payload(fixture):
    # Modified payload -> FAIL
    chain_id = fixture["chain_id"]

    validator = fixture["validator_keys"][0]
    sk = hx(validator["private_key_hex"])
    pk = hx(validator["public_key_hex"])

    domain = f"VOTE:{chain_id}"
    original_payload = b"height=1|round=0|phase=PREVOTE"
    tampered_payload = b"height=1|round=0|phase=PRECOMMIT"

    signature = sign(sk, domain, original_payload)

    assert verify(
        pk, domain, tampered_payload, signature,
    ) is False