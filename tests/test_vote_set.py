"""
Tests for VoteSet — covers T2-07, T2-08, T2-09, T2-10.

T2-07: storage by (height, round, phase, validator_pubkey)
T2-08: duplicate detection (ignored) and equivocation detection (logged, first kept)
T2-09: has_quorum() — only True when >= 2f+1 distinct non-NIL validators
T2-10: full unit-test coverage for the above
"""

import pytest

from src.vote import Vote
from src.vote_set import AddResult, EquivocationRecord, VoteOutcome, VoteSet


# ── helpers ───────────────────────────────────────────────────────────────────

def make_vote(
    *,
    height: int = 1,
    round: int = 0,
    phase: str = "PREVOTE",
    block_hash: bytes | None = b"\xaa" * 32,
    validator_index: int = 0,
) -> Vote:
    """Create a syntactically valid Vote (signature is a dummy placeholder)."""
    pubkey = bytes([validator_index + 1]) * 32
    sig = bytes([validator_index + 0x10]) * 64
    return Vote(
        chain_id="test-chain",
        height=height,
        round=round,
        phase=phase,
        block_hash_or_nil=block_hash,
        validator_pubkey=pubkey,
        signature=sig,
    )


def make_validator_set(n: int) -> list[bytes]:
    """Return n distinct 32-byte public keys."""
    return [bytes([i + 1]) * 32 for i in range(n)]


# ── T2-07: basic storage ──────────────────────────────────────────────────────

class TestVoteSetStorage:
    def test_add_and_get_single_vote(self):
        vs = VoteSet()
        v = make_vote(validator_index=0)
        result = vs.add(v)

        assert result.outcome == VoteOutcome.ACCEPTED
        assert result.stored_vote == v
        assert vs.get(1, 0, "PREVOTE", v.validator_pubkey) == v
        assert len(vs) == 1

    def test_get_missing_returns_none(self):
        vs = VoteSet()
        assert vs.get(1, 0, "PREVOTE", b"\x01" * 32) is None

    def test_votes_returns_all_for_slot(self):
        vs = VoteSet()
        v0 = make_vote(validator_index=0)
        v1 = make_vote(validator_index=1)
        v2 = make_vote(validator_index=2, height=2)  # different height — excluded

        vs.add(v0)
        vs.add(v1)
        vs.add(v2)

        slot_votes = vs.votes(1, 0, "PREVOTE")
        assert len(slot_votes) == 2
        assert v0 in slot_votes
        assert v1 in slot_votes
        assert v2 not in slot_votes

    def test_votes_empty_slot_returns_empty_list(self):
        vs = VoteSet()
        assert vs.votes(99, 0, "PREVOTE") == []

    def test_len_counts_accepted_votes_only(self):
        vs = VoteSet()
        vs.add(make_vote(validator_index=0))
        vs.add(make_vote(validator_index=1))
        assert len(vs) == 2

    def test_votes_different_phases_are_independent(self):
        vs = VoteSet()
        prevote = make_vote(phase="PREVOTE", validator_index=0)
        precommit = make_vote(phase="PRECOMMIT", validator_index=0)
        vs.add(prevote)
        vs.add(precommit)

        assert len(vs.votes(1, 0, "PREVOTE")) == 1
        assert len(vs.votes(1, 0, "PRECOMMIT")) == 1

    def test_votes_different_rounds_are_independent(self):
        vs = VoteSet()
        r0 = make_vote(round=0, validator_index=0)
        r1 = make_vote(round=1, validator_index=0)
        vs.add(r0)
        vs.add(r1)

        assert len(vs.votes(1, 0, "PREVOTE")) == 1
        assert len(vs.votes(1, 1, "PREVOTE")) == 1


# ── T2-08: duplicate & equivocation detection ─────────────────────────────────

class TestDuplicateDetection:
    def test_exact_duplicate_is_ignored(self):
        vs = VoteSet()
        v = make_vote(validator_index=0, block_hash=b"\xaa" * 32)
        dup = make_vote(validator_index=0, block_hash=b"\xaa" * 32)

        first = vs.add(v)
        second = vs.add(dup)

        assert first.outcome == VoteOutcome.ACCEPTED
        assert second.outcome == VoteOutcome.DUPLICATE_IGNORED
        assert second.stored_vote == v   # original kept
        assert second.equivocation is None
        assert len(vs) == 1
        assert vs.equivocations() == []

    def test_nil_vote_duplicate_is_ignored(self):
        vs = VoteSet()
        v = make_vote(validator_index=0, block_hash=None)
        vs.add(v)
        result = vs.add(make_vote(validator_index=0, block_hash=None))

        assert result.outcome == VoteOutcome.DUPLICATE_IGNORED
        assert len(vs) == 1

    def test_duplicate_does_not_increment_count(self):
        vs = VoteSet()
        v = make_vote(validator_index=0)
        vs.add(v)
        for _ in range(5):
            vs.add(v)
        assert len(vs) == 1


