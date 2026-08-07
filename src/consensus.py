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

T4-03 

Proposal handler + Timeout handling.
    - propose(): builds, signs, and broadcasts a block for the current
      (height, round) when this node is the proposer to every peer,
      HEADER is sent before BODY.
    - schedule_proposal_timeout() / handle_proposal_timeout(): a
      non-proposer schedules a wakeup at current_time + proposal_timeout;
      if no valid proposal has been accepted by the time it fires, the
      node prevotes NIL for this (height, round) and broadcasts it.

T4-04

    Prevote guard (F-35): prevote the block if unlocked or if the lock matches; 
    prevote a different block only if there is a quorum of prevotes for a later round; 
    otherwise, prevote NIL.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence

from src.block import BlockHeader, compute_tx_root
from src.block_store import BlockStore
from src.encoding import encode_bytes, encode_uint64
from src.executor import ExecutionConfig, execute_block
from src.identity import ValidatorIdentity, load_validator_keys
from src.ledger import Ledger
from src.network import Network
from src.state import State
from src.transaction import Transaction, encode_transaction_list
from src.vote import PHASE_PREVOTE, Vote
from src.vote_set import VoteSet

HASH_SIZE = 32
TIMEOUT_PROPOSAL_PAYLOAD = b"TIMEOUT:PROPOSAL"

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



# ====================================================
# Proposal handler
# ====================================================

@dataclass(frozen=True)
class ProposalResult:
    """
    Outcome of propose(). 
    success=False means this node is not the proposer for the current (height, round), 
    or building the block failed (e.g. execution rejected one of the pending transactions)
    in neither case is anything broadcast.
    """

    success: bool
    header: Optional[BlockHeader] = None
    reason: Optional[str] = None


def propose(
    state: ConsensusState,
    *,
    network: Network,
    ledger: Ledger,
    self_identity: ValidatorIdentity,
    validator_node_ids: Sequence[str],
    peers: Sequence[str],
    pending_transactions: list[Transaction],
    chain_id: str,
    exec_config: ExecutionConfig,
    logical_time: int,
) -> ProposalResult:
    """
    If this node is the proposer for (state.height, state.round): build a
    block on top of the current finalized parent, sign the header, and
    broadcast HEADER to every peer BEFORE broadcasting BODY.

    `validator_node_ids` maps validator index -> node_id string:
    validator_node_ids[i] must be the node_id for the validator whose
    ValidatorIdentity.index == i. Used to resolve both "am I the proposer"
    (by identity, not node_id) and the node_id to use as `sender` when
    broadcasting.

    `peers` must be given in a fixed, caller-determined order (e.g.
    sorted node_id order) — sends go out to each peer in the order
    given, no sorting or deduplication is done here.

    Returns success=False (nothing sent) if this node is not the current
    proposer, the parent block isn't finalized yet, or the tentative
    block fails execution (an invalid transaction was included).
    """
    proposer = state.proposer()
    if proposer.public_key != self_identity.public_key:
        return ProposalResult(success=False, reason="NOT_PROPOSER")

    if self_identity.index >= len(validator_node_ids):
        return ProposalResult(success=False, reason="UNKNOWN_SELF_NODE_ID")
    self_node_id = validator_node_ids[self_identity.index]

    parent_height = state.height - 1
    if parent_height == 0:
        parent_hash = b"\x00" * 32
        parent_state = State()
        parent_nonces: dict[bytes, int] = {}
    else:
        if not ledger.is_finalized(parent_height):
            return ProposalResult(success=False, reason="PARENT_NOT_FINALIZED")
        parent_entry = ledger.get_entry(parent_height)
        parent_hash = parent_entry.block_hash
        parent_state = ledger.get_state(parent_height)
        parent_nonces = ledger.get_nonces(parent_height)

    exec_result = execute_block(
        pending_transactions, parent_state, parent_nonces, exec_config
    )
    if not exec_result.success:
        return ProposalResult(
            success=False,
            reason=f"EXECUTION_REJECTED: {exec_result.error_reason}",
        )

    tx_ids = [tx.tx_id() for tx in pending_transactions]
    tx_root = compute_tx_root(tx_ids)
    state_hash = exec_result.post_state.state_hash()

    header = BlockHeader.create_signed(
        chain_id=chain_id,
        height=state.height,
        round=state.round,
        parent_hash=parent_hash,
        tx_root=tx_root,
        state_hash=state_hash,
        proposer_pubkey=self_identity.public_key,
        proposer_privkey=self_identity.private_key,
    )

    # HEADER before BODY, to every peer, in the given order.
    for peer in peers:
        network.send(
            sender=self_node_id,
            receiver=peer,
            payload=header.signed_bytes(),
            logical_time=logical_time,
            height=state.height,
            round=state.round,
        )

    body_payload = encode_transaction_list(pending_transactions)
    for peer in peers:
        network.send(
            sender=self_node_id,
            receiver=peer,
            payload=body_payload,
            logical_time=logical_time,
            height=state.height,
            round=state.round,
        )

    return ProposalResult(success=True, header=header)


