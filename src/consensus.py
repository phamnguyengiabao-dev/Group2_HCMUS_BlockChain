"""
consensus.py

T4-01

Consensus state maintained for one block height.

State per height:

    round
    locked_block_hash
    locked_round
    valid_block_hash
    prevotes
    precommits

T4-02

Deterministic proposer selection:

    sorted_validator_set[
        (height + round) % n
    ]
"""

from __future__ import annotations

from dataclasses import dataclass

from src.block_store import BlockStore
from src.identity import (
    ValidatorIdentity,
    load_validator_keys,
)
from src.vote_set import VoteSet

HASH_SIZE = 32


def _check_hash(value: bytes | None) -> bytes | None:
    """
    Validate a block hash.
    """

    if value is None:
        return None

    if not isinstance(value, bytes):
        raise TypeError(
            "block hash must be bytes"
        )

    if len(value) != HASH_SIZE:
        raise ValueError(
            f"block hash must be {HASH_SIZE} bytes"
        )

    return value


def select_proposer(
    height: int,
    round: int,
) -> ValidatorIdentity:
    """
    T4-02

    proposer =
        validator_set_sorted[
            (height + round) % n
        ]
    """

    if height <= 0:
        raise ValueError(
            "height must be positive"
        )

    if round < 0:
        raise ValueError(
            "round must be >= 0"
        )

    validators = load_validator_keys()

    if len(validators) == 0:
        raise ValueError(
            "validator set is empty"
        )

    return validators[
        (height + round)
        % len(validators)
    ]


@dataclass(slots=True)
class ConsensusState:
    """
    Consensus state for one blockchain height.
    """

    height: int

    round: int = 0

    locked_block_hash: bytes | None = None
    locked_round: int | None = None

    valid_block_hash: bytes | None = None

    block_store: BlockStore | None = None

    prevotes: VoteSet | None = None
    precommits: VoteSet | None = None

    def __post_init__(self) -> None:

        if self.height <= 0:
            raise ValueError(
                "height must be positive"
            )

        _check_hash(
            self.locked_block_hash
        )

        _check_hash(
            self.valid_block_hash
        )

        if self.block_store is None:
            self.block_store = BlockStore()

        if self.prevotes is None:
            self.prevotes = VoteSet()

        if self.precommits is None:
            self.precommits = VoteSet()

    # --------------------------------------------------
    # round
    # --------------------------------------------------

    def set_round(
        self,
        round: int,
    ) -> None:

        if round < 0:
            raise ValueError(
                "round must be >= 0"
            )

        self.round = round

    def next_round(self) -> int:
        self.round += 1
        return self.round

    # --------------------------------------------------
    # proposer
    # --------------------------------------------------

    def proposer(self) -> ValidatorIdentity:
        """
        Return proposer for the
        current (height, round).
        """

        return select_proposer(
            self.height,
            self.round,
        )

    # --------------------------------------------------
    # lock
    # --------------------------------------------------

    @property
    def locked(self) -> bool:
        return (
            self.locked_block_hash
            is not None
        )

    def lock(
        self,
        block_hash: bytes,
        round: int,
    ) -> None:

        _check_hash(block_hash)

        if not self.block_store.has_header(
            block_hash
        ):
            raise ValueError(
                "unknown block hash"
            )

        self.locked_block_hash = block_hash
        self.locked_round = round

    def unlock(self) -> None:

        self.locked_block_hash = None
        self.locked_round = None

    # --------------------------------------------------
    # valid block
    # --------------------------------------------------

    def set_valid_block(
        self,
        block_hash: bytes | None,
    ) -> None:

        if block_hash is not None:

            _check_hash(block_hash)

            if not self.block_store.has_header(
                block_hash
            ):
                raise ValueError(
                    "unknown block hash"
                )

        self.valid_block_hash = block_hash

    # --------------------------------------------------
    # votes
    # --------------------------------------------------

    def reset_votes(self) -> None:
        """
        Clear all prevotes and
        precommits.
        """

        self.prevotes = VoteSet()
        self.precommits = VoteSet()

    # --------------------------------------------------
    # height
    # --------------------------------------------------

    def reset_height(
        self,
        new_height: int,
    ) -> None:

        if new_height <= 0:
            raise ValueError(
                "height must be positive"
            )

        self.height = new_height
        self.round = 0

        self.locked_block_hash = None
        self.locked_round = None

        self.valid_block_hash = None

        self.block_store = BlockStore()

        self.prevotes = VoteSet()
        self.precommits = VoteSet()