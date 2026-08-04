"""
Pending block storage with the header-first ordering rule (F-30).
Enforces ordering only — a body can never be stored for a block_hash that has no stored header yet. 
It does not re-validate header or body content.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from src.block import BlockHeader
from src.transaction import Transaction


@dataclass(frozen=True)
class StoreRejection:
    """
    code is one of:
        HEADER_NOT_FOUND  - store_body called for a block_hash with no stored header yet
        BODY_CONFLICT     - a different body is already stored for this block_hash
        HEADER_CONFLICT   - a different header is already stored for this block_hash 
                             (should be impossible in practice as block_hash is derived from the header's own signed bytes
                             kept as a defensive check)
    """

    code: str
    detail: str


@dataclass(frozen=True)
class StoreResult:
    success: bool
    rejection: Optional[StoreRejection] = None


class BlockStore:
    """
    Keyed by block_hash. Each entry independently tracks:
        - whether a header has been stored
        - whether a body has been stored (only possible once the header is)
    """

    __slots__ = ("_headers", "_bodies")

    def __init__(self) -> None:
        self._headers: Dict[bytes, BlockHeader] = {}
        self._bodies: Dict[bytes, Tuple[Transaction, ...]] = {}

    def store_header(self, header: BlockHeader) -> StoreResult:
        """
        Store a header, keyed by its own block_hash.

        Idempotent: storing the identical header again (same block_hash, same content) is a no-op success.
        This method does not re-check chain_id, proposer, or signature.
        """
        block_hash = header.block_hash()

        existing = self._headers.get(block_hash)
        if existing is not None:
            if existing != header:
                # Should not be reachable in practice.
                # Kept as a defensive guard rather than a silent overwrite.
                return StoreResult(
                    success=False,
                    rejection=StoreRejection(
                        "HEADER_CONFLICT",
                        f"a different header is already stored for "
                        f"block_hash {block_hash.hex()}",
                    ),
                )
            return StoreResult(success=True)  # identical re-store, no-op

        self._headers[block_hash] = header
        return StoreResult(success=True)

    def store_body(self, block_hash: bytes, transactions: List[Transaction]) -> StoreResult:
        """
        Store a body for a previously-stored header.

        Rejects with HEADER_NOT_FOUND if no header has been stored yet for this block_hash
        the body must never be processed first.
        This method does not re-check that the body actually matches the header's tx_root.
        """
        if block_hash not in self._headers:
            return StoreResult(
                success=False,
                rejection=StoreRejection(
                    "HEADER_NOT_FOUND",
                    f"no header stored for block_hash {block_hash.hex()}; "
                    f"body rejected (header-first rule)",
                ),
            )

        body_tuple = tuple(transactions)
        existing = self._bodies.get(block_hash)
        if existing is not None:
            if existing != body_tuple:
                return StoreResult(
                    success=False,
                    rejection=StoreRejection(
                        "BODY_CONFLICT",
                        f"a different body is already stored for "
                        f"block_hash {block_hash.hex()}",
                    ),
                )
            return StoreResult(success=True)  # identical re-store, no-op

        self._bodies[block_hash] = body_tuple
        return StoreResult(success=True)

    # -- reads --------------------------------------------------

    def has_header(self, block_hash: bytes) -> bool:
        return block_hash in self._headers

    def has_body(self, block_hash: bytes) -> bool:
        return block_hash in self._bodies

    def get_header(self, block_hash: bytes) -> Optional[BlockHeader]:
        return self._headers.get(block_hash)

    def get_body(self, block_hash: bytes) -> Optional[Tuple[Transaction, ...]]:
        return self._bodies.get(block_hash)

    def is_complete(self, block_hash: bytes) -> bool:
        """True once both header and body are stored for this block_hash."""
        return self.has_header(block_hash) and self.has_body(block_hash)