"""Focused tests for the F-35 and F-33 consensus safety guards."""

from __future__ import annotations

import pytest

from src.consensus import ConsensusState, VoteSigningGuard
from src.identity import ValidatorIdentity, load_validator_keys
from src.vote import PHASE_PRECOMMIT, PHASE_PREVOTE, Vote
from src.vote_set import VoteSet


CHAIN_ID = "lab01-testnet"
HEIGHT = 7
CANDIDATE = b"c" * 32
OTHER_BLOCK = b"o" * 32
LOCKED_BLOCK = b"l" * 32


@pytest.fixture(scope="module")
def validators() -> list[ValidatorIdentity]:
    return load_validator_keys()


def _evidence(
    validators: list[ValidatorIdentity],
    *,
    height: int = HEIGHT,
    round: int = 3,
    phase: str = PHASE_PREVOTE,
    block_hash: bytes = CANDIDATE,
    indices: tuple[int, ...] = (0, 1, 2),
) -> VoteSet:
    votes = VoteSet()
    validator_set = tuple(validator.public_key for validator in validators)
    for index in indices:
        identity = validators[index]
        vote = Vote.create_signed(
            chain_id=CHAIN_ID,
            height=height,
            round=round,
            phase=phase,
            block_hash_or_nil=block_hash,
            validator_pubkey=identity.public_key,
            validator_privkey=identity.private_key,
        )
        # Evidence fixtures exercise the real signature path and satisfy the
        # same acceptance guards that precede insertion in production.
        vote.validate(
            expected_chain_id=CHAIN_ID,
            validator_set=validator_set,
            expected_height=height,
            expected_round=round,
            expected_phase=phase,
        )
        votes.add(vote)
    return votes


def _locked_state(*, round: int = 4, locked_round: int = 1) -> ConsensusState:
    return ConsensusState(
        height=HEIGHT,
        round=round,
        locked_block_hash=LOCKED_BLOCK,
        locked_round=locked_round,
    )


def _guard(
    validators: list[ValidatorIdentity], index: int = 0
) -> VoteSigningGuard:
    identity = validators[index]
    return VoteSigningGuard(
        chain_id=CHAIN_ID,
        validator_pubkey=identity.public_key,
        validator_privkey=identity.private_key,
        validator_set=[validator.public_key for validator in validators],
    )


# ---------------------------------------------------------------------------
# F-35: lock-aware PREVOTE selection
# ---------------------------------------------------------------------------


def test_unlocked_validator_prevotes_fully_valid_candidate():
    state = ConsensusState(height=HEIGHT, round=2)

    assert state.choose_prevote(CANDIDATE, proposal_is_valid=True, n=4) == CANDIDATE


def test_matching_lock_prevotes_candidate_without_evidence():
    state = ConsensusState(
        height=HEIGHT,
        round=2,
        locked_block_hash=CANDIDATE,
        locked_round=1,
    )

    assert state.choose_prevote(CANDIDATE, proposal_is_valid=True, n=4) == CANDIDATE


def test_different_lock_without_evidence_prevotes_nil():
    state = _locked_state()

    assert state.choose_prevote(CANDIDATE, proposal_is_valid=True, n=4) is None


def test_different_lock_with_strictly_later_exact_quorum_prevotes_candidate(validators):
    state = _locked_state(locked_round=1)
    evidence = _evidence(validators, round=3)

    assert state.choose_prevote(
        CANDIDATE,
        proposal_is_valid=True,
        n=4,
        evidence_round=3,
        prevote_evidence=evidence,
    ) == CANDIDATE


@pytest.mark.parametrize("evidence_round", [0, 1, 2])
def test_same_or_earlier_evidence_round_never_overrides_lock(validators, evidence_round):
    state = _locked_state(round=4, locked_round=2)
    evidence = _evidence(validators, round=evidence_round)

    assert state.choose_prevote(
        CANDIDATE,
        proposal_is_valid=True,
        n=4,
        evidence_round=evidence_round,
        prevote_evidence=evidence,
    ) is None


def test_future_round_evidence_never_overrides_lock(validators):
    state = _locked_state(round=4, locked_round=1)
    evidence = _evidence(validators, round=5)

    assert state.choose_prevote(
        CANDIDATE,
        proposal_is_valid=True,
        n=4,
        evidence_round=5,
        prevote_evidence=evidence,
    ) is None


