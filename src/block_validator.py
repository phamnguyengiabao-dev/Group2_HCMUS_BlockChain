"""
Header-level validation guards.

- chain_id matches this run
- height / round are exactly what currently expected.
- parent_hash matches the expected parentparentent.
- proposer_pubkey matches the expected proposer for (height, round): validator_set[(height + round) % n]
- header.signature verifies under domain HEADER:<chain_id>, over header.unsigned_bytes()
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from src.block import BlockHeader
from src.crypto import verify


@dataclass(frozen=True)
class HeaderRejection:
    """
    code is one of:
        CHAIN_ID_MISMATCH
        HEIGHT_MISMATCH
        ROUND_MISMATCH
        PARENT_HASH_MISMATCH
        UNEXPECTED_PROPOSER
        INVALID_HEADER_SIGNATURE
    """
    code: str
    detail: str


@dataclass(frozen=True)
class HeaderValidationResult:
    success: bool
    rejection: Optional[HeaderRejection] = None


def expected_proposer(height: int, round_: int, validator_set: List[bytes]) -> bytes:
    n = len(validator_set)
    if n == 0:
        raise ValueError("validator_set must not be empty")
    return validator_set[(height + round_) % n]


def validate_header(
    header: BlockHeader,
    *,
    expected_chain_id: str,
    expected_height: int,
    expected_round: int,
    expected_parent_hash: bytes,
    validator_set: List[bytes],
) -> HeaderValidationResult:
    if header.chain_id != expected_chain_id:
        return HeaderValidationResult(
            success=False,
            rejection=HeaderRejection(
                "CHAIN_ID_MISMATCH",
                f"expected {expected_chain_id!r}, got {header.chain_id!r}",
            ),
        )

    if header.height != expected_height:
        return HeaderValidationResult(
            success=False,
            rejection=HeaderRejection(
                "HEIGHT_MISMATCH",
                f"expected height {expected_height}, got {header.height}",
            ),
        )

    if header.round != expected_round:
        return HeaderValidationResult(
            success=False,
            rejection=HeaderRejection(
                "ROUND_MISMATCH",
                f"expected round {expected_round}, got {header.round}",
            ),
        )

    if header.parent_hash != expected_parent_hash:
        return HeaderValidationResult(
            success=False,
            rejection=HeaderRejection(
                "PARENT_HASH_MISMATCH",
                f"expected parent {expected_parent_hash.hex()}, "
                f"got {header.parent_hash.hex()}",
            ),
        )

    proposer = expected_proposer(expected_height, expected_round, validator_set)
    if header.proposer_pubkey != proposer:
        return HeaderValidationResult(
            success=False,
            rejection=HeaderRejection(
                "UNEXPECTED_PROPOSER",
                f"expected proposer {proposer.hex()}, "
                f"got {header.proposer_pubkey.hex()}",
            ),
        )

    if not verify(
        header.proposer_pubkey,
        f"HEADER:{expected_chain_id}",
        header.unsigned_bytes(),
        header.signature,
    ):
        return HeaderValidationResult(
            success=False,
            rejection=HeaderRejection(
                "INVALID_HEADER_SIGNATURE",
                "header signature does not verify under HEADER domain",
            ),
        )

    return HeaderValidationResult(success=True)