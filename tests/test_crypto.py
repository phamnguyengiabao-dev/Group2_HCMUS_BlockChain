"""
Unit tests for src/crypto.py

Run all:         pytest tests/test_crypto.py -v
Hash tests only: pytest tests/test_crypto.py -v -m hash
Sign/verify:     pytest tests/test_crypto.py -v -m sign_verify

T1-05 — hash_bytes():
  SHA-256 output, length, determinism, known vectors, type rejection.

T1-08 — sign() / verify() domain separation:
  Signatures are only valid when domain, pubkey, payload, and signature all match.
  Changing ANY field must cause verify() to return False.
  Two test suites are included:
    - fixture-based: uses the canonical validator_keys.json key pairs
    - generated-key: uses freshly generated key pairs for edge-case coverage
"""

import json
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from src.crypto import hash_bytes, sign, verify, SIGNATURE_LEN

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

FIXTURE_PATH = Path(__file__).resolve().parents[1] / "config" / "validator_keys.json"

DOMAIN = "TX:lab01"


def hx(h: str) -> bytes:
    return bytes.fromhex(h)


def make_key_pair() -> tuple[bytes, bytes]:
    """Return (privkey_seed: 32 bytes, pubkey: 32 bytes)."""
    sk = Ed25519PrivateKey.generate()
    privkey = sk.private_bytes_raw()
    pubkey = sk.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    return privkey, pubkey


