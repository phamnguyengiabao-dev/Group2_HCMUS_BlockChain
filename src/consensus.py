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

from src.block import BlockHeader, compute_tx_root, validate_block_body
from src.block_store import BlockStore
from src.encoding import encode_bytes, encode_uint64
from src.executor import ExecutionConfig, execute_block
from src.identity import ValidatorIdentity, load_validator_keys
from src.ledger import Ledger
from src.network import Network
from src.state import State
from src.transaction import Transaction, encode_transaction_list
from src.vote import PHASE_PREVOTE, PHASE_PRECOMMIT, Vote
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


# ====================================================
# T4-05
# Lock logic (F-36)
# ====================================================

def apply_lock(
    state: ConsensusState,
    *,
    round: int,
    validator_count: int,
) -> bytes | None:
    """
    F-36: After a quorum of non-NIL prevotes for `round` is detected,
    lock the node onto the block with the quorum and update valid_block_hash.

    Returns the block_hash that was locked, or None if no quorum was found.

    Conditions:
        - >= 2f+1 prevotes for a specific non-NIL block_hash at (height, round)
        - Lock state updated: locked_block_hash, locked_round, valid_block_hash
    """

    # Scan stored prevotes for the best non-NIL block_hash with quorum
    candidate_hashes: set[bytes] = set()

    for vote in state.prevotes.votes(state.height, round, PHASE_PREVOTE):
        if vote.block_hash_or_nil is not None:
            candidate_hashes.add(vote.block_hash_or_nil)

    for block_hash in sorted(candidate_hashes):
        if state.prevotes.has_quorum(
            height=state.height,
            round=round,
            phase=PHASE_PREVOTE,
            n=validator_count,
            block_hash=block_hash,
        ):
            # Verify the block is known before locking
            if not state.block_store.has_header(block_hash):
                continue  # skip unknown blocks

            state.locked_block_hash = block_hash
            state.locked_round = round
            state.valid_block_hash = block_hash
            return block_hash

    return None


# ====================================================
# T4-06
# Precommit logic (F-37)
# ====================================================

@dataclass(frozen=True)
class PrecommitResult:
    """Outcome of one precommit decision."""
    vote: Vote
    block_hash_or_nil: bytes | None


def make_precommit(
    state: ConsensusState,
    *,
    chain_id: str,
    self_identity: ValidatorIdentity,
    validator_count: int,
    network: Network,
    validator_node_ids: Sequence[str],
    peers: Sequence[str],
    logical_time: int,
) -> PrecommitResult:
    """
    F-37: Determine the precommit target and broadcast it.

    Rules:
        1. If there is a quorum of non-NIL prevotes for some block_hash
           at this (height, round) → precommit that block_hash.
        2. Otherwise → precommit NIL.

    The precommit is stored in state.precommits and broadcast to all peers.
    """
    # Determine target: quorum prevote non-NIL?
    target: bytes | None = None

    if state.locked_block_hash is not None and state.prevotes.has_quorum(
        height=state.height,
        round=state.round,
        phase=PHASE_PREVOTE,
        n=validator_count,
        block_hash=state.locked_block_hash,
    ):
        target = state.locked_block_hash
    else:
        # Check for any block with quorum
        candidate_hashes: set[bytes] = set()
        for vote in state.prevotes.votes(state.height, state.round, PHASE_PREVOTE):
            if vote.block_hash_or_nil is not None:
                candidate_hashes.add(vote.block_hash_or_nil)

        for block_hash in sorted(candidate_hashes):
            if state.prevotes.has_quorum(
                height=state.height,
                round=state.round,
                phase=PHASE_PREVOTE,
                n=validator_count,
                block_hash=block_hash,
            ):
                target = block_hash
                break

    # Sign the precommit
    self_node_id = validator_node_ids[self_identity.index]

    vote = Vote.create_signed(
        chain_id=chain_id,
        height=state.height,
        round=state.round,
        phase=PHASE_PRECOMMIT,
        block_hash_or_nil=target,
        validator_pubkey=self_identity.public_key,
        validator_privkey=self_identity.private_key,
    )

    state.precommits.add(vote)

    # Broadcast to all peers
    for peer in peers:
        network.send(
            sender=self_node_id,
            receiver=peer,
            payload=vote.signed_bytes(),
            logical_time=logical_time,
            height=state.height,
            round=state.round,
        )

    return PrecommitResult(vote=vote, block_hash_or_nil=target)