def test_quorum_for_wrong_hash_never_overrides_lock(validators):
    state = _locked_state()
    evidence = _evidence(validators, round=3, block_hash=OTHER_BLOCK)

    assert state.choose_prevote(
        CANDIDATE,
        proposal_is_valid=True,
        n=4,
        evidence_round=3,
        prevote_evidence=evidence,
    ) is None


def test_quorum_for_wrong_height_never_overrides_lock(validators):
    state = _locked_state()
    evidence = _evidence(validators, height=HEIGHT + 1, round=3)

    assert state.choose_prevote(
        CANDIDATE,
        proposal_is_valid=True,
        n=4,
        evidence_round=3,
        prevote_evidence=evidence,
    ) is None


def test_quorum_for_wrong_phase_never_overrides_lock(validators):
    state = _locked_state()
    evidence = _evidence(validators, round=3, phase=PHASE_PRECOMMIT)

    assert state.choose_prevote(
        CANDIDATE,
        proposal_is_valid=True,
        n=4,
        evidence_round=3,
        prevote_evidence=evidence,
    ) is None


@pytest.mark.parametrize(
    "state",
    [
        ConsensusState(height=HEIGHT, round=4),
        _locked_state(round=4, locked_round=1),
    ],
)
def test_invalid_proposal_always_prevotes_nil(state, validators):
    evidence = _evidence(validators, round=3)

    assert state.choose_prevote(
        CANDIDATE,
        proposal_is_valid=False,
        n=4,
        evidence_round=3,
        prevote_evidence=evidence,
    ) is None


def test_evidence_requires_exact_distinct_validator_quorum(validators):
    state = _locked_state()
    below_quorum = _evidence(validators, round=3, indices=(0, 1))

    assert state.choose_prevote(
        CANDIDATE,
        proposal_is_valid=True,
        n=4,
        evidence_round=3,
        prevote_evidence=below_quorum,
    ) is None

    # n=4 -> f=1 -> quorum=3.  The exact third distinct validator enables it.
    identity = validators[2]
    below_quorum.add(
        Vote.create_signed(
            chain_id=CHAIN_ID,
            height=HEIGHT,
            round=3,
            phase=PHASE_PREVOTE,
            block_hash_or_nil=CANDIDATE,
            validator_pubkey=identity.public_key,
            validator_privkey=identity.private_key,
        )
    )
    assert state.choose_prevote(
        CANDIDATE,
        proposal_is_valid=True,
        n=4,
        evidence_round=3,
        prevote_evidence=below_quorum,
    ) == CANDIDATE


def test_split_votes_do_not_form_quorum_for_candidate(validators):
    state = _locked_state()
    split = _evidence(validators, round=3, indices=(0, 1))
    identity = validators[2]
    split.add(
        Vote.create_signed(
            chain_id=CHAIN_ID,
            height=HEIGHT,
            round=3,
            phase=PHASE_PREVOTE,
            block_hash_or_nil=OTHER_BLOCK,
            validator_pubkey=identity.public_key,
            validator_privkey=identity.private_key,
        )
    )

    assert state.choose_prevote(
        CANDIDATE,
        proposal_is_valid=True,
        n=4,
        evidence_round=3,
        prevote_evidence=split,
    ) is None


def test_state_prevotes_are_default_evidence(validators):
    state = _locked_state()
    state.prevotes = _evidence(validators, round=3)

    assert state.choose_prevote(
        CANDIDATE,
        proposal_is_valid=True,
        n=4,
        evidence_round=3,
    ) == CANDIDATE


@pytest.mark.parametrize("bad_hash", [b"short", b"x" * 33, bytearray(32), None])
def test_choose_prevote_rejects_malformed_candidate_hash(bad_hash):
    state = ConsensusState(height=HEIGHT)

    with pytest.raises((TypeError, ValueError), match="INVALID_BLOCK_HASH"):
        state.choose_prevote(bad_hash, proposal_is_valid=True, n=4)  # type: ignore[arg-type]


@pytest.mark.parametrize("bad_n", [0, -1, True, 1.5])
def test_choose_prevote_rejects_invalid_validator_count(bad_n):
    state = ConsensusState(height=HEIGHT)

    with pytest.raises((TypeError, ValueError), match="INVALID_VALIDATOR_COUNT"):
        state.choose_prevote(CANDIDATE, proposal_is_valid=True, n=bad_n)  # type: ignore[arg-type]


