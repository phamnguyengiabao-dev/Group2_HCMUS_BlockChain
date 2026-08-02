"""
Deterministic transaction executor.

T1-13: 
- Apply an ORDERED list of transactions (the block body, in the order given — this module never reorders).
- A transaction is applied if it passes every validity guard below, checked in a FIXED order.
- If ANY transaction in the list is invalid, the ENTIRE block is rejected: no partial state change is returned, and the caller must not apply the block.
- Pure / side-effect free: never mutates the given state, never reads wall-clock, RNG, filesystem, or network/receipt order.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Set, Tuple

from src.state import State
from src.transaction import Transaction


IsTxFinalized = Callable[[bytes], bool]

@dataclass(frozen=True)
class ExecutionConfig:
    max_key_bytes: int = 256          # network.max_key_size_bytes
    max_value_bytes: int = 4096       # network.max_value_size_bytes
    max_block_transactions: int = 10  # block_capacity


@dataclass(frozen=True)
class TxRejection:
    tx_index: int             # position in block body, 0-based (-1 = block-level)
    tx_id: Optional[bytes]    # None if rejected before tx_id could be computed
    code: str                 # exception class name
    detail: str               # full message, for logging


@dataclass(frozen=True)
class ExecutionResult:
    ok: bool
    # populated iff ok is True:
    state: Optional[State] = None
    nonces: Optional[Dict[bytes, int]] = None
    applied_tx_ids: List[bytes] = field(default_factory=list)
    # populated iff ok is False:
    rejection: Optional[TxRejection] = None


def execute_block(
    transactions: List[Transaction],
    parent_state: State,
    nonces: Dict[bytes, int],
    chain_id: str,
    is_tx_finalized: IsTxFinalized,
    config: ExecutionConfig = ExecutionConfig(),
) -> ExecutionResult:
    """
    Apply `transactions` in order, on top of `parent_state`.
    `parent_state` and `nonces` are never mutated (State.copy() + a fresh dict own every write). 
    Never reads wall-clock, RNG, filesystem, or network/receipt order.

    On success: returns the full new post-state, the full updated nonce map, and the ordered list of applied tx_ids.
    
    On the first invalid transaction: the WHOLE block is rejected (ok=False, one rejection), 
    and `state`/`nonces` stay None, so the caller must not commit anything from this attempt.
    """
    if len(transactions) > config.max_block_transactions:
        return ExecutionResult(
            ok=False,
            rejection=TxRejection(
                -1, None, "BLOCK_TOO_MANY_TX",
                f"{len(transactions)} transactions exceeds "
                f"maximum {config.max_block_transactions}",
            ),
        )

    new_state = parent_state.copy()
    new_nonces: Dict[bytes, int] = dict(nonces)
    seen_tx_ids: Set[bytes] = set()
    applied_tx_ids: List[bytes] = []

    for i, tx in enumerate(transactions):
        expected_nonce = new_nonces.get(tx.sender_pubkey, 0)

        try:
            tx.validate(
                expected_chain_id=chain_id,
                expected_nonce=expected_nonce,
                max_key_size=config.max_key_bytes,
                max_value_size=config.max_value_bytes,
            )
        except (TypeError, ValueError) as exc:
            return ExecutionResult(ok=False, rejection=TxRejection(i, None, type(exc).__name__, str(exc)))

        tx_id = tx.tx_id()
        if tx_id in seen_tx_ids:
            return ExecutionResult(
                ok=False,
                rejection=TxRejection(
                    i, tx_id, "DUPLICATE_IN_BLOCK",
                    f"tx_id {tx_id.hex()} appears more than once in this block"
                )
            )
        if is_tx_finalized(tx_id):
            return ExecutionResult(
                ok=False,
                rejection=TxRejection(
                    i, tx_id, "ALREADY_FINALIZED",
                    f"tx_id {tx_id.hex()} is already in finalized history"
                )
            )

        # All guards passed: apply.
        new_state.insert(tx.key, tx.value_bytes)
        new_nonces[tx.sender_pubkey] = tx.nonce + 1
        seen_tx_ids.add(tx_id)
        applied_tx_ids.append(tx_id)

    return ExecutionResult(ok=True, state=new_state, nonces=new_nonces, applied_tx_ids=applied_tx_ids)