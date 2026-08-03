import pytest

from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
)
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    PublicFormat,
)

from src.crypto import hash_bytes, sign
from src.encoding import encode_bytes
from src.vote import PHASE_PRECOMMIT, PHASE_PREVOTE, Vote


CHAIN_ID = "test-chain"
HEIGHT = 10
ROUND = 2
BLOCK_HASH = hash_bytes(b"candidate-block")


def make_key_pair() -> tuple[bytes, bytes]:
    """
    Create an Ed25519 key pair.

    Returns:
        private_key_seed: 32 bytes
        public_key: 32 bytes
    """

    private_key_object = Ed25519PrivateKey.generate()

    private_key_seed = private_key_object.private_bytes_raw()

    public_key = (
        private_key_object.public_key()
        .public_bytes(
            Encoding.Raw,
            PublicFormat.Raw,
        )
    )

    return private_key_seed, public_key


def make_valid_vote(
    private_key: bytes,
    public_key: bytes,
    chain_id: str = CHAIN_ID,
    height: int = HEIGHT,
    round: int = ROUND,
    phase: str = PHASE_PREVOTE,
    block_hash_or_nil: bytes | None = BLOCK_HASH,
) -> Vote:
    """
    Create a correctly signed vote.
    """

    return Vote.create_signed(
        chain_id=chain_id,
        height=height,
        round=round,
        phase=phase,
        block_hash_or_nil=block_hash_or_nil,
        validator_pubkey=public_key,
        validator_privkey=private_key,
    )


def validate_vote(
    vote: Vote,
    validator_set: set,
    expected_height: int = HEIGHT,
    expected_round: int = ROUND,
    expected_phase: str = PHASE_PREVOTE,
) -> None:
    """
    Helper to validate a vote against the standard test parameters.
    """

    vote.validate(
        expected_chain_id=CHAIN_ID,
        validator_set=validator_set,
        expected_height=expected_height,
        expected_round=expected_round,
        expected_phase=expected_phase,
    )


# ============================================================
# Valid vote
# ============================================================

def test_valid_vote():
    private_key, public_key = make_key_pair()

    vote = make_valid_vote(private_key, public_key)

    # Test passes if no exception is raised.
    validate_vote(vote, {public_key})


def test_valid_vote_with_nil_block_hash():
    private_key, public_key = make_key_pair()

    vote = make_valid_vote(
        private_key,
        public_key,
        block_hash_or_nil=None,
    )

    validate_vote(vote, {public_key})


# ============================================================
# Canonical encoding
# ============================================================

def test_unsigned_bytes_excludes_signature():
    private_key, public_key = make_key_pair()

    vote = make_valid_vote(private_key, public_key)

    assert vote.signature not in vote.unsigned_bytes()


def test_signed_bytes_includes_signature():
    private_key, public_key = make_key_pair()

    vote = make_valid_vote(private_key, public_key)

    assert (
        vote.signed_bytes()
        == vote.unsigned_bytes() + encode_bytes(vote.signature)
    )


def test_signed_bytes_change_when_signature_changes():
    private_key, public_key = make_key_pair()

    vote = make_valid_vote(private_key, public_key)

    modified_signature = (
        vote.signature[:-1]
        + bytes([vote.signature[-1] ^ 1])
    )

    modified_vote = Vote(
        chain_id=vote.chain_id,
        height=vote.height,
        round=vote.round,
        phase=vote.phase,
        block_hash_or_nil=vote.block_hash_or_nil,
        validator_pubkey=vote.validator_pubkey,
        signature=modified_signature,
    )

    assert vote.signed_bytes() != modified_vote.signed_bytes()


# ============================================================
# chain_id guard
# ============================================================

def test_rejects_wrong_chain_id():
    private_key, public_key = make_key_pair()

    vote = make_valid_vote(
        private_key,
        public_key,
        chain_id="another-chain",
    )

    with pytest.raises(ValueError, match="INVALID_CHAIN_ID"):
        validate_vote(vote, {public_key})


# ============================================================
# member check
# ============================================================

def test_rejects_non_member_validator():
    private_key, public_key = make_key_pair()
    _, other_public_key = make_key_pair()

    vote = make_valid_vote(private_key, public_key)

    with pytest.raises(ValueError, match="NOT_A_VALIDATOR"):
        validate_vote(vote, {other_public_key})


# ============================================================
# VOTE domain signature
# ============================================================