def test_consensus_state_rejects_inconsistent_or_future_lock():
    with pytest.raises(ValueError, match="INVALID_LOCK"):
        ConsensusState(height=HEIGHT, locked_block_hash=LOCKED_BLOCK)
    with pytest.raises(ValueError, match="INVALID_LOCK"):
        ConsensusState(height=HEIGHT, locked_round=0)
    with pytest.raises(ValueError, match="INVALID_LOCK"):
        ConsensusState(
            height=HEIGHT,
            round=1,
            locked_block_hash=LOCKED_BLOCK,
            locked_round=2,
        )


# ---------------------------------------------------------------------------
# F-33: one locally signed vote per slot
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("phase", [PHASE_PREVOTE, PHASE_PRECOMMIT])
def test_identical_vote_retry_is_idempotent_for_each_phase(validators, phase):
    guard = _guard(validators)

    original = guard.sign_vote(
        height=HEIGHT,
        round=2,
        phase=phase,
        block_hash_or_nil=CANDIDATE,
    )
    retry = guard.sign_vote(
        height=HEIGHT,
        round=2,
        phase=phase,
        block_hash_or_nil=CANDIDATE,
    )

    assert retry is original
    assert len(guard) == 1
    assert guard.get_signed_vote(height=HEIGHT, round=2, phase=phase) is original


@pytest.mark.parametrize("phase", [PHASE_PREVOTE, PHASE_PRECOMMIT])
def test_conflicting_vote_is_rejected_for_each_phase(validators, phase, monkeypatch):
    guard = _guard(validators)
    original_create_signed = Vote.create_signed
    calls = 0

    def counted_create_signed(**kwargs):
        nonlocal calls
        calls += 1
        return original_create_signed(**kwargs)

    monkeypatch.setattr(Vote, "create_signed", counted_create_signed)
    original = guard.sign_vote(
        height=HEIGHT,
        round=2,
        phase=phase,
        block_hash_or_nil=CANDIDATE,
    )

    with pytest.raises(ValueError, match="CONFLICTING_VOTE"):
        guard.sign_vote(
            height=HEIGHT,
            round=2,
            phase=phase,
            block_hash_or_nil=OTHER_BLOCK,
        )

    assert calls == 1
    assert len(guard) == 1
    assert guard.get_signed_vote(height=HEIGHT, round=2, phase=phase) is original


@pytest.mark.parametrize(
    ("first_hash", "conflicting_hash"),
    [(None, CANDIDATE), (CANDIDATE, None)],
)
def test_nil_and_non_nil_are_conflicting_intents(validators, first_hash, conflicting_hash):
    guard = _guard(validators)
    original = guard.sign_vote(
        height=HEIGHT,
        round=0,
        phase=PHASE_PREVOTE,
        block_hash_or_nil=first_hash,
    )

    with pytest.raises(ValueError, match="CONFLICTING_VOTE"):
        guard.sign_vote(
            height=HEIGHT,
            round=0,
            phase=PHASE_PREVOTE,
            block_hash_or_nil=conflicting_hash,
        )

    assert guard.signed_votes() == (original,)


def test_identical_nil_retry_is_idempotent(validators):
    guard = _guard(validators)
    first = guard.sign_vote(
        height=HEIGHT,
        round=0,
        phase=PHASE_PREVOTE,
        block_hash_or_nil=None,
    )
    second = guard.sign_vote(
        height=HEIGHT,
        round=0,
        phase=PHASE_PREVOTE,
        block_hash_or_nil=None,
    )

    assert second is first
    assert len(guard) == 1


def test_distinct_phases_rounds_and_heights_have_independent_slots(validators):
    guard = _guard(validators)
    votes = [
        guard.sign_vote(
            height=HEIGHT,
            round=0,
            phase=PHASE_PREVOTE,
            block_hash_or_nil=CANDIDATE,
        ),
        guard.sign_vote(
            height=HEIGHT,
            round=0,
            phase=PHASE_PRECOMMIT,
            block_hash_or_nil=CANDIDATE,
        ),
        guard.sign_vote(
            height=HEIGHT,
            round=1,
            phase=PHASE_PREVOTE,
            block_hash_or_nil=OTHER_BLOCK,
        ),
        guard.sign_vote(
            height=HEIGHT + 1,
            round=0,
            phase=PHASE_PREVOTE,
            block_hash_or_nil=None,
        ),
    ]

    assert len(guard) == 4
    assert guard.signed_votes() == tuple(
        sorted(votes, key=lambda vote: (vote.height, vote.round, vote.phase))
    )


