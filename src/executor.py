"""
Deterministic transaction executor (T1-13).

The executor applies an ordered list of transactions to a parent state,
producing a post-state and an updated nonce map.

Key correctness properties
--------------------------
P1 — Atomicity:   If any transaction in the block is invalid, the entire
                  block is invalidated; the parent state is returned unchanged
                  and the nonce map is not mutated.

P2 — Determinism: Given the same parent state, nonce map, transaction list,
                  and configuration, two executions always produce the same
                  post-state hash and the same result flag.

P3 — No double-apply: tx_id deduplication within a block prevents the same
                  transaction from being applied twice in one block.

P4 — Canonical order: Transactions are applied strictly in the order provided;
                  the executor never reorders them.

The executor does NOT persist anything — that is the ledger's job (T2-12/T2-13).
It only computes the post-state and communicates success or failure.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from src.state import State
from src.transaction import Transaction


@dataclass(frozen=True)
class ExecutionConfig:
    """
    Protocol-level limits forwarded to each transaction's ``validate()`` call.

    All values come from ``config/default.json``; the scenario runner injects
    them here so the executor never reads the config directly.
    """

    chain_id: str
    max_key_size: int
    max_value_size: int


@dataclass
class ExecutionResult:
    """
    Output of a single block execution attempt.

    Attributes
    ----------
    success : bool
        True  — all transactions validated and applied; ``post_state`` and
                ``nonces`` contain the authoritative post-execution values.
        False — at least one transaction was invalid; ``post_state`` is the
                *unchanged* parent state and ``nonces`` is the unchanged map.
                ``error_tx_index`` and ``error_reason`` identify the failure.
    post_state : State
        The resulting state (either a new State after a successful run, or the
        unchanged parent State on failure).
    nonces : dict[bytes, int]
        The resulting nonce map (updated on success, unchanged on failure).
    error_tx_index : int | None
        Zero-based index of the first invalid transaction, or None on success.
    error_reason : str | None
        Human-readable reason for the failure, or None on success.
    applied_tx_ids : list[bytes]
        tx_ids of every transaction that was successfully applied (empty on
        failure).
    """

    success: bool
    post_state: State
    nonces: dict[bytes, int]
    error_tx_index: int | None = None
    error_reason: str | None = None
    applied_tx_ids: list[bytes] = field(default_factory=list)


def execute_block(
    transactions: list[Transaction],
    parent_state: State,
    nonces: dict[bytes, int],
    config: ExecutionConfig,
) -> ExecutionResult:
    """
    Apply *transactions* to *parent_state* and return an ExecutionResult.

    The function is pure: it never mutates *parent_state* or *nonces*.  It
    works on private copies and either commits them (success) or discards them
    (failure).

    Parameters
    ----------
    transactions:
        Ordered list of Transaction objects representing the block's body.
        May be empty (producing a state hash identical to the parent).
    parent_state:
        The last-finalized or parent-candidate State.  Not mutated.
    nonces:
        Map from sender_pubkey (bytes) to their next expected nonce.
        A sender absent from the map is treated as having nonce 0.
        Not mutated.
    config:
        Protocol-level limits (chain_id, max_key_size, max_value_size).

    Returns
    -------
    ExecutionResult
        See the dataclass docstring for field semantics.
    """

    # Work on copies — the originals must not be touched on failure (P1).
    working_state = parent_state.copy()
    working_nonces: dict[bytes, int] = dict(nonces)

    # Deduplication set: tx_id bytes → already-seen flag (P3).
    seen_tx_ids: set[bytes] = set()

    applied_ids: list[bytes] = []

    for idx, tx in enumerate(transactions):
        pubkey = tx.sender_pubkey

        # --- expected nonce for this sender ---
        expected_nonce = working_nonces.get(pubkey, 0)

        # --- duplicate-tx-id guard (P3) — checked before nonce validation so
        #     the error message is unambiguous.  A duplicate tx will also fail
        #     the nonce check (the nonce was already advanced by the first
        #     copy), but DUPLICATE_TX_ID is the more precise rejection reason.
        tx_id = tx.tx_id()
        if tx_id in seen_tx_ids:
            return ExecutionResult(
                success=False,
                post_state=parent_state,
                nonces=nonces,
                error_tx_index=idx,
                error_reason=f"DUPLICATE_TX_ID: tx_id {tx_id.hex()} already in block",
            )

        # --- attempt validation ---
        try:
            tx.validate(
                expected_chain_id=config.chain_id,
                expected_nonce=expected_nonce,
                max_key_size=config.max_key_size,
                max_value_size=config.max_value_size,
            )
        except (ValueError, TypeError) as exc:
            # P1: discard all work, return parent unchanged.
            return ExecutionResult(
                success=False,
                post_state=parent_state,
                nonces=nonces,
                error_tx_index=idx,
                error_reason=str(exc),
            )

        # --- apply the write ---
        working_state.insert(tx.key, tx.value_bytes)

        # --- advance this sender's nonce and register tx_id ---
        working_nonces[pubkey] = expected_nonce + 1
        seen_tx_ids.add(tx_id)
        applied_ids.append(tx_id)

    # All transactions validated and applied (P1 satisfied, P4 preserved).
    return ExecutionResult(
        success=True,
        post_state=working_state,
        nonces=working_nonces,
        applied_tx_ids=applied_ids,
    )
