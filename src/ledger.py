"""
Append-only finalized ledger + state snapshot store for the blockchain
protocol.

T2-12:
- Ledger object holding the finalized chain, keyed by height
- Every finalize() call appends exactly the next height -- no gaps,
  no overwrite, no delete
- Each entry captures an immutable snapshot of post-execution state and
  sender nonces, so history can never be corrupted by later mutation

T2-13 (F-52):
- Atomically persist the latest finalized entry to disk

T2-14 (F-53):
- Recover the latest finalized entry from the persisted snapshot
- Discard unfinalized proposals and votes
"""

from __future__ import annotations

<<<<<<< Updated upstream
from dataclasses import dataclass
=======
import base64
import binascii
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any
>>>>>>> Stashed changes

from src.block import BlockHeader
from src.state import State


@dataclass(frozen=True, slots=True)
class LedgerEntry:
    """
    One finalized block, plus the state it produced.

    `state` and `nonces` are the post-execution snapshot.
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

    T2-14 restores only finalized data. Unfinalized proposals and
    votes are intentionally not persisted or restored.
    """

<<<<<<< Updated upstream
    __slots__ = ("_chain_id", "_entries")
=======
    __slots__ = (
        "_chain_id",
        "_entries",
        "_storage_path",
    )
>>>>>>> Stashed changes

    def __init__(self, chain_id: str) -> None:
        self._chain_id = chain_id
        self._entries: dict[int, LedgerEntry] = {}
<<<<<<< Updated upstream
=======

        self._storage_path = (
            Path(storage_path)
            if storage_path is not None
            else None
        )

    @property
    def storage_path(self) -> Path | None:
        """Path used for the finalized snapshot."""
        return self._storage_path
>>>>>>> Stashed changes

    @property
    def chain_id(self) -> str:
        """Return the chain ID."""
        return self._chain_id

    @property
    def finalized_height(self) -> int:
        """Highest finalized height, or 0 if empty."""
        return max(
            self._entries,
            default=0,
        )

    @property
    def finalized_hash(self) -> bytes | None:
        """Hash of the highest finalized block."""
        if not self._entries:
            return None

        return self._entries[
            self.finalized_height
        ].block_hash

    # ============================================================
    # T2-12
    # ============================================================

    def finalize(
        self,
        *,
        header: BlockHeader,
        applied_tx_ids: list[bytes],
        state: State,
        nonces: dict[bytes, int],
    ) -> LedgerEntry:
        """Append the next finalized block."""

        if header.chain_id != self._chain_id:
            raise ValueError(
                "CHAIN_ID_MISMATCH: "
                f"ledger is {self._chain_id!r}, "
                f"header is {header.chain_id!r}"
            )

        expected_height = (
            self.finalized_height + 1
        )

        if header.height != expected_height:
            raise ValueError(
                "NON_SEQUENTIAL_HEIGHT: "
                f"expected {expected_height}, "
                f"got {header.height}"
            )

        if expected_height > 1:
            parent_entry = self._entries[
                expected_height - 1
            ]

            if (
                header.parent_hash
                != parent_entry.block_hash
            ):
                raise ValueError(
                    "PARENT_HASH_MISMATCH: "
                    f"expected "
                    f"{parent_entry.block_hash.hex()}, "
                    f"got "
                    f"{header.parent_hash.hex()}"
                )

        entry = LedgerEntry(
            height=header.height,
            block_hash=header.block_hash(),
            header=header,
            applied_tx_ids=tuple(
                applied_tx_ids
            ),
            state=state.copy(),
            nonces=dict(
                nonces
            ),
        )

<<<<<<< Updated upstream
        self._entries[header.height] = entry
        return entry

    def get_entry(self, height: int) -> LedgerEntry:
        """Return the finalized entry at `height`. Raises KeyError if absent."""
        return self._entries[height]