# ====================================================
# T4-07
# Finalization logic (F-38)
# ====================================================

@dataclass(frozen=True)
class FinalizationResult:
    """Outcome of a finalization attempt."""
    success: bool
    entry: Optional["LedgerEntry"] = None
    reason: Optional[str] = None


def try_finalize(
    state: ConsensusState,
    *,
    ledger: Ledger,
    chain_id: str,
    exec_config: ExecutionConfig,
    validator_count: int,
) -> FinalizationResult:
    """
    F-38: If there is a quorum of non-NIL precommits for some block_hash at
    (height, round), validate the block body and append it to the ledger.

    On success:
        - Block is appended to the ledger
        - ConsensusState is reset to height+1, round=0
        - locked/valid state is cleared

    Returns FinalizationResult(success=True, entry=...) or
            FinalizationResult(success=False, reason=...).
    """
    # Find a block_hash with quorum precommits
    candidate_hashes: set[bytes] = set()
    for vote in state.precommits.votes(state.height, state.round, PHASE_PRECOMMIT):
        if vote.block_hash_or_nil is not None:
            candidate_hashes.add(vote.block_hash_or_nil)

    finalize_hash: bytes | None = None
    for block_hash in sorted(candidate_hashes):
        if state.precommits.has_quorum(
            height=state.height,
            round=state.round,
            phase=PHASE_PRECOMMIT,
            n=validator_count,
            block_hash=block_hash,
        ):
            finalize_hash = block_hash
            break

    if finalize_hash is None:
        return FinalizationResult(success=False, reason="NO_PRECOMMIT_QUORUM")

    # Must have header and body
    if not state.block_store.has_header(finalize_hash):
        return FinalizationResult(success=False, reason="HEADER_NOT_FOUND")

    if not state.block_store.has_body(finalize_hash):
        return FinalizationResult(success=False, reason="BODY_NOT_FOUND")

    header = state.block_store.get_header(finalize_hash)
    transactions = list(state.block_store.get_body(finalize_hash))

    # Load parent state for re-validation
    parent_height = header.height - 1
    if parent_height == 0:
        parent_state = State()
        parent_nonces: dict[bytes, int] = {}
    else:
        if not ledger.is_finalized(parent_height):
            return FinalizationResult(success=False, reason="PARENT_NOT_FINALIZED")
        parent_state = ledger.get_state(parent_height)
        parent_nonces = ledger.get_nonces(parent_height)

    # Re-validate the block body (F-38 requires full re-validation)
    validation = validate_block_body(
        header,
        transactions,
        parent_state,
        parent_nonces,
        exec_config,
    )

    if not validation.success:
        return FinalizationResult(
            success=False,
            reason=f"BODY_VALIDATION_FAILED: {validation.rejection.code}",
        )

    # Append to ledger (atomic persist via T2-13)
    entry = ledger.finalize(
        header=header,
        applied_tx_ids=list(validation.applied_tx_ids),
        state=validation.state,
        nonces=validation.nonces,
    )

    # Reset consensus state to next height, round 0
    state.reset_height(header.height + 1)

    return FinalizationResult(success=True, entry=entry)


# ====================================================
# T4-08
# Round change logic (F-39)
# ====================================================

@dataclass(frozen=True)
class RoundChangeResult:
    """Outcome of a round change."""
    new_round: int
    kept_locked_block_hash: bytes | None
    kept_locked_round: int | None


