from src.vote import Vote
from src.vote_set import VoteSet


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

    vote_set.add(vote)

    result = vote_set.get(
        height=1,
        round=0,
        phase="PREVOTE",
        validator_pubkey=b"\x01" * 32,
    )

    assert result == vote
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