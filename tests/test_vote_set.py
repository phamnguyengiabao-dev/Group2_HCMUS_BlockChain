 from src.vote import Vote
from src.vote_set import VoteSet, VoteOutcome


def test_add_and_get_vote():
    vote_set = VoteSet()

    vote = Vote(
        chain_id="test-chain",
        height=1,
        round=0,
        phase="PREVOTE",
        block_hash_or_nil=None,
        validator_pubkey=b"\x01" * 32,
        signature=b"\x02" * 64,
    )

    result = vote_set.add(vote)
    assert result.outcome == VoteOutcome.ACCEPTED
    assert result.stored_vote == vote

    fetched = vote_set.get(
        height=1,
        round=0,
        phase="PREVOTE",
        validator_pubkey=b"\x01" * 32,
    )

    assert fetched == vote
    assert len(vote_set) == 1


def test_get_votes_by_height_round_phase():
    vote_set = VoteSet()

    vote_1 = Vote(
        chain_id="test-chain",
        height=1,
        round=0,
        phase="PREVOTE",
        block_hash_or_nil=None,
        validator_pubkey=b"\x01" * 32,
        signature=b"\x02" * 64,
    )

    vote_2 = Vote(
        chain_id="test-chain",
        height=1,
        round=0,
        phase="PREVOTE",
        block_hash_or_nil=None,
        validator_pubkey=b"\x03" * 32,
        signature=b"\x04" * 64,
    )

    vote_set.add(vote_1)
    vote_set.add(vote_2)

    votes = vote_set.votes(
        height=1,
        round=0,
        phase="PREVOTE",
    )

    assert len(votes) == 2


def test_duplicate_vote_is_ignored():
    """Same key, same block_hash_or_nil, sent twice."""
    vote_set = VoteSet()

    vote = Vote(
        chain_id="test-chain",
        height=1,
        round=0,
        phase="PREVOTE",
        block_hash_or_nil=b"\xaa" * 32,
        validator_pubkey=b"\x01" * 32,
        signature=b"\x02" * 64,
    )

    duplicate = Vote(
        chain_id="test-chain",
        height=1,
        round=0,
        phase="PREVOTE",
        block_hash_or_nil=b"\xaa" * 32,
        validator_pubkey=b"\x01" * 32,
        signature=b"\x02" * 64,
    )

    first_result = vote_set.add(vote)
    second_result = vote_set.add(duplicate)

    assert first_result.outcome == VoteOutcome.ACCEPTED
    assert second_result.outcome == VoteOutcome.DUPLICATE_IGNORED
    assert second_result.stored_vote == vote  # original kept, not the duplicate
    assert len(vote_set) == 1
    assert vote_set.equivocations() == []


def test_equivocation_is_detected_and_first_vote_kept():
    """Same (height, round, phase, validator_pubkey) but different block_hash_or_nil → equivocation."""
    vote_set = VoteSet()

    first_vote = Vote(
        chain_id="test-chain",
        height=1,
        round=0,
        phase="PREVOTE",
        block_hash_or_nil=b"\xaa" * 32,
        validator_pubkey=b"\x01" * 32,
        signature=b"\x02" * 64,
    )
    conflicting_vote = Vote(
        chain_id="test-chain",
        height=1,
        round=0,
        phase="PREVOTE",
        block_hash_or_nil=b"\xbb" * 32,  # different block
        validator_pubkey=b"\x01" * 32,   # same validator, same slot
        signature=b"\x05" * 64,
    )

    first_result = vote_set.add(first_vote)
    second_result = vote_set.add(conflicting_vote)

    assert first_result.outcome == VoteOutcome.ACCEPTED
    assert second_result.outcome == VoteOutcome.EQUIVOCATION_DETECTED

    # The first vote is kept under this key.
    assert second_result.stored_vote == first_vote
    stored = vote_set.get(
        height=1, round=0, phase="PREVOTE", validator_pubkey=b"\x01" * 32
    )
    assert stored == first_vote
    assert len(vote_set) == 1  # conflicting vote did not add a second entry

    # Evidence was recorded, not silently discarded.
    assert vote_set.has_equivocated(
        height=1, round=0, phase="PREVOTE", validator_pubkey=b"\x01" * 32
    )
    records = vote_set.equivocations()
    assert len(records) == 1
    assert records[0].first_vote == first_vote
    assert records[0].conflicting_vote == conflicting_vote

    # AddResult also exposes the evidence for immediate logging.
    assert second_result.equivocation is not None
    assert second_result.equivocation.first_vote == first_vote
    assert second_result.equivocation.conflicting_vote == conflicting_vote