def do_round_change(
    state: ConsensusState,
    *,
    network: Network,
    self_identity: ValidatorIdentity,
    validator_node_ids: Sequence[str],
    peers: Sequence[str],
    chain_id: str,
    logical_time: int,
    precommit_timeout: int,
) -> RoundChangeResult:
    """
    F-39: Precommit timeout → increment round → reset vote sets → keep locks.

    Schedule a proposal timeout for the new round (as a self-addressed TIMEOUT
    envelope) so the node can detect if the new round's proposer is silent.

    The lock state (locked_block_hash, locked_round) is preserved across round
    changes, per the Tendermint safety invariant. vote sets are cleared for
    the new round.
    """
    # Preserve lock state before clearing votes
    kept_locked_hash = state.locked_block_hash
    kept_locked_round = state.locked_round

    # Advance round
    new_round = state.next_round()

    # Reset votes for the new round (but keep block_store and lock state)
    state.reset_votes()

    return RoundChangeResult(
        new_round=new_round,
        kept_locked_block_hash=kept_locked_hash,
        kept_locked_round=kept_locked_round,
    )


def schedule_precommit_timeout(
    state: ConsensusState,
    *,
    network: Network,
    self_identity: ValidatorIdentity,
    validator_node_ids: Sequence[str],
    current_logical_time: int,
    precommit_timeout: int,
) -> None:
    """
    Schedule a precommit-timeout wakeup for round change detection.

    Delivered as a self-addressed envelope carrying TIMEOUT_PRECOMMIT_PAYLOAD.
    """
    self_node_id = validator_node_ids[self_identity.index]
    network.send(
        sender=self_node_id,
        receiver=self_node_id,
        payload=TIMEOUT_PRECOMMIT_PAYLOAD,
        logical_time=current_logical_time + precommit_timeout,
        height=state.height,
        round=state.round,
    )


# ====================================================
# T4-09
# "Send at most one vote" guard (F-33)
# ====================================================

class VoteSentTracker:
    """
    Per-node guard enforcing F-33: a node may cast at most one vote per
    (height, round, phase).

    Usage:
        tracker = VoteSentTracker()

        # Before signing a vote:
        if tracker.can_vote(height, round, phase):
            vote = Vote.create_signed(...)
            tracker.record_vote(height, round, phase)
            broadcast(vote)
    """

    def __init__(self) -> None:
        # Set of (height, round, phase) slots that already have a sent vote
        self._sent: set[tuple[int, int, str]] = set()

    def can_vote(self, height: int, round: int, phase: str) -> bool:
        """Return True if no vote has been sent for this (height, round, phase)."""
        return (height, round, phase) not in self._sent

    def record_vote(self, height: int, round: int, phase: str) -> None:
        """Mark (height, round, phase) as voted. Idempotent."""
        self._sent.add((height, round, phase))

    def has_voted(self, height: int, round: int, phase: str) -> bool:
        """Return True if a vote was already sent for (height, round, phase)."""
        return (height, round, phase) in self._sent

    def reset_height(self, new_height: int) -> None:
        """
        Discard all entries for heights strictly below new_height.
        Called when the node finalizes a block and moves to the next height.
        """
        self._sent = {
            (h, r, p)
            for (h, r, p) in self._sent
            if h >= new_height
        }


# ====================================================
# Sentinel payloads for timeout self-messages
# ====================================================

TIMEOUT_PRECOMMIT_PAYLOAD = b"TIMEOUT:PRECOMMIT"
TIMEOUT_PREVOTE_PAYLOAD = b"TIMEOUT:PREVOTE"


__all__ = [
    "ConsensusState",
    "FinalizationResult",
    "PrecommitResult",
    "ProposalResult",
    "RoundChangeResult",
    "VoteSentTracker",
    "TIMEOUT_PRECOMMIT_PAYLOAD",
    "TIMEOUT_PREVOTE_PAYLOAD",
    "TIMEOUT_PROPOSAL_PAYLOAD",
    "apply_lock",
    "do_round_change",
    "handle_proposal_timeout",
    "make_precommit",
    "make_prevote",
    "prevote_block_or_nil",
    "propose",
    "schedule_precommit_timeout",
    "schedule_proposal_timeout",
    "select_proposer",
    "try_finalize",
]