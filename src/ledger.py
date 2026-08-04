"""
Append-only finalized ledger + state snapshot store for the blockchain
protocol.

T2-12:
- Ledger object holding the finalized chain, keyed by height
- Every finalize() call appends exactly the next height -- no gaps,
  no overwrite, no delete
- Each entry captures an immutable snapshot of post-execution state and
  sender nonces, so history can never be corrupted by later mutation

Out of scope here (extended in this same file by later tasks):
    T2-13 (F-52) -- atomic disk persistence of each finalized entry
    T2-14 (F-53) -- crash recovery: reload from the last persisted snapshot
"""

from __future__ import annotations

import base64
import json
import os
from dataclasses import dataclass
from typing import Any
from pathlib import Path

from src.block import BlockHeader
from src.state import State


@dataclass(frozen=True, slots=True)
class LedgerEntry:
    """
    One finalized block, plus the state it produced.

    `state` and `nonces` are the post-execution snapshot -- the result of
    applying this block's transactions on top of the parent's snapshot.
    """

    height: int
    block_hash: bytes
    header: BlockHeader
    applied_tx_ids: tuple[bytes, ...]
    state: State
    nonces: dict[bytes, int]


class Ledger:
    """
    Append-only store of finalized blocks, one entry per height.

    Invariants:
        - `finalize()` only ever accepts the next sequential height
          (`finalized_height + 1`); any other height is rejected.
        - There is no delete, update, or replace operation. Once an entry
          is appended it is never touched again -- the chain never rolls
          back (PROTOCOL_SPEC.md Section 7: "Block và state đã finalize là
          append-only; node không bao giờ rollback height đã finalize").
        - Every read returns a defensive copy of the stored `State`, so a
          caller mutating what it got back cannot corrupt ledger history.
    """

    __slots__ = ("_chain_id", "_entries", "_storage_path")

    def __init__(
        self,
        chain_id: str,
        storage_path: str | os.PathLike[str] | None = None,
    ) -> None:
        self._chain_id = chain_id
        self._entries: dict[int, LedgerEntry] = {}
        self._storage_path = Path(storage_path) if storage_path is not None else None

    @property
    def storage_path(self) -> Path | None:
        """Path used for the optional atomic finalized snapshot."""
        return self._storage_path

    @property
    def chain_id(self) -> str:
        return self._chain_id

    @property
    def finalized_height(self) -> int:
        """Highest finalized height, or 0 if nothing has been finalized yet."""
        return max(self._entries, default=0)

    @property
    def finalized_hash(self) -> bytes | None:
        """block_hash of the highest finalized block, or None if empty."""
        if not self._entries:
            return None
        return self._entries[self.finalized_height].block_hash

    def finalize(
        self,
        *,
        header: BlockHeader,
        applied_tx_ids: list[bytes],
        state: State,
        nonces: dict[bytes, int],
    ) -> LedgerEntry:
        """
        Append a newly-finalized block and its post-execution state.

        Args:
            header: The finalized block's signed header.
            applied_tx_ids: tx_ids applied by this block, in order.
            state: Post-execution state (a snapshot is taken; the caller's
                object is not retained or mutated).
            nonces: Post-execution sender nonce map (a snapshot is taken).

        Returns:
            The newly-created LedgerEntry.

        Raises:
            ValueError:
                - `header.chain_id` does not match this ledger's chain_id.
                - `header.height` is not exactly `finalized_height + 1`
                  (rejects gaps, re-finalizing, and any out-of-order write).
                - `header.parent_hash` does not match the previous entry's
                  `block_hash` (rejects appending onto a fork).
        """

        if header.chain_id != self._chain_id:
            raise ValueError(
                "CHAIN_ID_MISMATCH: "
                f"ledger is {self._chain_id!r}, header is {header.chain_id!r}"
            )

        expected_height = self.finalized_height + 1
        if header.height != expected_height:
            raise ValueError(
                "NON_SEQUENTIAL_HEIGHT: "
                f"expected {expected_height}, got {header.height}"
            )

        if expected_height > 1:
            parent_entry = self._entries[expected_height - 1]
            if header.parent_hash != parent_entry.block_hash:
                raise ValueError(
                    "PARENT_HASH_MISMATCH: "
                    f"expected {parent_entry.block_hash.hex()}, "
                    f"got {header.parent_hash.hex()}"
                )

        entry = LedgerEntry(
            height=header.height,
            block_hash=header.block_hash(),
            header=header,
            applied_tx_ids=tuple(applied_tx_ids),
            state=state.copy(),
            nonces=dict(nonces),
        )

        # Persist before publishing the entry in memory.  If serialization,
        # fsync, or replace fails, the in-memory ledger remains unchanged.
        self._persist_entry(entry)
        self._entries[header.height] = entry
        return entry

    @staticmethod
    def _hex(value: bytes) -> str:
        return value.hex()

    def _snapshot_payload(self, entry: LedgerEntry) -> dict[str, Any]:
        """Build the deterministic F-52 snapshot representation."""
        header = entry.header
        return {
            "finalized_height": entry.height,
            "finalized_hash": self._hex(entry.block_hash),
            "state": [
                {"key": key, "value": base64.b64encode(value).decode("ascii")}
                for key, value in entry.state.items()
            ],
            "nonces": [
                {"sender_pubkey": self._hex(pubkey), "nonce": nonce}
                for pubkey, nonce in sorted(
                    entry.nonces.items(), key=lambda item: item[0]
                )
            ],
            "block": {
                "header": {
                    "chain_id": header.chain_id,
                    "height": header.height,
                    "round": header.round,
                    "parent_hash": self._hex(header.parent_hash),
                    "tx_root": self._hex(header.tx_root),
                    "state_hash": self._hex(header.state_hash),
                    "proposer_pubkey": self._hex(header.proposer_pubkey),
                    "signature": self._hex(header.signature),
                },
                "applied_tx_ids": [
                    self._hex(tx_id) for tx_id in entry.applied_tx_ids
                ],
            },
        }

    def _persist_entry(self, entry: LedgerEntry) -> None:
        """Atomically replace the snapshot file for a finalized entry."""
        if self._storage_path is None:
            return

        path = self._storage_path
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(
            self._snapshot_payload(entry),
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8") + b"\n"
        temp_path = path.with_name(f".{path.name}.tmp")
        try:
            with temp_path.open("wb") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_path, path)
        finally:
            try:
                temp_path.unlink()
            except FileNotFoundError:
                pass

    def get_entry(self, height: int) -> LedgerEntry:
        """Return the finalized entry at `height`. Raises KeyError if absent."""
        return self._entries[height]

    def get_state(self, height: int) -> State:
        """
        Return a fresh copy of the state snapshot as of `height`.

        A copy is returned (rather than the stored snapshot itself) so the
        caller is free to mutate it without corrupting ledger history.
        """
        return self._entries[height].state.copy()

    def get_nonces(self, height: int) -> dict[bytes, int]:
        """Return a copy of the sender nonce map as of `height`."""
        return dict(self._entries[height].nonces)

    def is_finalized(self, height: int) -> bool:
        return height in self._entries

    def __len__(self) -> int:
        return len(self._entries)

    def __contains__(self, height: int) -> bool:
        return height in self._entries

    def __iter__(self):
        """Iterate finalized heights in ascending order."""
        return iter(sorted(self._entries))