class TestEquivocationDetection:
    def test_equivocation_detected_first_vote_kept(self):
        vs = VoteSet()
        first = make_vote(validator_index=0, block_hash=b"\xaa" * 32)
        conflict = Vote(
            chain_id="test-chain",
            height=1,
            round=0,
            phase="PREVOTE",
            block_hash_or_nil=b"\xbb" * 32,   # different block
            validator_pubkey=first.validator_pubkey,
            signature=b"\xff" * 64,
        )

        r1 = vs.add(first)
        r2 = vs.add(conflict)

        assert r1.outcome == VoteOutcome.ACCEPTED
        assert r2.outcome == VoteOutcome.EQUIVOCATION_DETECTED
        # The first vote is retained
        assert r2.stored_vote == first
        assert vs.get(1, 0, "PREVOTE", first.validator_pubkey) == first
        assert len(vs) == 1  # conflicting vote did NOT add a second entry

    def test_equivocation_evidence_is_recorded(self):
        vs = VoteSet()
        first = make_vote(validator_index=0, block_hash=b"\xaa" * 32)
        conflict = Vote(
            chain_id="test-chain",
            height=1,
            round=0,
            phase="PREVOTE",
            block_hash_or_nil=b"\xbb" * 32,
            validator_pubkey=first.validator_pubkey,
            signature=b"\xff" * 64,
        )
        vs.add(first)
        result = vs.add(conflict)

        records = vs.equivocations()
        assert len(records) == 1
        assert records[0].first_vote == first
        assert records[0].conflicting_vote == conflict
        assert result.equivocation is not None
        assert result.equivocation == records[0]

    def test_has_equivocated_true_after_conflict(self):
        vs = VoteSet()
        first = make_vote(validator_index=0, block_hash=b"\xaa" * 32)
        conflict = Vote(
            chain_id="test-chain",
            height=1,
            round=0,
            phase="PREVOTE",
            block_hash_or_nil=b"\xcc" * 32,
            validator_pubkey=first.validator_pubkey,
            signature=b"\xfe" * 64,
        )
        vs.add(first)
        vs.add(conflict)

        assert vs.has_equivocated(1, 0, "PREVOTE", first.validator_pubkey)

    def test_has_equivocated_false_for_clean_validator(self):
        vs = VoteSet()
        vs.add(make_vote(validator_index=0))
        assert not vs.has_equivocated(1, 0, "PREVOTE", make_vote(validator_index=0).validator_pubkey)

    def test_equivocation_does_not_count_toward_quorum(self):
        """The conflicting vote must NOT inflate the quorum count."""
        # n=4 → f=1 → threshold=3
        n = 4
        vs = VoteSet()
        # validator 0 equivocates
        first = make_vote(validator_index=0, block_hash=b"\xaa" * 32)
        conflict = Vote(
            chain_id="test-chain",
            height=1, round=0, phase="PREVOTE",
            block_hash_or_nil=b"\xbb" * 32,
            validator_pubkey=first.validator_pubkey,
            signature=b"\xff" * 64,
        )
        vs.add(first)
        vs.add(conflict)
        # only 1 validator so far — no quorum
        assert not vs.has_quorum(1, 0, "PREVOTE", n)
        # Add 2 more distinct validators
        vs.add(make_vote(validator_index=1))
        vs.add(make_vote(validator_index=2))
        # Now 3 distinct validators have voted — threshold reached
        assert vs.has_quorum(1, 0, "PREVOTE", n)

    def test_non_member_vote_raises_type_error(self):
        vs = VoteSet()
        with pytest.raises(TypeError):
            vs.add("not-a-vote")  # type: ignore[arg-type]


# ── T2-09 / T2-10: has_quorum ─────────────────────────────────────────────────

