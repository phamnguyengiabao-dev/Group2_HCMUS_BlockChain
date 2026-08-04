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
