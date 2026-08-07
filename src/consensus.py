"""Safety guards for local consensus voting.

This module implements the two consensus rules that do not require the full
round/finalization state machine:

* F-35: choose a PREVOTE without violating the validator's current lock.
* F-33: never sign two different votes for the same
  ``(height, round, phase)`` slot.

Observed votes are expected to have passed the normal router/Vote validation
before being inserted into a :class:`~src.vote_set.VoteSet`.  The lock guard
still asks ``VoteSet`` to establish an exact, distinct-validator quorum; it
never accepts a caller-supplied "has quorum" flag.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Collection

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from src.vote import (
    HASH_SIZE,
    PHASE_PRECOMMIT,
    PHASE_PREVOTE,
    Vote,
)
from src.vote_set import VoteSet


# Vote exposes the public/signature sizes, while the private Ed25519 seed has
# the same fixed width as its public key in this protocol.
PRIVATE_KEY_SIZE = 32
UINT64_MAX = (1 << 64) - 1
VoteSlot = tuple[int, int, str]


def _validate_height(height: object) -> int:
    if not isinstance(height, int) or isinstance(height, bool):
        raise TypeError("INVALID_HEIGHT: height must be an integer")
    if height < 1 or height > UINT64_MAX:
        raise ValueError("INVALID_HEIGHT: height must be in [1, 2^64 - 1]")
    return height


def _validate_round(round_: object, *, field_name: str = "round") -> int:
    if not isinstance(round_, int) or isinstance(round_, bool):
        raise TypeError(f"INVALID_ROUND: {field_name} must be an integer")
    if round_ < 0 or round_ > UINT64_MAX:
        raise ValueError(f"INVALID_ROUND: {field_name} must be in [0, 2^64 - 1]")
    return round_


def _validate_hash(value: object, *, field_name: str, allow_none: bool) -> bytes | None:
    if value is None:
        if allow_none:
            return None
        raise TypeError(f"INVALID_BLOCK_HASH: {field_name} must be bytes")
    if not isinstance(value, bytes):
        suffix = " or None" if allow_none else ""
        raise TypeError(f"INVALID_BLOCK_HASH: {field_name} must be bytes{suffix}")
    if len(value) != HASH_SIZE:
        raise ValueError(
            f"INVALID_BLOCK_HASH: {field_name} must be exactly {HASH_SIZE} bytes"
        )
    return value


def _validate_phase(phase: object) -> str:
    if not isinstance(phase, str):
        raise TypeError("INVALID_PHASE: phase must be a string")
    if phase not in (PHASE_PREVOTE, PHASE_PRECOMMIT):
        raise ValueError(
            "INVALID_PHASE: phase must be PREVOTE or PRECOMMIT"
        )
    return phase


@dataclass(slots=True)
class ConsensusState:
    """The minimum per-height state needed by the F-35 prevote guard."""

    height: int
    round: int = 0
    locked_block_hash: bytes | None = None
    locked_round: int | None = None
    valid_block_hash: bytes | None = None
    prevotes: VoteSet = field(default_factory=VoteSet)
    precommits: VoteSet = field(default_factory=VoteSet)

    def __post_init__(self) -> None:
        _validate_height(self.height)
        _validate_round(self.round)
        _validate_hash(
            self.locked_block_hash,
            field_name="locked_block_hash",
            allow_none=True,
        )
        _validate_hash(
            self.valid_block_hash,
            field_name="valid_block_hash",
            allow_none=True,
        )

        if (self.locked_block_hash is None) != (self.locked_round is None):
            raise ValueError(
                "INVALID_LOCK: locked_block_hash and locked_round must both be set or both be None"
            )
        if self.locked_round is not None:
            _validate_round(self.locked_round, field_name="locked_round")
            if self.locked_round > self.round:
                raise ValueError(
                    "INVALID_LOCK: locked_round cannot be greater than the current round"
                )

        if not isinstance(self.prevotes, VoteSet):
            raise TypeError("prevotes must be a VoteSet")
        if not isinstance(self.precommits, VoteSet):
            raise TypeError("precommits must be a VoteSet")

    def choose_prevote(
        self,
        candidate_hash: bytes,
        *,
        proposal_is_valid: bool,
        n: int,
        evidence_round: int | None = None,
        prevote_evidence: VoteSet | None = None,
    ) -> bytes | None:
        """Return the block hash to PREVOTE, or ``None`` for a NIL vote.

        A fully valid proposal is selected immediately when this validator is
        unlocked or when it matches the current lock.  A different proposal
        needs an exact PREVOTE quorum in ``evidence_round`` at this height.  Its
        evidence round must be strictly newer than ``locked_round`` and cannot
        be later than the current round.

        ``prevote_evidence`` defaults to this state's ``prevotes``.  It must be
        a ``VoteSet`` because quorum is established with
        :meth:`VoteSet.has_quorum`, including its distinct-validator counting.
        """

        candidate = _validate_hash(
            candidate_hash,
            field_name="candidate_hash",
            allow_none=False,
        )
        if not isinstance(proposal_is_valid, bool):
            raise TypeError("proposal_is_valid must be a boolean")
        if not isinstance(n, int) or isinstance(n, bool):
            raise TypeError("INVALID_VALIDATOR_COUNT: n must be an integer")
        if n < 1:
            raise ValueError("INVALID_VALIDATOR_COUNT: n must be >= 1")

        evidence = self.prevotes if prevote_evidence is None else prevote_evidence
        if not isinstance(evidence, VoteSet):
            raise TypeError("prevote_evidence must be a VoteSet")
        if evidence_round is not None:
            _validate_round(evidence_round, field_name="evidence_round")

        # Recheck mutable state at the decision boundary.  Invalid state must
        # never be converted into a vote decision merely because dataclass
        # fields are public.
        _validate_height(self.height)
        _validate_round(self.round)
        _validate_hash(
            self.locked_block_hash,
            field_name="locked_block_hash",
            allow_none=True,
        )
        if (self.locked_block_hash is None) != (self.locked_round is None):
            raise ValueError(
                "INVALID_LOCK: locked_block_hash and locked_round must both be set or both be None"
            )
        if self.locked_round is not None:
            _validate_round(self.locked_round, field_name="locked_round")
            if self.locked_round > self.round:
                raise ValueError(
                    "INVALID_LOCK: locked_round cannot be greater than the current round"
                )

        # Invalid proposals never receive a non-NIL vote, regardless of lock
        # state or any apparent quorum evidence.
        if not proposal_is_valid:
            return None

        if self.locked_block_hash is None or candidate == self.locked_block_hash:
            return candidate

        # A different block while locked needs explicit, eligible evidence.
        assert self.locked_round is not None
        if evidence_round is None:
            return None
        if evidence_round <= self.locked_round or evidence_round > self.round:
            return None

        if evidence.has_quorum(
            self.height,
            evidence_round,
            PHASE_PREVOTE,
            n,
            block_hash=candidate,
        ):
            return candidate
        return None


class VoteSigningGuard:
    """Sign at most one local vote per ``(height, round, phase)`` slot.

    One guard belongs to one fixed local validator identity and chain.  An
    identical retry is idempotent and returns the originally stored ``Vote``;
    a different block choice for the same slot raises ``CONFLICTING_VOTE``
    before any second signature is attempted.
    """

    def __init__(
        self,
        *,
        chain_id: str,
        validator_pubkey: bytes,
        validator_privkey: bytes,
        validator_set: Collection[bytes],
    ) -> None:
        if not isinstance(chain_id, str):
            raise TypeError("INVALID_CHAIN_ID: chain_id must be a string")
        if not chain_id:
            raise ValueError("INVALID_CHAIN_ID: chain_id must not be empty")
        if not isinstance(validator_pubkey, bytes):
            raise TypeError("INVALID_VALIDATOR_PUBKEY: validator_pubkey must be bytes")
        if len(validator_pubkey) != HASH_SIZE:
            raise ValueError(
                f"INVALID_VALIDATOR_PUBKEY: validator_pubkey must be {HASH_SIZE} bytes"
            )
        if not isinstance(validator_privkey, bytes):
            raise TypeError("INVALID_VALIDATOR_PRIVKEY: validator_privkey must be bytes")
        if len(validator_privkey) != PRIVATE_KEY_SIZE:
            raise ValueError(
                f"INVALID_VALIDATOR_PRIVKEY: validator_privkey must be {PRIVATE_KEY_SIZE} bytes"
            )
        if isinstance(validator_set, (bytes, bytearray, str)) or not isinstance(
            validator_set, Collection
        ):
            raise TypeError("INVALID_VALIDATOR_SET: validator_set must be a collection")

        validators = tuple(validator_set)
        if not validators:
            raise ValueError("INVALID_VALIDATOR_SET: validator_set must not be empty")
        for public_key in validators:
            if not isinstance(public_key, bytes) or len(public_key) != HASH_SIZE:
                raise ValueError(
                    "INVALID_VALIDATOR_SET: every validator public key must be 32 bytes"
                )
        if len(set(validators)) != len(validators):
            raise ValueError("INVALID_VALIDATOR_SET: validator public keys must be unique")
        if validator_pubkey not in validators:
            raise ValueError("NOT_A_VALIDATOR: local public key is not in validator_set")

        derived_pubkey = (
            Ed25519PrivateKey.from_private_bytes(validator_privkey)
            .public_key()
            .public_bytes(Encoding.Raw, PublicFormat.Raw)
        )
        if derived_pubkey != validator_pubkey:
            raise ValueError(
                "VALIDATOR_KEY_MISMATCH: private key does not match validator_pubkey"
            )

        self._chain_id = chain_id
        self._validator_pubkey = validator_pubkey
        self._validator_privkey = validator_privkey
        self._validator_set = tuple(sorted(validators))
        self._signed_votes: dict[VoteSlot, Vote] = {}

    @property
    def chain_id(self) -> str:
        return self._chain_id

    @property
    def validator_pubkey(self) -> bytes:
        return self._validator_pubkey

    @property
    def validator_set(self) -> tuple[bytes, ...]:
        """Return the validator set in canonical public-key order."""

        return self._validator_set

    def sign_vote(
        self,
        *,
        height: int,
        round: int,
        phase: str,
        block_hash_or_nil: bytes | None,
    ) -> Vote:
        """Create one signed vote, enforcing F-33 before signing."""

        checked_height = _validate_height(height)
        checked_round = _validate_round(round)
        checked_phase = _validate_phase(phase)
        checked_hash = _validate_hash(
            block_hash_or_nil,
            field_name="block_hash_or_nil",
            allow_none=True,
        )
        slot: VoteSlot = (checked_height, checked_round, checked_phase)

        existing = self._signed_votes.get(slot)
        if existing is not None:
            if existing.block_hash_or_nil == checked_hash:
                return existing
            raise ValueError(
                "CONFLICTING_VOTE: a different vote is already signed for "
                f"height={checked_height}, round={checked_round}, phase={checked_phase}"
            )

        # Do not reserve the slot before both construction and verification
        # succeed.  A crypto/construction failure therefore leaves it free for
        # a later retry.
        vote = Vote.create_signed(
            chain_id=self._chain_id,
            height=checked_height,
            round=checked_round,
            phase=checked_phase,
            block_hash_or_nil=checked_hash,
            validator_pubkey=self._validator_pubkey,
            validator_privkey=self._validator_privkey,
        )
        if not isinstance(vote, Vote):
            raise TypeError("SIGNED_VOTE_INVALID: Vote.create_signed() must return Vote")
        vote.validate(
            expected_chain_id=self._chain_id,
            validator_set=self._validator_set,
            expected_height=checked_height,
            expected_round=checked_round,
            expected_phase=checked_phase,
        )

        self._signed_votes[slot] = vote
        return vote

    def get_signed_vote(self, *, height: int, round: int, phase: str) -> Vote | None:
        """Return the original vote stored for a slot, if one exists."""

        slot = (
            _validate_height(height),
            _validate_round(round),
            _validate_phase(phase),
        )
        return self._signed_votes.get(slot)

    def signed_votes(self) -> tuple[Vote, ...]:
        """Return stored votes in canonical slot order."""

        return tuple(self._signed_votes[slot] for slot in sorted(self._signed_votes))

    def __len__(self) -> int:
        return len(self._signed_votes)


__all__ = [
    "ConsensusState",
    "VoteSigningGuard",
]