# ── T2-09 & T2-10: Quorum Counting Tests ──────────────────────────────────────


def test_quorum_count_single_validator():
    """T2-09: Single validator vote counts as 1."""
    vote_set = VoteSet()

    vote = Vote(
        chain_id="test-chain",
        height=1,
        round=0,
        phase="PREVOTE",
        block_hash_or_nil=b"\xaa" * 32,
        validator_pubkey=b"\x01" * 32,
        signature=b"\x02" * 64,
    )

    vote_set.add(vote)
    count = vote_set.quorum_count(height=1, round=0, phase="PREVOTE")

    assert count == 1


def test_quorum_count_multiple_validators():
    """T2-09: Multiple distinct validators all count."""
    vote_set = VoteSet()

    for i in range(1, 5):  # 4 validators
        vote = Vote(
            chain_id="test-chain",
            height=1,
            round=0,
            phase="PREVOTE",
            block_hash_or_nil=b"\xaa" * 32,
            validator_pubkey=bytes([i]) * 32,
            signature=bytes([i + 10]) * 64,
        )
        vote_set.add(vote)

    count = vote_set.quorum_count(height=1, round=0, phase="PREVOTE")
    assert count == 4


def test_quorum_count_duplicate_vote_not_double_counted():
    """T2-10: Duplicate vote from same validator doesn't increase count."""
    vote_set = VoteSet()

    vote = Vote(
        chain_id="test-chain",
        height=1,
        round=0,
        phase="PREVOTE",
        block_hash_or_nil=b"\xaa" * 32,
        validator_pubkey=b"\x01" * 32,
        signature=b"\x02" * 64,
    )

    duplicate = Vote(
        chain_id="test-chain",
        height=1,
        round=0,
        phase="PREVOTE",
        block_hash_or_nil=b"\xaa" * 32,
        validator_pubkey=b"\x01" * 32,
        signature=b"\x02" * 64,
    )

    vote_set.add(vote)
    vote_set.add(duplicate)

    count = vote_set.quorum_count(height=1, round=0, phase="PREVOTE")
    assert count == 1  # still 1, not 2


def test_quorum_count_equivocation_still_counts():
    """T2-10: Equivocation detected, but validator still counts in quorum."""
    vote_set = VoteSet()

    first_vote = Vote(
        chain_id="test-chain",
        height=1,
        round=0,
        phase="PREVOTE",
        block_hash_or_nil=b"\xaa" * 32,
        validator_pubkey=b"\x01" * 32,
        signature=b"\x02" * 64,
    )
    conflicting_vote = Vote(
        chain_id="test-chain",
        height=1,
        round=0,
        phase="PREVOTE",
        block_hash_or_nil=b"\xbb" * 32,
        validator_pubkey=b"\x01" * 32,
        signature=b"\x05" * 64,
    )

    vote_set.add(first_vote)
    vote_set.add(conflicting_vote)

    count = vote_set.quorum_count(height=1, round=0, phase="PREVOTE")
    assert count == 1  # validator still counts, once

    # Equivocation is detected, but quorum still includes them
    assert vote_set.has_equivocated(
        height=1, round=0, phase="PREVOTE", validator_pubkey=b"\x01" * 32
    )