@pytest.fixture(scope="session")
def fixture():
    with open(FIXTURE_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


# ===========================================================================
# T1-05: hash_bytes()
# ===========================================================================

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
    assert hash_bytes(data) == hash_bytes(data)


@pytest.mark.hash
def test_hash_bytes_changes_for_different_input():
    assert hash_bytes(b"transaction-1") != hash_bytes(b"transaction-2")


@pytest.mark.hash
def test_hash_bytes_rejects_string():
    with pytest.raises(TypeError):
        hash_bytes("hello")


@pytest.mark.hash
def test_hash_bytes_rejects_integer():
    with pytest.raises(TypeError):
        hash_bytes(123)


# ===========================================================================
# T1-08: sign() / verify() — fixture-based (uses validator_keys.json)
# ===========================================================================

@pytest.mark.sign_verify
def test_sign_verify_success(fixture):
    """Correct key + correct domain + correct payload → True."""
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
    """Correct key + wrong domain → False."""
    chain_id = fixture["chain_id"]
    validator = fixture["validator_keys"][0]
    sk = hx(validator["private_key_hex"])
    pk = hx(validator["public_key_hex"])

    payload = b"canonical-payload"
    signature = sign(sk, f"VOTE:{chain_id}", payload)

    assert verify(pk, f"HEADER:{chain_id}", payload, signature) is False


@pytest.mark.sign_verify
def test_verify_fail_wrong_key(fixture):
    """Wrong public key → False."""
    chain_id = fixture["chain_id"]
    signer = fixture["validator_keys"][0]
    other = fixture["validator_keys"][1]

    sk = hx(signer["private_key_hex"])
    wrong_pk = hx(other["public_key_hex"])

    payload = b"canonical-payload"
    domain = f"VOTE:{chain_id}"

    signature = sign(sk, domain, payload)
    assert verify(wrong_pk, domain, payload, signature) is False


@pytest.mark.sign_verify
def test_verify_fail_wrong_payload(fixture):
    """Modified payload → False."""
    chain_id = fixture["chain_id"]
    validator = fixture["validator_keys"][0]
    sk = hx(validator["private_key_hex"])
    pk = hx(validator["public_key_hex"])

    domain = f"VOTE:{chain_id}"
    original_payload = b"height=1|round=0|phase=PREVOTE"
    tampered_payload = b"height=1|round=0|phase=PRECOMMIT"

    signature = sign(sk, domain, original_payload)
    assert verify(pk, domain, tampered_payload, signature) is False


# ===========================================================================
# T1-08: sign() / verify() — generated-key (edge case coverage)
# ===========================================================================

@pytest.mark.sign_verify
def test_valid_signature():
    """sign + verify with correct domain, pubkey, payload → True."""
    privkey, pubkey = make_key_pair()
    sig = sign(privkey, DOMAIN, b"hello blockchain")
    assert verify(pubkey, DOMAIN, b"hello blockchain", sig) is True


@pytest.mark.sign_verify
def test_wrong_domain():
    """verify with a different domain string → False."""
    privkey, pubkey = make_key_pair()
    sig = sign(privkey, DOMAIN, b"some payload")
    assert verify(pubkey, "WRONG_DOMAIN", b"some payload", sig) is False


@pytest.mark.sign_verify
def test_wrong_pubkey():
    """verify with another key pair's public key → False."""
    privkey, pubkey = make_key_pair()
    _, other_pubkey = make_key_pair()
    sig = sign(privkey, DOMAIN, b"some payload")
    assert verify(other_pubkey, DOMAIN, b"some payload", sig) is False


@pytest.mark.sign_verify
def test_wrong_payload():
    """verify with payload mutated by 1 byte → False."""
    privkey, pubkey = make_key_pair()
    payload = b"original payload"
    sig = sign(privkey, DOMAIN, payload)
    tampered = payload[:-1] + bytes([payload[-1] ^ 0xFF])
    assert verify(pubkey, DOMAIN, tampered, sig) is False


@pytest.mark.sign_verify
def test_tampered_signature():
    """verify with 1 bit flipped in the signature → False."""
    privkey, pubkey = make_key_pair()
    sig = sign(privkey, DOMAIN, b"valid payload")
    tampered_sig = sig[:-1] + bytes([sig[-1] ^ 0x01])
    assert verify(pubkey, DOMAIN, b"valid payload", tampered_sig) is False


@pytest.mark.sign_verify
def test_different_domains_dont_cross_verify():
    """Signature made under domain A must not verify under domain B."""
    privkey, pubkey = make_key_pair()
    sig_a = sign(privkey, "DOMAIN_A", b"cross-domain test")
    assert verify(pubkey, "DOMAIN_B", b"cross-domain test", sig_a) is False


@pytest.mark.sign_verify
def test_empty_payload():
    """sign/verify with an empty payload → True (edge case)."""
    privkey, pubkey = make_key_pair()
    sig = sign(privkey, DOMAIN, b"")
    assert verify(pubkey, DOMAIN, b"", sig) is True


@pytest.mark.sign_verify
def test_malformed_pubkey_wrong_length():
    """pubkey not exactly 32 bytes → verify returns False."""
    privkey, pubkey = make_key_pair()
    sig = sign(privkey, DOMAIN, b"some payload")

    assert verify(pubkey[:31], DOMAIN, b"some payload", sig) is False   # 31 bytes
    assert verify(pubkey + b"\x00", DOMAIN, b"some payload", sig) is False  # 33 bytes
    assert verify(b"", DOMAIN, b"some payload", sig) is False            # 0 bytes


@pytest.mark.sign_verify
def test_malformed_signature_wrong_length():
    """signature not exactly 64 bytes → verify returns False."""
    privkey, pubkey = make_key_pair()
    sig = sign(privkey, DOMAIN, b"some payload")

    assert verify(pubkey, DOMAIN, b"some payload", sig[:63]) is False    # 63 bytes
    assert verify(pubkey, DOMAIN, b"some payload", sig + b"\x00") is False  # 65 bytes
    assert verify(pubkey, DOMAIN, b"some payload", b"") is False          # 0 bytes


@pytest.mark.sign_verify
def test_multiple_domains():
    """TX:lab01, PREVOTE, PRECOMMIT are fully independent domains."""
    privkey, pubkey = make_key_pair()
    payload = b"consensus vote payload"
    domains = ["TX:lab01", "PREVOTE", "PRECOMMIT"]

    for signing_domain in domains:
        sig = sign(privkey, signing_domain, payload)
        for verifying_domain in domains:
            result = verify(pubkey, verifying_domain, payload, sig)
            if signing_domain == verifying_domain:
                assert result is True, (
                    f"Expected True: signed and verified under same domain '{signing_domain}'"
                )
            else:
                assert result is False, (
                    f"Expected False: signed under '{signing_domain}', "
                    f"verified under '{verifying_domain}'"
                )