def test_signing_failure_leaves_slot_free(validators, monkeypatch):
    guard = _guard(validators)
    original_create_signed = Vote.create_signed
    fail = True

    def flaky_create_signed(**kwargs):
        nonlocal fail
        if fail:
            fail = False
            raise RuntimeError("simulated signing failure")
        return original_create_signed(**kwargs)

    monkeypatch.setattr(Vote, "create_signed", flaky_create_signed)

    with pytest.raises(RuntimeError, match="simulated signing failure"):
        guard.sign_vote(
            height=HEIGHT,
            round=0,
            phase=PHASE_PREVOTE,
            block_hash_or_nil=CANDIDATE,
        )
    assert len(guard) == 0

    vote = guard.sign_vote(
        height=HEIGHT,
        round=0,
        phase=PHASE_PREVOTE,
        block_hash_or_nil=CANDIDATE,
    )
    assert len(guard) == 1
    assert vote.block_hash_or_nil == CANDIDATE


def test_invalid_constructed_vote_leaves_slot_free(validators, monkeypatch):
    guard = _guard(validators)
    identity = validators[0]
    original_create_signed = Vote.create_signed

    invalid_vote = Vote(
        chain_id=CHAIN_ID,
        height=HEIGHT,
        round=0,
        phase=PHASE_PREVOTE,
        block_hash_or_nil=CANDIDATE,
        validator_pubkey=identity.public_key,
        signature=b"bad",
    )
    monkeypatch.setattr(Vote, "create_signed", lambda **_: invalid_vote)
    with pytest.raises(ValueError, match="INVALID_SIGNATURE_LENGTH"):
        guard.sign_vote(
            height=HEIGHT,
            round=0,
            phase=PHASE_PREVOTE,
            block_hash_or_nil=CANDIDATE,
        )
    assert len(guard) == 0

    monkeypatch.setattr(Vote, "create_signed", original_create_signed)
    guard.sign_vote(
        height=HEIGHT,
        round=0,
        phase=PHASE_PREVOTE,
        block_hash_or_nil=CANDIDATE,
    )
    assert len(guard) == 1


@pytest.mark.parametrize(
    ("field", "value", "code"),
    [
        ("height", 0, "INVALID_HEIGHT"),
        ("height", True, "INVALID_HEIGHT"),
        ("round", -1, "INVALID_ROUND"),
        ("round", False, "INVALID_ROUND"),
        ("phase", "PROPOSE", "INVALID_PHASE"),
        ("phase", 1, "INVALID_PHASE"),
        ("block_hash_or_nil", b"short", "INVALID_BLOCK_HASH"),
        ("block_hash_or_nil", bytearray(32), "INVALID_BLOCK_HASH"),
    ],
)
def test_invalid_vote_fields_do_not_consume_slot(validators, field, value, code):
    guard = _guard(validators)
    arguments = {
        "height": HEIGHT,
        "round": 0,
        "phase": PHASE_PREVOTE,
        "block_hash_or_nil": CANDIDATE,
    }
    arguments[field] = value

    with pytest.raises((TypeError, ValueError), match=code):
        guard.sign_vote(**arguments)
    assert len(guard) == 0


def test_guard_rejects_non_member_and_mismatched_key_pair(validators):
    member = validators[0]
    other = validators[1]
    validator_set = [validator.public_key for validator in validators]

    with pytest.raises(ValueError, match="NOT_A_VALIDATOR"):
        VoteSigningGuard(
            chain_id=CHAIN_ID,
            validator_pubkey=b"n" * 32,
            validator_privkey=member.private_key,
            validator_set=validator_set,
        )

    with pytest.raises(ValueError, match="VALIDATOR_KEY_MISMATCH"):
        VoteSigningGuard(
            chain_id=CHAIN_ID,
            validator_pubkey=member.public_key,
            validator_privkey=other.private_key,
            validator_set=validator_set,
        )


def test_vote_signing_is_deterministic(validators):
    first_guard = _guard(validators)
    second_guard = _guard(validators)

    first = first_guard.sign_vote(
        height=HEIGHT,
        round=9,
        phase=PHASE_PRECOMMIT,
        block_hash_or_nil=CANDIDATE,
    )
    second = second_guard.sign_vote(
        height=HEIGHT,
        round=9,
        phase=PHASE_PRECOMMIT,
        block_hash_or_nil=CANDIDATE,
    )

    assert first == second
    assert first.signed_bytes() == second.signed_bytes()
