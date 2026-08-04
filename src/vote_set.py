"""
VoteSet storage.

T2-07:
Store votes using the key:

    (height, round, phase, validator_pubkey)

T2-08:
- Duplicate detection:
    A re-received vote with the same (height, round, phase, validator_pubkey) and
    the same block_hash_or_nil is the same statement arriving twice (network
    duplication) — ignored silently.
- Equivocation detection:
    A re-received vote with the same key but a different block_hash_or_nil
    means this validator signed two conflicting votes for the same slot —
    Byzantine behavior. The first vote received is kept; the conflicting vote is
    rejected and recorded as evidence, not silently dropped.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional, Tuple

from src.vote import Vote


class VoteOutcome(str, Enum):
    ACCEPTED = "ACCEPTED"
    DUPLICATE_IGNORED = "DUPLICATE_IGNORED"
    EQUIVOCATION_DETECTED = "EQUIVOCATION_DETECTED"


VoteKey = Tuple[int, int, str, bytes]  # (height, round, phase, validator_pubkey)


@dataclass(frozen=True)
class EquivocationRecord:
    """Evidence of a validator signing two conflicting votes for one slot."""

    key: VoteKey
    first_vote: Vote
    conflicting_vote: Vote


@dataclass(frozen=True)
class AddResult:
    outcome: VoteOutcome
    stored_vote: Vote  # the vote counted under this key after add() returns
    equivocation: Optional[EquivocationRecord] = None


class VoteSet:
    """Store and retrieve votes, with duplicate/equivocation handling."""

    def __init__(self) -> None:
        self._votes: Dict[VoteKey, Vote] = {}
        self._equivocations: List[EquivocationRecord] = []

    def add(self, vote: Vote) -> AddResult:
        """
        Store a vote under (height, round, phase, validator_pubkey).

        Returns an AddResult describing what happened:
            ACCEPTED              — first vote seen for this key, stored.
            DUPLICATE_IGNORED     — same key, same block_hash_or_nil: already
                                    stored; ignored, original kept.
            EQUIVOCATION_DETECTED — same key, different block_hash_or_nil:
                                    original kept; evidence recorded and
                                    returned, new vote rejected.
        """

        if not isinstance(vote, Vote):
            raise TypeError(
                f"vote must be a Vote, got {type(vote).__name__}"
            )

        key: VoteKey = (
            vote.height,
            vote.round,
            vote.phase,
            vote.validator_pubkey,
        )

        existing = self._votes.get(key)

        if existing is None:
            self._votes[key] = vote
            return AddResult(outcome=VoteOutcome.ACCEPTED, stored_vote=vote)

        if existing.block_hash_or_nil == vote.block_hash_or_nil:
            # Same statement arriving again — ignore, keep what's stored.
            return AddResult(
                outcome=VoteOutcome.DUPLICATE_IGNORED,
                stored_vote=existing,
            )

        # Same VoteKey, different block_hash_or_nil: equivocation.
        # Keep the first vote; reject and record the conflicting one.
        record = EquivocationRecord(
            key=key,
            first_vote=existing,
            conflicting_vote=vote,
        )
        self._equivocations.append(record)

        return AddResult(
            outcome=VoteOutcome.EQUIVOCATION_DETECTED,
            stored_vote=existing,
            equivocation=record,
        )

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
        """Return the total number of stored (accepted) votes."""

        return len(self._votes)

    # ── equivocation evidence ──────────────────────────────────────────────────

    def equivocations(self) -> List[EquivocationRecord]:
        """All equivocation evidence recorded so far, in detection order."""
        return list(self._equivocations)

    def has_equivocated(
        self,
        height: int,
        round: int,
        phase: str,
        validator_pubkey: bytes,
    ) -> bool:
        """True if this validator equivocated at this (height, round, phase)."""
        key = (height, round, phase, validator_pubkey)
        return any(r.key == key for r in self._equivocations)