def test_has_quorum_reaches_threshold():
    """T2-09: has_quorum returns True when quorum_count >= quorum_size."""
    vote_set = VoteSet()

    # Add 5 votes from 5 different validators
    for i in range(1, 6):
        vote = Vote(
            chain_id="test-chain",
            height=1,
            round=0,
            phase="PRECOMMIT",
            block_hash_or_nil=b"\xaa" * 32,
            validator_pubkey=bytes([i]) * 32,
            signature=bytes([i + 10]) * 64,
        )
        vote_set.add(vote)

    # For n=8, f=2, quorum = 2f+1 = 5
    assert vote_set.has_quorum(height=1, round=0, phase="PRECOMMIT", quorum_size=5)

    # But with a higher threshold, should fail
    assert not vote_set.has_quorum(
        height=1, round=0, phase="PRECOMMIT", quorum_size=6
    )


def test_quorum_count_per_phase_isolation():
    """T2-09: Votes in different phases are counted separately."""
    vote_set = VoteSet()

    for i in range(1, 4):
        prevote = Vote(
            chain_id="test-chain",
            height=1,
            round=0,
            phase="PREVOTE",
            block_hash_or_nil=b"\xaa" * 32,
            validator_pubkey=bytes([i]) * 32,
            signature=bytes([i + 10]) * 64,
        )
        precommit = Vote(
            chain_id="test-chain",
            height=1,
            round=0,
            phase="PRECOMMIT",
            block_hash_or_nil=b"\xaa" * 32,
            validator_pubkey=bytes([i]) * 32,
            signature=bytes([i + 20]) * 64,
        )
        vote_set.add(prevote)
        vote_set.add(precommit)

    prevote_count = vote_set.quorum_count(height=1, round=0, phase="PREVOTE")
    precommit_count = vote_set.quorum_count(height=1, round=0, phase="PRECOMMIT")

    assert prevote_count == 3
    assert precommit_count == 3


def test_quorum_count_per_height_round_isolation():
    """T2-09: Votes in different heights/rounds are counted separately."""
    vote_set = VoteSet()

    # Add 3 votes at (h=1, r=0, PREVOTE)
    for i in range(1, 4):
        vote = Vote(
            chain_id="test-chain",
            height=1,
            round=0,
            phase="PREVOTE",
            block_hash_or_nil=b"\xaa" * 32,
            validator_pubkey=bytes([i]) * 32,
            signature=bytes([i + 10]) * 64,
        )
        vote_set.add(vote)

    # Add 2 votes at (h=1, r=1, PREVOTE)
    for i in range(1, 3):
        vote = Vote(
            chain_id="test-chain",
            height=1,
            round=1,
            phase="PREVOTE",
            block_hash_or_nil=b"\xaa" * 32,
            validator_pubkey=bytes([i]) * 32,
            signature=bytes([i + 20]) * 64,
        )
        vote_set.add(vote)

    count_r0 = vote_set.quorum_count(height=1, round=0, phase="PREVOTE")
    count_r1 = vote_set.quorum_count(height=1, round=1, phase="PREVOTE")

    assert count_r0 == 3
    assert count_r1 == 2


def test_quorum_count_nonexistent_slot():
    """T2-09: Quorum count is 0 for a slot with no votes."""
    vote_set = VoteSet()

    vote = Vote(
        chain_id="test-chain",
        height=1,
        round=0,
        phase="PREVOTE",
        block_hash_or_nil=b"\xaa" * 32,
        validator_pubkey=b"\x01" * 32,
        signature=b"\x02" * 64,
    )
    vote_set.add(vote)

    # Different height
    count = vote_set.quorum_count(height=2, round=0, phase="PREVOTE")
    assert count == 0

    # Different round
    count = vote_set.quorum_count(height=1, round=1, phase="PREVOTE")
    assert count == 0

    # Different phase
    count = vote_set.quorum_count(height=1, round=0, phase="PRECOMMIT")
    assert count == 0