=======
        # T2-13:
        # Persist before publishing in memory.
        self._persist_entry(
            entry
        )

        self._entries[
            header.height
        ] = entry

        return entry

    # ============================================================
    # T2-13
    # ============================================================

    @staticmethod
    def _hex(value: bytes) -> str:
        return value.hex()

    def _snapshot_payload(
        self,
        entry: LedgerEntry,
    ) -> dict[str, Any]:
        """Build deterministic snapshot data."""

        header = entry.header

        return {
            "finalized_height": (
                entry.height
            ),

            "finalized_hash": (
                self._hex(
                    entry.block_hash
                )
            ),

            "state": [
                {
                    "key": key,
                    "value": (
                        base64
                        .b64encode(value)
                        .decode("ascii")
                    ),
                }
                for key, value
                in entry.state.items()
            ],

            "nonces": [
                {
                    "sender_pubkey": (
                        self._hex(
                            pubkey
                        )
                    ),
                    "nonce": nonce,
                }
                for pubkey, nonce
                in sorted(
                    entry.nonces.items(),
                    key=lambda item: item[0],
                )
            ],

            "block": {
                "header": {
                    "chain_id": (
                        header.chain_id
                    ),

                    "height": (
                        header.height
                    ),

                    "round": (
                        header.round
                    ),

                    "parent_hash": (
                        self._hex(
                            header.parent_hash
                        )
                    ),

                    "tx_root": (
                        self._hex(
                            header.tx_root
                        )
                    ),

                    "state_hash": (
                        self._hex(
                            header.state_hash
                        )
                    ),

                    "proposer_pubkey": (
                        self._hex(
                            header.proposer_pubkey
                        )
                    ),

                    "signature": (
                        self._hex(
                            header.signature
                        )
                    ),
                },

                "applied_tx_ids": [
                    self._hex(
                        tx_id
                    )
                    for tx_id
                    in entry.applied_tx_ids
                ],
            },
        }

    def _persist_entry(
        self,
        entry: LedgerEntry,
    ) -> None:
        """
        T2-13 / F-52:
        Atomically persist the latest finalized entry.
        """

        if self._storage_path is None:
            return

        path = self._storage_path

        path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        payload = (
            json.dumps(
                self._snapshot_payload(
                    entry
                ),
                ensure_ascii=False,
                separators=(
                    ",",
                    ":",
                ),
            ).encode("utf-8")
            + b"\n"
        )

        temp_path = path.with_name(
            f".{path.name}.tmp"
        )

        try:
            with temp_path.open(
                "wb"
            ) as handle:

                handle.write(
                    payload
                )

                handle.flush()

                os.fsync(
                    handle.fileno()
                )

            os.replace(
                temp_path,
                path,
            )

        finally:
            try:
                temp_path.unlink()

            except FileNotFoundError:
                pass

    # ============================================================
    # T2-14 / F-53
    # ============================================================