# ====================================================
# Timeout handling
# ====================================================

def schedule_proposal_timeout(
    state: ConsensusState,
    *,
    network: Network,
    self_identity: ValidatorIdentity,
    validator_node_ids: Sequence[str],
    current_logical_time: int,
    proposal_timeout: int,
) -> None:
    """
    Schedule this node's own proposal-timeout wakeup at
    current_logical_time + proposal_timeout, as a self-addressed
    Envelope carrying TIMEOUT_PROPOSAL_PAYLOAD.

    Only meaningful for a non-proposer (a proposer doesn't need to wait
    on itself) — the caller decides whether to call this at all.
    """
    self_node_id = validator_node_ids[self_identity.index]
    network.send(
        sender=self_node_id,
        receiver=self_node_id,
        payload=TIMEOUT_PROPOSAL_PAYLOAD,
        logical_time=current_logical_time + proposal_timeout,
        height=state.height,
        round=state.round,
    )


def handle_proposal_timeout(
    state: ConsensusState,
    *,
    network: Network,
    self_identity: ValidatorIdentity,
    validator_node_ids: Sequence[str],
    peers: Sequence[str],
    chain_id: str,
    logical_time: int,
    has_valid_proposal: bool,
) -> Optional[Vote]:
    """
    Called when a previously-scheduled TIMEOUT_PROPOSAL envelope is
    delivered back to this node.

    If a valid proposal WAS accepted before this fired: the timeout is
    stale, do nothing (return None).

    If NOT: sign and broadcast a PREVOTE for NIL (block_hash_or_nil =
    None) at the current (height, round).
    """
    if has_valid_proposal:
        return None

    self_node_id = validator_node_ids[self_identity.index]

    vote = Vote.create_signed(
        chain_id=chain_id,
        height=state.height,
        round=state.round,
        phase=PHASE_PREVOTE,
        block_hash_or_nil=None,
        validator_pubkey=self_identity.public_key,
        validator_privkey=self_identity.private_key,
    )

    for peer in peers:
        network.send(
            sender=self_node_id,
            receiver=peer,
            payload=vote.signed_bytes(),
            logical_time=logical_time,
            height=state.height,
            round=state.round,
        )

    return vote       

# ====================================================
# T4-04
# Prevote guard (F-35)
# ====================================================

def _has_later_round_prevote_quorum(
    state: ConsensusState,
    block_hash: bytes,
    validator_count: int,
) -> bool:
    """
    Return True iff block_hash already has a PREVOTE quorum
    in any round greater than state.locked_round.
    """

    if state.locked_round is None:
        return False

    r = state.locked_round + 1

    while r <= state.round:
        if state.prevotes.has_quorum(
            height=state.height,
            round=r,
            phase=PHASE_PREVOTE,
            n=validator_count,
            block_hash=block_hash,
        ):
            return True

        r += 1

    return False


def prevote_block_or_nil(
    state: ConsensusState,
    *,
    proposed_block_hash: bytes,
    validator_count: int,
) -> bytes | None:
    """
    F-35.

    Rules

    1. unlocked
           -> prevote proposed block

    2. locked on same block
           -> prevote proposed block

    3. locked on another block
           -> only prevote proposed block if it already has
              a later-round quorum

    4. otherwise
           -> prevote NIL
    """

    _check_hash(proposed_block_hash)

    #
    # unlocked
    #

    if state.locked_block_hash is None:
        return proposed_block_hash

    #
    # already locked on this block
    #

    if state.locked_block_hash == proposed_block_hash:
        return proposed_block_hash

    #
    # locked on another block
    #

    if _has_later_round_prevote_quorum(
        state,
        proposed_block_hash,
        validator_count,
    ):
        return proposed_block_hash

    #
    # otherwise vote NIL
    #

    return None


def make_prevote(
    state: ConsensusState,
    *,
    chain_id: str,
    self_identity: ValidatorIdentity,
    proposed_block_hash: bytes,
    validator_count: int,
) -> Vote:
    """
    Produce one PREVOTE according to F-35.

    The vote is stored in ConsensusState.prevotes before returning.
    """

    target = prevote_block_or_nil(
        state,
        proposed_block_hash=proposed_block_hash,
        validator_count=validator_count,
    )

    vote = Vote.create_signed(
        chain_id=chain_id,
        height=state.height,
        round=state.round,
        phase=PHASE_PREVOTE,
        block_hash_or_nil=target,
        validator_pubkey=self_identity.public_key,
        validator_privkey=self_identity.private_key,
    )

    state.prevotes.add(vote)

    return vote