def test_rejects_invalid_signature():
    private_key, public_key = make_key_pair()

    vote = make_valid_vote(private_key, public_key)

    tampered_vote = Vote(
        chain_id=vote.chain_id,
        height=vote.height,
        round=vote.round,
        phase=vote.phase,
        block_hash_or_nil=vote.block_hash_or_nil,
        validator_pubkey=vote.validator_pubkey,
        signature=(
            vote.signature[:-1]
            + bytes([vote.signature[-1] ^ 1])
        ),
    )

    with pytest.raises(ValueError, match="INVALID_SIGNATURE"):
        validate_vote(tampered_vote, {public_key})


def test_rejects_signature_from_wrong_domain():
    private_key, public_key = make_key_pair()

    unsigned_vote = Vote(
        chain_id=CHAIN_ID,
        height=HEIGHT,
        round=ROUND,
        phase=PHASE_PREVOTE,
        block_hash_or_nil=BLOCK_HASH,
        validator_pubkey=public_key,
        signature=b"",
    )

    # Sign under the wrong domain (TX instead of VOTE).
    wrong_domain_signature = sign(
        private_key,
        f"TX:{CHAIN_ID}",
        unsigned_vote.unsigned_bytes(),
    )

    vote = Vote(
        chain_id=CHAIN_ID,
        height=HEIGHT,
        round=ROUND,
        phase=PHASE_PREVOTE,
        block_hash_or_nil=BLOCK_HASH,
        validator_pubkey=public_key,
        signature=wrong_domain_signature,
    )

    with pytest.raises(ValueError, match="INVALID_SIGNATURE"):
        validate_vote(vote, {public_key})


def test_rejects_signature_reused_across_votes():
    """A signature valid for one (height, round, phase) must not validate
    for a different tuple -- the signed payload must bind to all fields."""

    private_key, public_key = make_key_pair()

    vote = make_valid_vote(private_key, public_key, round=ROUND)

    replayed_vote = Vote(
        chain_id=vote.chain_id,
        height=vote.height,
        round=ROUND + 1,
        phase=vote.phase,
        block_hash_or_nil=vote.block_hash_or_nil,
        validator_pubkey=vote.validator_pubkey,
        signature=vote.signature,
    )

    with pytest.raises(ValueError, match="INVALID_SIGNATURE"):
        validate_vote(
            replayed_vote,
            {public_key},
            expected_round=ROUND + 1,
        )


# ============================================================
# height / round / phase match
# ============================================================

def test_rejects_wrong_height():
    private_key, public_key = make_key_pair()

    vote = make_valid_vote(private_key, public_key)

    with pytest.raises(ValueError, match="INVALID_HEIGHT"):
        validate_vote(vote, {public_key}, expected_height=HEIGHT + 1)


def test_rejects_wrong_round():
    private_key, public_key = make_key_pair()

    vote = make_valid_vote(private_key, public_key)

    with pytest.raises(ValueError, match="INVALID_ROUND"):
        validate_vote(vote, {public_key}, expected_round=ROUND + 1)


def test_rejects_wrong_phase():
    private_key, public_key = make_key_pair()

    vote = make_valid_vote(private_key, public_key, phase=PHASE_PREVOTE)

    with pytest.raises(ValueError, match="INVALID_PHASE"):
        validate_vote(
            vote,
            {public_key},
            expected_phase=PHASE_PRECOMMIT,
        )


# ============================================================
# Guard ordering (first failing guard wins)
# ============================================================

def test_chain_id_guard_runs_before_member_check():
    private_key, public_key = make_key_pair()

    vote = make_valid_vote(
        private_key,
        public_key,
        chain_id="another-chain",
    )

    # public_key is not even in the validator set either, but chain_id
    # should be reported first.
    with pytest.raises(ValueError, match="INVALID_CHAIN_ID"):
        validate_vote(vote, set())


def test_member_check_runs_before_signature_check():
    private_key, public_key = make_key_pair()

    vote = make_valid_vote(private_key, public_key)

    tampered_vote = Vote(
        chain_id=vote.chain_id,
        height=vote.height,
        round=vote.round,
        phase=vote.phase,
        block_hash_or_nil=vote.block_hash_or_nil,
        validator_pubkey=vote.validator_pubkey,
        signature=(
            vote.signature[:-1]
            + bytes([vote.signature[-1] ^ 1])
        ),
    )

    # Not a member AND bad signature -- membership should be reported first.
    with pytest.raises(ValueError, match="NOT_A_VALIDATOR"):
        validate_vote(tampered_vote, set())
