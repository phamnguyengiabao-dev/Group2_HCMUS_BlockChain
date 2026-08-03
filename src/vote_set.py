"""
VoteSet storage.

T2-07:
Store votes using the key:

    (height, round, phase, validator_pubkey)
"""

from src.vote import Vote


class VoteSet:
    """Store and retrieve votes."""

    def __init__(self) -> None:
        self._votes = {}

    def add(self, vote: Vote) -> None:
        """
        Store a vote.

        The storage key is:

            (height, round, phase, validator_pubkey)
        """

        if not isinstance(vote, Vote):
            raise TypeError(
                f"vote must be a Vote, got {type(vote).__name__}"
            )

        key = (
            vote.height,
            vote.round,
            vote.phase,
            vote.validator_pubkey,
        )

        self._votes[key] = vote

    def get(
        self,
        height: int,
        round: int,
        phase: str,
        validator_pubkey: bytes,
    ) -> Vote | None:
        """
        Get a vote using:

            (height, round, phase, validator_pubkey)

        Returns None if the vote does not exist.
        """

        key = (
            height,
            round,
            phase,
            validator_pubkey,
        )

        return self._votes.get(key)

    def votes(
        self,
        height: int,
        round: int,
        phase: str,
    ) -> list[Vote]:
        """
        Return all votes for:

            (height, round, phase)
        """

        result = []

        for key, vote in self._votes.items():
            if (
                key[0] == height
                and key[1] == round
                and key[2] == phase
            ):
                result.append(vote)

        return result

    def __len__(self) -> int:
        """Return the total number of stored votes."""

        return len(self._votes)