>>>>>>> Stashed changes

    @classmethod
    def load_snapshot(
        cls,
        chain_id: str,
        storage_path: str | os.PathLike[str],
    ) -> "Ledger":
        """
        Recover the latest finalized snapshot.

        Only finalized data is restored.

        Unfinalized proposals and votes are discarded because:
        - They are not included in the persisted snapshot.
        - Recovery creates a fresh Ledger.
        - Only the finalized LedgerEntry is inserted.
        """

        path = Path(
            storage_path
        )

        ledger = cls(
            chain_id=chain_id,
            storage_path=path,
        )

        # No persisted snapshot:
        # recover an empty ledger.
        if not path.exists():
            return ledger

        try:
            with path.open(
                "r",
                encoding="utf-8",
            ) as file:

                snapshot = json.load(
                    file
                )

            # ------------------------------------------------
            # Read finalized metadata.
            # ------------------------------------------------

            finalized_height = (
                snapshot[
                    "finalized_height"
                ]
            )

            finalized_hash = (
                bytes.fromhex(
                    snapshot[
                        "finalized_hash"
                    ]
                )
            )

            # ------------------------------------------------
            # Restore finalized state.
            # ------------------------------------------------

            state = State()

            for item in snapshot[
                "state"
            ]:

                state.insert(
                    item["key"],
                    base64.b64decode(
                        item["value"],
                        validate=True,
                    ),
                )

            # ------------------------------------------------
            # Restore finalized nonces.
            # ------------------------------------------------

            nonces: dict[
                bytes,
                int,
            ] = {}

            for item in snapshot[
                "nonces"
            ]:

                sender_pubkey = (
                    bytes.fromhex(
                        item[
                            "sender_pubkey"
                        ]
                    )
                )

                nonces[
                    sender_pubkey
                ] = item[
                    "nonce"
                ]

            # ------------------------------------------------
            # Restore finalized header.
            # ------------------------------------------------

            block_data = (
                snapshot[
                    "block"
                ]
            )

            header_data = (
                block_data[
                    "header"
                ]
            )

            header = BlockHeader(
                chain_id=(
                    header_data[
                        "chain_id"
                    ]
                ),

                height=(
                    header_data[
                        "height"
                    ]
                ),

                round=(
                    header_data[
                        "round"
                    ]
                ),

                parent_hash=(
                    bytes.fromhex(
                        header_data[
                            "parent_hash"
                        ]
                    )
                ),

                tx_root=(
                    bytes.fromhex(
                        header_data[
                            "tx_root"
                        ]
                    )
                ),

                state_hash=(
                    bytes.fromhex(
                        header_data[
                            "state_hash"
                        ]
                    )
                ),

                proposer_pubkey=(
                    bytes.fromhex(
                        header_data[
                            "proposer_pubkey"
                        ]
                    )
                ),

                signature=(
                    bytes.fromhex(
                        header_data[
                            "signature"
                        ]
                    )
                ),
            )

            # ------------------------------------------------
            # Restore finalized transaction IDs.
            # ------------------------------------------------

            applied_tx_ids = tuple(
                bytes.fromhex(
                    tx_id
                )
                for tx_id
                in block_data[
                    "applied_tx_ids"
                ]
            )

        except (
            KeyError,
            TypeError,
            ValueError,
            json.JSONDecodeError,
            binascii.Error,
        ) as exc:

            raise ValueError(
                "INVALID_SNAPSHOT"
            ) from exc

        # ----------------------------------------------------
        # Validate snapshot consistency.
        # ----------------------------------------------------

        if (
            header.chain_id
            != chain_id
        ):
            raise ValueError(
                "CHAIN_ID_MISMATCH: "
                f"expected "
                f"{chain_id!r}, "
                f"got "
                f"{header.chain_id!r}"
            )

        if (
            finalized_height
            != header.height
        ):
            raise ValueError(
                "INVALID_SNAPSHOT: "
                "finalized_height does not "
                "match header.height"
            )

        if (
            finalized_hash
            != header.block_hash()
        ):
            raise ValueError(
                "INVALID_SNAPSHOT: "
                "finalized_hash does not "
                "match block hash"
            )

        # ----------------------------------------------------
        # Restore only finalized entry.
        # ----------------------------------------------------

        ledger._entries[
            finalized_height
        ] = LedgerEntry(
            height=finalized_height,
            block_hash=finalized_hash,
            header=header,
            applied_tx_ids=(
                applied_tx_ids
            ),
            state=state.copy(),
            nonces=dict(
                nonces
            ),
        )

        # F-53:
        # Proposals and votes that were not finalized are not
        # loaded. They are discarded after crash recovery.

        return ledger

    # ============================================================
    # Read operations
    # ============================================================

    def get_entry(
        self,
        height: int,
    ) -> LedgerEntry:
        """Return finalized entry at height."""

        return self._entries[
            height
        ]

    def get_state(
        self,
        height: int,
    ) -> State:
        """Return a defensive copy."""

        return (
            self._entries[
                height
            ]
            .state
            .copy()
        )

    def get_nonces(
        self,
        height: int,
    ) -> dict[bytes, int]:
        """Return a defensive copy."""

        return dict(
            self._entries[
                height
            ].nonces
        )

    def is_finalized(
        self,
        height: int,
    ) -> bool:
        return (
            height
            in self._entries
        )

    def __len__(self) -> int:
        return len(
            self._entries
        )

    def __contains__(
        self,
        height: int,
    ) -> bool:
        return (
            height
            in self._entries
        )

    def __iter__(self):
        """Iterate heights in ascending order."""

        return iter(
            sorted(
                self._entries
            )
        )