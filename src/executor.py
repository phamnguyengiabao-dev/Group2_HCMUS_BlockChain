"""
Deterministic transaction executor (T1-13).

The executor applies an ORDERED list of transactions to a parent state,
producing a post-state and an updated nonce map.

Key correctness properties
--------------------------
P1 — Atomicity:   If ANY transaction in the block is invalid the ENTIRE block
                  is rejected; no partial state change is returned and the
                  caller must not commit anything from this attempt.

P2 — Determinism: Given the same parent_state, nonces, transactions, chain_id
                  and config, two executions always produce byte-identical
                  post-state hashes and the same result flag.

P3 — No double-apply: Duplicate tx_id within a block is detected and rejected
                  before any state mutation.  Cross-block replay is rejected
                  via the `is_tx_finalized` callback.

P4 — Canonical order: Transactions are applied strictly in the order provided;
                  this module never reorders them.

Pure / side-effect free: never mutates the given state or nonces, never reads
wall-clock, RNG, filesystem, or network.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Set

from src.state import State
from src.transaction import Transaction


# Callback type: given a tx_id (bytes), return True if that transaction has
# already been committed to the finalized chain.
IsTxFinalized = Callable[[bytes], bool]


@dataclass(frozen=True)
class ExecutionConfig:
    """
    Protocol-level limits for block execution.

    Defaults match config/default.json so callers that do not override get
    the correct production values automatically.
    """
    chain_id: str = "lab01-testnet"      # must match the running chain
    max_key_bytes: int = 256             # network.max_key_size_bytes
    max_value_bytes: int = 4096          # network.max_value_size_bytes
    max_block_transactions: int = 10     # block_capacity


@dataclass(frozen=True)
class TxRejection:
    """
    Structured description of why a block was rejected.

    tx_index == -1 means the rejection is at the block level (e.g. too many
    transactions) rather than tied to a specific transaction.
    tx_id is None when the rejection is raised before tx_id can be computed.
    """
    tx_index: int            # 0-based position; -1 = block-level
    tx_id: Optional[bytes]   # None if rejected before tx_id was computed
    code: str                # machine-readable rejection code
    detail: str              # human-readable message for logging


@dataclass(frozen=True)
class ExecutionResult:
    """
    Output of a single block execution attempt.

    On success (ok=True):
        state             — the full post-execution State
        nonces            — the updated nonce map
        applied_tx_ids    — ordered list of applied tx_ids

    On failure (ok=False):
        state / nonces    — both None; caller must not commit anything
        rejection         — structured reason for the failure
    """
    ok: bool
    state: Optional[State] = None
    nonces: Optional[Dict[bytes, int]] = None
    applied_tx_ids: List[bytes] = field(default_factory=list)
    rejection: Optional[TxRejection] = None


def execute_block(
    transactions: List[Transaction],
    parent_state: State,
    nonces: Dict[bytes, int],
    is_tx_finalized: IsTxFinalized,
    config: ExecutionConfig = ExecutionConfig(),
) -> ExecutionResult:
    """
    Apply *transactions* in order on top of *parent_state*.

    *parent_state* and *nonces* are never mutated: the executor works on
    private copies and either commits them (success) or discards them
    (failure), satisfying P1.

    Parameters
    ----------
    transactions:
        Ordered list of Transaction objects (block body). May be empty.
    parent_state:
        The last-finalized or parent-candidate State. Not mutated.
    nonces:
        Map from sender_pubkey (bytes) → next expected nonce.
        A sender absent from the map is treated as having nonce 0.
        Not mutated.
    is_tx_finalized:
        Callback that returns True when a tx_id is already in the finalized
        chain (used to reject cross-block replays, P3).
    config:
        Protocol limits: chain_id, max key/value size, max transactions.

    Returns
    -------
    ExecutionResult — see the dataclass docstring.
    """
    # ── Block-level guard: too many transactions ─────────────────────────────
    if len(transactions) > config.max_block_transactions:
        return ExecutionResult(
            ok=False,
            rejection=TxRejection(
                tx_index=-1,
                tx_id=None,
                code="BLOCK_TOO_MANY_TX",
                detail=(
                    f"{len(transactions)} transactions exceeds "
                    f"maximum {config.max_block_transactions}"
                ),
            ),
        )

    # Work on copies — originals must not be touched on failure (P1).
    new_state = parent_state.copy()
    new_nonces: Dict[bytes, int] = dict(nonces)
    seen_tx_ids: Set[bytes] = set()
    applied_tx_ids: List[bytes] = []

    for i, tx in enumerate(transactions):
        expected_nonce = new_nonces.get(tx.sender_pubkey, 0)

        # ── Duplicate-tx-id guard (P3, within-block) ─────────────────────────
        # Checked BEFORE signature validation so the rejection code is
        # unambiguous (a duplicate tx also fails the nonce check, but
        # DUPLICATE_IN_BLOCK is the precise reason).
        tx_id = tx.tx_id()
        if tx_id in seen_tx_ids:
            return ExecutionResult(
                ok=False,
                rejection=TxRejection(
                    tx_index=i,
                    tx_id=tx_id,
                    code="DUPLICATE_IN_BLOCK",
                    detail=(
                        f"tx_id {tx_id.hex()} appears more than once "
                        "in this block"
                    ),
                ),
            )

        # ── Cross-block replay guard (P3, finalized history) ─────────────────
        if is_tx_finalized(tx_id):
            return ExecutionResult(
                ok=False,
                rejection=TxRejection(
                    tx_index=i,
                    tx_id=tx_id,
                    code="ALREADY_FINALIZED",
                    detail=(
                        f"tx_id {tx_id.hex()} is already in "
                        "finalized history"
                    ),
                ),
            )

        # ── Per-transaction validity guards ──────────────────────────────────
        try:
            tx.validate(
                expected_chain_id=config.chain_id,
                expected_nonce=expected_nonce,
                max_key_size=config.max_key_bytes,
                max_value_size=config.max_value_bytes,
            )
        except (TypeError, ValueError) as exc:
            # P1: discard all work, return with rejection.
            return ExecutionResult(
                ok=False,
                rejection=TxRejection(
                    tx_index=i,
                    tx_id=tx_id,
                    code=type(exc).__name__,
                    detail=str(exc),
                ),
            )

        # ── All guards passed: apply write ────────────────────────────────────
        new_state.insert(tx.key, tx.value_bytes)
        new_nonces[tx.sender_pubkey] = tx.nonce + 1
        seen_tx_ids.add(tx_id)
        applied_tx_ids.append(tx_id)

    # All transactions validated and applied (P1 satisfied, P4 preserved).
    return ExecutionResult(
        ok=True,
        state=new_state,
        nonces=new_nonces,
        applied_tx_ids=applied_tx_ids,
    )