class TestHasQuorum:
    """
    Quorum formula:  threshold = 2f + 1,  f = (n-1) // 3

    n=1  → f=0 → threshold=1
    n=4  → f=1 → threshold=3
    n=7  → f=2 → threshold=5
    n=8  → f=2 → threshold=5  (8 validators, can tolerate 2 faults)
    """

    # ── basic threshold arithmetic ────────────────────────────────────────────

    def test_quorum_n1_threshold1(self):
        vs = VoteSet()
        vs.add(make_vote(validator_index=0))
        assert vs.has_quorum(1, 0, "PREVOTE", n=1)

    def test_quorum_n4_threshold3_not_met_with_2(self):
        vs = VoteSet()
        vs.add(make_vote(validator_index=0))
        vs.add(make_vote(validator_index=1))
        assert not vs.has_quorum(1, 0, "PREVOTE", n=4)

    def test_quorum_n4_threshold3_met_with_3(self):
        vs = VoteSet()
        for i in range(3):
            vs.add(make_vote(validator_index=i))
        assert vs.has_quorum(1, 0, "PREVOTE", n=4)

    def test_quorum_n7_threshold5(self):
        vs = VoteSet()
        for i in range(4):
            vs.add(make_vote(validator_index=i))
        assert not vs.has_quorum(1, 0, "PREVOTE", n=7)
        vs.add(make_vote(validator_index=4))
        assert vs.has_quorum(1, 0, "PREVOTE", n=7)

    def test_quorum_n8_threshold5(self):
        vs = VoteSet()
        for i in range(5):
            vs.add(make_vote(validator_index=i))
        assert vs.has_quorum(1, 0, "PREVOTE", n=8)

    # ── NIL votes do not count ─────────────────────────────────────────────────

    def test_nil_votes_do_not_count_toward_quorum(self):
        # n=4 → threshold=3; all 4 validators vote NIL → still no quorum
        vs = VoteSet()
        for i in range(4):
            vs.add(make_vote(validator_index=i, block_hash=None))
        assert not vs.has_quorum(1, 0, "PREVOTE", n=4)

    def test_mix_nil_and_non_nil(self):
        # n=4 → threshold=3; 2 vote NIL, 2 vote non-NIL → no quorum
        vs = VoteSet()
        for i in range(2):
            vs.add(make_vote(validator_index=i, block_hash=None))
        for i in range(2, 4):
            vs.add(make_vote(validator_index=i, block_hash=b"\xaa" * 32))
        assert not vs.has_quorum(1, 0, "PREVOTE", n=4)

    # ── distinct validators only ───────────────────────────────────────────────

    def test_same_validator_counted_once_despite_duplicates(self):
        # n=4 → threshold=3; same validator sends vote 3 times → still 1 distinct
        vs = VoteSet()
        v = make_vote(validator_index=0)
        for _ in range(3):
            vs.add(v)
        assert not vs.has_quorum(1, 0, "PREVOTE", n=4)

    # ── block_hash filter ─────────────────────────────────────────────────────

    def test_quorum_for_specific_block(self):
        # n=4 → threshold=3
        BLOCK_A = b"\xaa" * 32
        BLOCK_B = b"\xbb" * 32
        vs = VoteSet()
        # 2 vote for A, 2 vote for B → neither has quorum alone
        for i in range(2):
            vs.add(make_vote(validator_index=i, block_hash=BLOCK_A))
        for i in range(2, 4):
            vs.add(make_vote(validator_index=i, block_hash=BLOCK_B))

        assert not vs.has_quorum(1, 0, "PREVOTE", n=4, block_hash=BLOCK_A)
        assert not vs.has_quorum(1, 0, "PREVOTE", n=4, block_hash=BLOCK_B)

    def test_quorum_for_specific_block_met(self):
        # n=4 → threshold=3; all 3 vote for A
        BLOCK_A = b"\xaa" * 32
        vs = VoteSet()
        for i in range(3):
            vs.add(make_vote(validator_index=i, block_hash=BLOCK_A))
        assert vs.has_quorum(1, 0, "PREVOTE", n=4, block_hash=BLOCK_A)

    def test_quorum_without_filter_counts_all_non_nil(self):
        # No block_hash filter — counts any non-NIL vote
        vs = VoteSet()
        vs.add(make_vote(validator_index=0, block_hash=b"\xaa" * 32))
        vs.add(make_vote(validator_index=1, block_hash=b"\xbb" * 32))
        vs.add(make_vote(validator_index=2, block_hash=b"\xcc" * 32))
        assert vs.has_quorum(1, 0, "PREVOTE", n=4)

    # ── slot isolation ─────────────────────────────────────────────────────────

    def test_quorum_only_counts_matching_slot(self):
        # Votes in other slots must not bleed into the queried slot
        vs = VoteSet()
        # height=1, round=0, PREVOTE — 3 votes (quorum if n=4)
        for i in range(3):
            vs.add(make_vote(validator_index=i, height=1, round=0, phase="PREVOTE"))
        # height=2, round=0, PREVOTE — 3 more votes (different height)
        for i in range(3):
            vs.add(make_vote(validator_index=i, height=2, round=0, phase="PREVOTE"))

        assert vs.has_quorum(1, 0, "PREVOTE", n=4)
        assert vs.has_quorum(2, 0, "PREVOTE", n=4)
        # height=3 has no votes — no quorum
        assert not vs.has_quorum(3, 0, "PREVOTE", n=4)

    def test_quorum_phase_isolation(self):
        vs = VoteSet()
        for i in range(3):
            vs.add(make_vote(validator_index=i, phase="PREVOTE"))
        # PRECOMMIT has no votes
        assert not vs.has_quorum(1, 0, "PRECOMMIT", n=4)

    # ── edge cases ────────────────────────────────────────────────────────────

    def test_empty_voteset_no_quorum(self):
        vs = VoteSet()
        assert not vs.has_quorum(1, 0, "PREVOTE", n=4)

    def test_invalid_n_raises_value_error(self):
        vs = VoteSet()
        with pytest.raises(ValueError, match="n must be >= 1"):
            vs.has_quorum(1, 0, "PREVOTE", n=0)

    def test_quorum_exactly_at_threshold(self):
        # n=7 → f=2 → threshold=5; exactly 5 validators vote
        vs = VoteSet()
        for i in range(5):
            vs.add(make_vote(validator_index=i))
        assert vs.has_quorum(1, 0, "PREVOTE", n=7)

    def test_quorum_one_below_threshold(self):
        # n=7 → threshold=5; only 4 vote
        vs = VoteSet()
        for i in range(4):
            vs.add(make_vote(validator_index=i))
        assert not vs.has_quorum(1, 0, "PREVOTE", n=7)
