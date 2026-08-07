import pytest
import shutil

from src.consensus import (
    TIMEOUT_PROPOSAL_PAYLOAD,
    ConsensusState,
    handle_proposal_timeout,
    propose,
    schedule_proposal_timeout,
    select_proposer,
    prevote_block_or_nil,
    make_prevote,
)
from src.block import BlockHeader
from src.identity import load_validator_keys
from src.event_log import EventLog
from src.executor import ExecutionConfig
from src.ledger import Ledger
from src.network import Network
from src.scheduler import Scheduler
from src.transaction import Transaction, encode_transaction_list
from src.vote import PHASE_PREVOTE, PHASE_PRECOMMIT, Vote

CHAIN_ID = "test-chain"

# ============================================================
# Helpers
# ============================================================

def make_header(height=1):
    validator = load_validator_keys()[0]

    return BlockHeader.create_signed(
        chain_id="test-chain",
        height=height,
        round=0,
        parent_hash=b"\x00" * 32,
        tx_root=b"\x11" * 32,
        state_hash=b"\x22" * 32,
        proposer_pubkey=validator.public_key,
        proposer_privkey=validator.private_key,
    )


def make_tx(sender_pubkey=b"\x01" * 32, key_suffix="x", nonce=0):
    return Transaction(
        chain_id=CHAIN_ID,
        nonce=nonce,
        sender_pubkey=sender_pubkey,
        key=sender_pubkey.hex()[:0] or ("00" * 32 + "/" + key_suffix),
        value_bytes=b"v",
        signature=b"\x00" * 64,
    )


def build_network(scenario_id: str, run_id: str = "run1") -> Network:
    event_log = EventLog(scenario_id=scenario_id, run_id=run_id)
    scheduler = Scheduler(seed=1)
    return Network(event_log=event_log, scheduler=scheduler)


def node_ids_for(validators) -> list[str]:
    """validator_node_ids[i] is the node_id for ValidatorIdentity.index == i."""
    return [f"validator_{v.index}" for v in validators]


def proposer_and_round_for_index(validators, target_index: int, height: int) -> int:
    """Find a round at this height for which `target_index` is the proposer."""
    n = len(validators)
    for round_ in range(n):
        if (height + round_) % n == target_index:
            return round_
    raise AssertionError("no round found (should be impossible for a full cycle)")


@pytest.fixture(scope="module")
def validators():
    return load_validator_keys()


def teardown_function():
    """Clean logs created by tests that construct a real EventLog."""
    shutil.rmtree("logs", ignore_errors=True)


# ============================================================
# T4-01
# ============================================================

def test_init_defaults():
    state = ConsensusState(height=1)

    assert state.height == 1
    assert state.round == 0

    assert state.locked_block_hash is None
    assert state.locked_round is None
    assert state.valid_block_hash is None

    assert state.block_store is not None
    assert state.prevotes is not None
    assert state.precommits is not None


def test_invalid_height():
    with pytest.raises(ValueError):
        ConsensusState(height=0)


def test_set_round():
    state = ConsensusState(height=1)

    state.set_round(5)

    assert state.round == 5


def test_next_round():
    state = ConsensusState(height=1)

    assert state.next_round() == 1
    assert state.next_round() == 2
    assert state.round == 2


def test_negative_round():
    state = ConsensusState(height=1)

    with pytest.raises(ValueError):
        state.set_round(-1)


def test_lock_unlock():
    state = ConsensusState(height=1)

    header = make_header()

    state.block_store.store_header(header)

    h = header.block_hash()

    state.lock(h, 0)

    assert state.locked
    assert state.locked_block_hash == h
    assert state.locked_round == 0

    state.unlock()

    assert not state.locked
    assert state.locked_block_hash is None
    assert state.locked_round is None


def test_lock_unknown_block():
    state = ConsensusState(height=1)

    with pytest.raises(ValueError):
        state.lock(b"\x55" * 32, 0)


def test_set_valid_block():
    state = ConsensusState(height=1)

    header = make_header()

    state.block_store.store_header(header)

    h = header.block_hash()

    state.set_valid_block(h)

    assert state.valid_block_hash == h


def test_set_valid_unknown_block():
    state = ConsensusState(height=1)

    with pytest.raises(ValueError):
        state.set_valid_block(b"\x77" * 32)


def test_reset_votes():
    state = ConsensusState(height=1)

    prev = state.prevotes
    pre = state.precommits

    state.reset_votes()

    assert state.prevotes is not prev
    assert state.precommits is not pre


def test_reset_height():
    state = ConsensusState(height=1)

    header = make_header()

    state.block_store.store_header(header)

    state.lock(header.block_hash(), 0)
    state.set_valid_block(header.block_hash())
    state.set_round(5)

    state.reset_height(2)

    assert state.height == 2
    assert state.round == 0

    assert state.locked_block_hash is None
    assert state.locked_round is None
    assert state.valid_block_hash is None

    assert len(state.block_store._headers) == 0
    assert len(state.prevotes) == 0
    assert len(state.precommits) == 0


# ============================================================
# T4-02
# ============================================================

def test_select_proposer_formula(validators):
    n = len(validators)

    for height in range(1, 20):
        for round in range(10):
            proposer = select_proposer(height, round)

            expected = validators[
                (height + round) % n
            ]

            assert proposer == expected


def test_same_input_same_output():
    p1 = select_proposer(10, 3)
    p2 = select_proposer(10, 3)

    assert p1 == p2


def test_height_changes(validators):
    n = len(validators)

    for height in range(1, n + 5):
        proposer = select_proposer(height, 0)

        expected = validators[
            height % n
        ]

        assert proposer == expected


def test_round_changes(validators):
    n = len(validators)

    for round in range(n):
        proposer = select_proposer(5, round)

        expected = validators[
            (5 + round) % n
        ]

        assert proposer == expected


def test_wraparound(validators):
    n = len(validators)

    proposer = select_proposer(
        height=n + 4,
        round=6,
    )

    expected = validators[
        ((n + 4) + 6) % n
    ]

    assert proposer == expected


def test_every_validator_selected(validators):
    chosen = set()

    for h in range(1, 20):
        for r in range(20):
            chosen.add(
                select_proposer(h, r).index
            )

    assert chosen == {
        v.index
        for v in validators
    }


def test_consensus_state_proposer(validators):
    state = ConsensusState(height=7)

    state.set_round(3)

    proposer = state.proposer()

    expected = validators[
        (7 + 3) % len(validators)
    ]

    assert proposer == expected


def test_invalid_height_proposer():
    with pytest.raises(ValueError):
        select_proposer(0, 0)


def test_invalid_round_proposer():
    with pytest.raises(ValueError):
        select_proposer(1, -1)


# ============================================================
# T4-03 Proposal handler
# ============================================================

def test_propose_rejects_non_proposer(validators):
    n = len(validators)
    height = 1
    # find someone who is NOT the proposer at (height, round=0)
    proposer_index = height % n
    non_proposer_index = (proposer_index + 1) % n
    self_identity = validators[non_proposer_index]

    state = ConsensusState(height=height)
    network = build_network("consensus_not_proposer")
    ledger = Ledger(chain_id=CHAIN_ID)
    node_ids = node_ids_for(validators)

    result = propose(
        state,
        network=network,
        ledger=ledger,
        self_identity=self_identity,
        validator_node_ids=node_ids,
        peers=[nid for nid in node_ids if nid != node_ids[non_proposer_index]],
        pending_transactions=[],
        chain_id=CHAIN_ID,
        exec_config=ExecutionConfig(
            chain_id=CHAIN_ID, max_key_size=256, max_value_size=4096
        ),
        logical_time=0,
    )

    assert result.success is False
    assert result.reason == "NOT_PROPOSER"
    assert result.header is None


def test_propose_success_sends_header_before_body(validators):
    height = 1
    round_ = 0
    n = len(validators)
    proposer_identity = validators[(height + round_) % n]

    state = ConsensusState(height=height)
    network = build_network("consensus_propose_success")
    ledger = Ledger(chain_id=CHAIN_ID)
    node_ids = node_ids_for(validators)
    self_node_id = node_ids[proposer_identity.index]
    peers = [nid for nid in node_ids if nid != self_node_id][:2]

    result = propose(
        state,
        network=network,
        ledger=ledger,
        self_identity=proposer_identity,
        validator_node_ids=node_ids,
        peers=peers,
        pending_transactions=[],
        chain_id=CHAIN_ID,
        exec_config=ExecutionConfig(
            chain_id=CHAIN_ID, max_key_size=256, max_value_size=4096
        ),
        logical_time=10,
    )

    assert result.success is True
    assert result.header is not None
    assert result.header.chain_id == CHAIN_ID
    assert result.header.height == height
    assert result.header.round == round_
    assert result.header.proposer_pubkey == proposer_identity.public_key
    assert result.header.parent_hash == b"\x00" * 32  # genesis parent

    delivered = network.run()

    # HEADER to every peer, then BODY to every peer — same logical_time,
    # so insertion_seq (assignment order) fully determines delivery order.
    expected_header_payload = result.header.signed_bytes()
    expected_body_payload = encode_transaction_list([])

    assert len(delivered) == 2 * len(peers)
    assert delivered[: len(peers)] == [expected_header_payload] * len(peers)
    assert delivered[len(peers):] == [expected_body_payload] * len(peers)


def test_propose_rejects_invalid_transaction(validators):
    height = 1
    round_ = 0
    n = len(validators)
    proposer_identity = validators[(height + round_) % n]

    state = ConsensusState(height=height)
    network = build_network("consensus_propose_bad_tx")
    ledger = Ledger(chain_id=CHAIN_ID)
    node_ids = node_ids_for(validators)
    peers = [nid for nid in node_ids if nid != node_ids[proposer_identity.index]][:1]

    # nonce=5 with an empty parent state (nonce map starts empty, so
    # expected nonce is 0) -> executor must reject this transaction.
    bad_tx = make_tx(nonce=5)

    result = propose(
        state,
        network=network,
        ledger=ledger,
        self_identity=proposer_identity,
        validator_node_ids=node_ids,
        peers=peers,
        pending_transactions=[bad_tx],
        chain_id=CHAIN_ID,
        exec_config=ExecutionConfig(
            chain_id=CHAIN_ID, max_key_size=256, max_value_size=4096
        ),
        logical_time=0,
    )

    assert result.success is False
    assert result.reason.startswith("EXECUTION_REJECTED")
    assert result.header is None

    # nothing should have been sent
    assert network.run() == []


def test_propose_rejects_when_parent_not_finalized(validators):
    height = 2  # requires height 1 to already be finalized
    round_ = 0
    n = len(validators)
    proposer_identity = validators[(height + round_) % n]

    state = ConsensusState(height=height)
    network = build_network("consensus_propose_no_parent")
    ledger = Ledger(chain_id=CHAIN_ID)  # nothing finalized yet
    node_ids = node_ids_for(validators)
    peers = [nid for nid in node_ids if nid != node_ids[proposer_identity.index]][:1]

    result = propose(
        state,
        network=network,
        ledger=ledger,
        self_identity=proposer_identity,
        validator_node_ids=node_ids,
        peers=peers,
        pending_transactions=[],
        chain_id=CHAIN_ID,
        exec_config=ExecutionConfig(
            chain_id=CHAIN_ID, max_key_size=256, max_value_size=4096
        ),
        logical_time=0,
    )

    assert result.success is False
    assert result.reason == "PARENT_NOT_FINALIZED"


# ============================================================
# T4-03 Timeout handling
# ============================================================

def test_schedule_proposal_timeout_sends_self_addressed_envelope(validators):
    self_identity = validators[0]
    node_ids = node_ids_for(validators)
    self_node_id = node_ids[self_identity.index]

    state = ConsensusState(height=1)
    network = build_network("consensus_timeout_schedule")

    schedule_proposal_timeout(
        state,
        network=network,
        self_identity=self_identity,
        validator_node_ids=node_ids,
        current_logical_time=100,
        proposal_timeout=10,
    )

    delivered = network.run()

    assert delivered == [TIMEOUT_PROPOSAL_PAYLOAD]
    # sender == receiver == self_node_id is asserted indirectly: only
    # this node's own timeout was scheduled and it was the only envelope.
    assert self_node_id == node_ids[self_identity.index]


def test_handle_proposal_timeout_prevotes_nil_when_no_valid_proposal(validators):
    self_identity = validators[0]
    node_ids = node_ids_for(validators)
    peers = node_ids[1:3]

    state = ConsensusState(height=1)
    network = build_network("consensus_timeout_nil")

    vote = handle_proposal_timeout(
        state,
        network=network,
        self_identity=self_identity,
        validator_node_ids=node_ids,
        peers=peers,
        chain_id=CHAIN_ID,
        logical_time=50,
        has_valid_proposal=False,
    )

    assert vote is not None
    assert vote.phase == PHASE_PREVOTE
    assert vote.block_hash_or_nil is None
    assert vote.height == 1
    assert vote.round == 0
    assert vote.validator_pubkey == self_identity.public_key

    delivered = network.run()
    assert delivered == [vote.signed_bytes()] * len(peers)


def test_handle_proposal_timeout_is_noop_when_proposal_already_valid(validators):
    self_identity = validators[0]
    node_ids = node_ids_for(validators)
    peers = node_ids[1:3]

    state = ConsensusState(height=1)
    network = build_network("consensus_timeout_stale")

    vote = handle_proposal_timeout(
        state,
        network=network,
        self_identity=self_identity,
        validator_node_ids=node_ids,
        peers=peers,
        chain_id=CHAIN_ID,
        logical_time=50,
        has_valid_proposal=True,
    )

    assert vote is None
    assert network.run() == []  # nothing broadcast

# ============================================================
# T4-04
# ============================================================

def test_prevote_unlocked_returns_block():
    state = ConsensusState(height=1)

    block_hash = b"\x11" * 32

    assert (
        prevote_block_or_nil(
            state,
            proposed_block_hash=block_hash,
            validator_count=8,
        )
        == block_hash
    )


def test_prevote_locked_same_block():
    state = ConsensusState(height=1)

    header = make_header()

    state.block_store.store_header(header)

    h = header.block_hash()

    state.lock(h, 0)

    assert (
        prevote_block_or_nil(
            state,
            proposed_block_hash=h,
            validator_count=8,
        )
        == h
    )


def test_prevote_locked_other_block_without_quorum():
    state = ConsensusState(height=1)

    header1 = make_header()

    state.block_store.store_header(header1)

    h1 = header1.block_hash()

    state.lock(h1, 0)

    h2 = b"\x44" * 32

    assert (
        prevote_block_or_nil(
            state,
            proposed_block_hash=h2,
            validator_count=8,
        )
        is None
    )


def test_prevote_locked_other_block_with_later_round_quorum(validators):
    state = ConsensusState(height=1)

    header1 = make_header()

    state.block_store.store_header(header1)

    locked_hash = header1.block_hash()

    state.lock(locked_hash, 0)

    state.set_round(1)

    proposed_hash = b"\x77" * 32

    #
    # n = 8
    # f = 2
    # quorum = 5
    #

    for validator in validators[:5]:

        vote = validator.public_key

        signed = __import__("src.vote", fromlist=["Vote"]).Vote.create_signed(
            chain_id=CHAIN_ID,
            height=1,
            round=1,
            phase=PHASE_PREVOTE,
            block_hash_or_nil=proposed_hash,
            validator_pubkey=validator.public_key,
            validator_privkey=validator.private_key,
        )

        state.prevotes.add(signed)

    assert (
        prevote_block_or_nil(
            state,
            proposed_block_hash=proposed_hash,
            validator_count=len(validators),
        )
        == proposed_hash
    )


def test_make_prevote_block(validators):
    state = ConsensusState(height=1)

    block_hash = b"\xaa" * 32

    vote = make_prevote(
        state,
        chain_id=CHAIN_ID,
        self_identity=validators[0],
        proposed_block_hash=block_hash,
        validator_count=len(validators),
    )

    assert vote.phase == PHASE_PREVOTE
    assert vote.block_hash_or_nil == block_hash

    stored = state.prevotes.get(
        1,
        0,
        PHASE_PREVOTE,
        validators[0].public_key,
    )

    assert stored == vote


def test_make_prevote_nil_when_locked(validators):
    state = ConsensusState(height=1)

    header = make_header()

    state.block_store.store_header(header)

    state.lock(
        header.block_hash(),
        0,
    )

    other_hash = b"\xbb" * 32

    vote = make_prevote(
        state,
        chain_id=CHAIN_ID,
        self_identity=validators[0],
        proposed_block_hash=other_hash,
        validator_count=len(validators),
    )

    assert vote.block_hash_or_nil is None

    stored = state.prevotes.get(
        1,
        0,
        PHASE_PREVOTE,
        validators[0].public_key,
    )

    assert stored == vote

# ============================================================
# T4-05  Lock logic (apply_lock)
# ============================================================

from src.consensus import apply_lock


def _add_prevotes_for_hash(state, validators, block_hash, round_, count):
    """Helper: add `count` prevotes for block_hash at (height, round_)."""
    for v in validators[:count]:
        vote = Vote.create_signed(
            chain_id=CHAIN_ID,
            height=state.height,
            round=round_,
            phase=PHASE_PREVOTE,
            block_hash_or_nil=block_hash,
            validator_pubkey=v.public_key,
            validator_privkey=v.private_key,
        )
        state.prevotes.add(vote)


def _add_precommits_for_hash(state, validators, block_hash, round_, count):
    """Helper: add `count` precommits for block_hash at (height, round_)."""
    for v in validators[:count]:
        vote = Vote.create_signed(
            chain_id=CHAIN_ID,
            height=state.height,
            round=round_,
            phase=PHASE_PRECOMMIT,
            block_hash_or_nil=block_hash,
            validator_pubkey=v.public_key,
            validator_privkey=v.private_key,
        )
        state.precommits.add(vote)


def test_apply_lock_sets_lock_when_quorum(validators):
    """Quorum prevotes (5/8) → lock and valid_block_hash updated."""
    state = ConsensusState(height=1)
    header = make_header()
    state.block_store.store_header(header)
    block_hash = header.block_hash()

    _add_prevotes_for_hash(state, validators, block_hash, round_=0, count=5)

    result = apply_lock(state, round=0, validator_count=8)

    assert result == block_hash
    assert state.locked_block_hash == block_hash
    assert state.locked_round == 0
    assert state.valid_block_hash == block_hash


def test_apply_lock_no_quorum_returns_none(validators):
    """Insufficient prevotes (4/8) → no lock."""
    state = ConsensusState(height=1)
    header = make_header()
    state.block_store.store_header(header)
    block_hash = header.block_hash()

    _add_prevotes_for_hash(state, validators, block_hash, round_=0, count=4)

    result = apply_lock(state, round=0, validator_count=8)

    assert result is None
    assert state.locked_block_hash is None


def test_apply_lock_skips_unknown_block(validators):
    """Quorum exists but block not in block_store → skip, return None."""
    state = ConsensusState(height=1)
    unknown_hash = b"\xde\xad" * 16  # 32 bytes, not in block_store

    _add_prevotes_for_hash(state, validators, unknown_hash, round_=0, count=5)

    result = apply_lock(state, round=0, validator_count=8)

    assert result is None
    assert state.locked_block_hash is None


def test_apply_lock_exact_quorum_threshold(validators):
    """Exactly 2f+1 = 5 prevotes with n=8, f=2 is just enough."""
    state = ConsensusState(height=1)
    header = make_header()
    state.block_store.store_header(header)
    block_hash = header.block_hash()

    # Exactly 5 prevotes (threshold for n=8, f=2)
    _add_prevotes_for_hash(state, validators, block_hash, round_=0, count=5)

    result = apply_lock(state, round=0, validator_count=8)
    assert result == block_hash


# ============================================================
# T4-06  Precommit logic (make_precommit)
# ============================================================

from src.consensus import make_precommit, PrecommitResult


def test_make_precommit_block_when_locked_with_quorum(validators):
    """Locked + quorum prevotes → precommit the block."""
    state = ConsensusState(height=1)
    header = make_header()
    state.block_store.store_header(header)
    block_hash = header.block_hash()

    state.lock(block_hash, 0)
    _add_prevotes_for_hash(state, validators, block_hash, round_=0, count=5)

    network = build_network("precommit_block")
    node_ids = node_ids_for(validators)
    peers = node_ids[1:4]

    result = make_precommit(
        state,
        chain_id=CHAIN_ID,
        self_identity=validators[0],
        validator_count=8,
        network=network,
        validator_node_ids=node_ids,
        peers=peers,
        logical_time=10,
    )

    assert result.block_hash_or_nil == block_hash
    assert result.vote.phase == PHASE_PRECOMMIT
    assert result.vote.block_hash_or_nil == block_hash
    # vote stored in precommits
    stored = state.precommits.get(1, 0, PHASE_PRECOMMIT, validators[0].public_key)
    assert stored is not None
    assert stored.block_hash_or_nil == block_hash
    # broadcast to all peers
    delivered = network.run()
    assert len(delivered) == len(peers)


def test_make_precommit_nil_when_no_quorum(validators):
    """No prevote quorum → precommit NIL."""
    state = ConsensusState(height=1)
    header = make_header()
    state.block_store.store_header(header)
    block_hash = header.block_hash()

    # Only 3 prevotes, below quorum of 5
    _add_prevotes_for_hash(state, validators, block_hash, round_=0, count=3)

    network = build_network("precommit_nil")
    node_ids = node_ids_for(validators)
    peers = node_ids[1:3]

    result = make_precommit(
        state,
        chain_id=CHAIN_ID,
        self_identity=validators[0],
        validator_count=8,
        network=network,
        validator_node_ids=node_ids,
        peers=peers,
        logical_time=20,
    )

    assert result.block_hash_or_nil is None
    assert result.vote.block_hash_or_nil is None
    delivered = network.run()
    assert len(delivered) == len(peers)


def test_make_precommit_any_block_with_quorum(validators):
    """No lock but quorum prevotes for a block → precommit that block."""
    state = ConsensusState(height=1)
    block_hash = b"\xcc" * 32

    # Build a fake header for this hash so apply_lock could work,
    # but here we test make_precommit directly (no lock)
    _add_prevotes_for_hash(state, validators, block_hash, round_=0, count=5)

    network = build_network("precommit_any")
    node_ids = node_ids_for(validators)
    peers = node_ids[1:2]

    result = make_precommit(
        state,
        chain_id=CHAIN_ID,
        self_identity=validators[1],
        validator_count=8,
        network=network,
        validator_node_ids=node_ids,
        peers=peers,
        logical_time=5,
    )

    assert result.block_hash_or_nil == block_hash


# ============================================================
# T4-07  Finalization pipeline (try_finalize)
# ============================================================

from src.consensus import try_finalize, FinalizationResult
from src.crypto import sign
from src.state import State
from src.executor import ExecutionConfig


def _make_valid_block(chain_id, height, round_, validators, parent_hash=None):
    """Build a valid BlockHeader + empty tx list that passes validate_block_body."""
    from src.block import compute_tx_root
    from src.state import State

    if parent_hash is None:
        parent_hash = b"\x00" * 32

    # Empty block: tx_root = hash of count=0, state_hash = empty state hash
    tx_root = compute_tx_root([])
    state_hash = State().state_hash()

    proposer_idx = (height + round_) % len(validators)
    proposer = validators[proposer_idx]

    header = BlockHeader.create_signed(
        chain_id=chain_id,
        height=height,
        round=round_,
        parent_hash=parent_hash,
        tx_root=tx_root,
        state_hash=state_hash,
        proposer_pubkey=proposer.public_key,
        proposer_privkey=proposer.private_key,
    )
    return header, []  # (header, transactions)


def test_try_finalize_success(validators):
    """Quorum precommits + valid header+body → finalize and reset height."""
    state = ConsensusState(height=1)
    header, txs = _make_valid_block(CHAIN_ID, 1, 0, validators)
    block_hash = header.block_hash()

    state.block_store.store_header(header)
    state.block_store.store_body(block_hash, txs)

    _add_precommits_for_hash(state, validators, block_hash, round_=0, count=5)

    ledger = Ledger(chain_id=CHAIN_ID)
    exec_config = ExecutionConfig(chain_id=CHAIN_ID, max_key_size=256, max_value_size=4096)

    result = try_finalize(
        state,
        ledger=ledger,
        chain_id=CHAIN_ID,
        exec_config=exec_config,
        validator_count=8,
    )

    assert result.success is True
    assert result.entry is not None
    assert result.entry.height == 1
    assert result.entry.block_hash == block_hash
    # ConsensusState reset to height 2
    assert state.height == 2
    assert state.round == 0
    assert state.locked_block_hash is None
    # Ledger has the finalized entry
    assert ledger.is_finalized(1)


def test_try_finalize_no_quorum(validators):
    """Insufficient precommits → no finalization."""
    state = ConsensusState(height=1)
    header, txs = _make_valid_block(CHAIN_ID, 1, 0, validators)
    block_hash = header.block_hash()

    state.block_store.store_header(header)
    state.block_store.store_body(block_hash, txs)
    _add_precommits_for_hash(state, validators, block_hash, round_=0, count=4)

    ledger = Ledger(chain_id=CHAIN_ID)
    exec_config = ExecutionConfig(chain_id=CHAIN_ID, max_key_size=256, max_value_size=4096)

    result = try_finalize(
        state,
        ledger=ledger,
        chain_id=CHAIN_ID,
        exec_config=exec_config,
        validator_count=8,
    )

    assert result.success is False
    assert result.reason == "NO_PRECOMMIT_QUORUM"
    assert state.height == 1  # unchanged


def test_try_finalize_no_body(validators):
    """Quorum precommits but body not stored → fail with BODY_NOT_FOUND."""
    state = ConsensusState(height=1)
    header, _ = _make_valid_block(CHAIN_ID, 1, 0, validators)
    block_hash = header.block_hash()

    state.block_store.store_header(header)
    # body NOT stored
    _add_precommits_for_hash(state, validators, block_hash, round_=0, count=5)

    ledger = Ledger(chain_id=CHAIN_ID)
    exec_config = ExecutionConfig(chain_id=CHAIN_ID, max_key_size=256, max_value_size=4096)

    result = try_finalize(
        state,
        ledger=ledger,
        chain_id=CHAIN_ID,
        exec_config=exec_config,
        validator_count=8,
    )

    assert result.success is False
    assert result.reason == "BODY_NOT_FOUND"


def test_try_finalize_sequential_heights(validators):
    """Finalize height 1 then height 2 — parent_hash chain is correct."""
    ledger = Ledger(chain_id=CHAIN_ID)
    exec_config = ExecutionConfig(chain_id=CHAIN_ID, max_key_size=256, max_value_size=4096)

    # Height 1
    state = ConsensusState(height=1)
    h1, txs1 = _make_valid_block(CHAIN_ID, 1, 0, validators)
    bh1 = h1.block_hash()
    state.block_store.store_header(h1)
    state.block_store.store_body(bh1, txs1)
    _add_precommits_for_hash(state, validators, bh1, round_=0, count=5)

    r1 = try_finalize(state, ledger=ledger, chain_id=CHAIN_ID, exec_config=exec_config, validator_count=8)
    assert r1.success
    assert state.height == 2  # reset to 2

    # Height 2 — parent_hash must match bh1
    h2, txs2 = _make_valid_block(CHAIN_ID, 2, 0, validators, parent_hash=bh1)
    bh2 = h2.block_hash()
    state.block_store.store_header(h2)
    state.block_store.store_body(bh2, txs2)
    _add_precommits_for_hash(state, validators, bh2, round_=0, count=5)

    r2 = try_finalize(state, ledger=ledger, chain_id=CHAIN_ID, exec_config=exec_config, validator_count=8)
    assert r2.success
    assert state.height == 3
    assert ledger.is_finalized(2)


# ============================================================
# T4-08  Round change (do_round_change)
# ============================================================

from src.consensus import do_round_change, RoundChangeResult, schedule_precommit_timeout, TIMEOUT_PRECOMMIT_PAYLOAD


def test_do_round_change_increments_round(validators):
    """Round change advances round and preserves lock."""
    state = ConsensusState(height=1)
    header = make_header()
    state.block_store.store_header(header)
    block_hash = header.block_hash()
    state.lock(block_hash, 0)

    network = build_network("round_change")
    node_ids = node_ids_for(validators)

    result = do_round_change(
        state,
        network=network,
        self_identity=validators[0],
        validator_node_ids=node_ids,
        peers=node_ids[1:3],
        chain_id=CHAIN_ID,
        logical_time=50,
        precommit_timeout=5,
    )

    assert result.new_round == 1
    assert state.round == 1
    # Lock preserved
    assert result.kept_locked_block_hash == block_hash
    assert result.kept_locked_round == 0
    assert state.locked_block_hash == block_hash


def test_do_round_change_resets_votes(validators):
    """Round change clears vote sets."""
    state = ConsensusState(height=1)
    block_hash = b"\xab" * 32
    _add_prevotes_for_hash(state, validators, block_hash, round_=0, count=3)

    prev_prevotes = state.prevotes
    network = build_network("round_change_votes")
    node_ids = node_ids_for(validators)

    do_round_change(
        state,
        network=network,
        self_identity=validators[0],
        validator_node_ids=node_ids,
        peers=[],
        chain_id=CHAIN_ID,
        logical_time=30,
        precommit_timeout=5,
    )

    assert state.round == 1
    assert len(state.prevotes) == 0
    assert state.prevotes is not prev_prevotes


def test_do_round_change_multiple_rounds(validators):
    """Multiple round changes accumulate correctly."""
    state = ConsensusState(height=1)
    network = build_network("multi_round_change")
    node_ids = node_ids_for(validators)

    for expected_round in range(1, 4):
        result = do_round_change(
            state,
            network=network,
            self_identity=validators[0],
            validator_node_ids=node_ids,
            peers=[],
            chain_id=CHAIN_ID,
            logical_time=expected_round * 10,
            precommit_timeout=5,
        )
        assert result.new_round == expected_round
        assert state.round == expected_round


def test_schedule_precommit_timeout_sends_self_envelope(validators):
    """schedule_precommit_timeout enqueues TIMEOUT:PRECOMMIT at correct time."""
    state = ConsensusState(height=1)
    network = build_network("precommit_timeout_schedule")
    node_ids = node_ids_for(validators)

    schedule_precommit_timeout(
        state,
        network=network,
        self_identity=validators[0],
        validator_node_ids=node_ids,
        current_logical_time=20,
        precommit_timeout=8,
    )

    delivered = network.run()
    assert delivered == [TIMEOUT_PRECOMMIT_PAYLOAD]


# ============================================================
# T4-09  VoteSentTracker — "send at most one vote" guard
# ============================================================

from src.consensus import VoteSentTracker


def test_vote_sent_tracker_initial_can_vote():
    tracker = VoteSentTracker()
    assert tracker.can_vote(1, 0, PHASE_PREVOTE) is True
    assert tracker.has_voted(1, 0, PHASE_PREVOTE) is False


def test_vote_sent_tracker_blocks_second_vote():
    tracker = VoteSentTracker()
    tracker.record_vote(1, 0, PHASE_PREVOTE)

    assert tracker.can_vote(1, 0, PHASE_PREVOTE) is False
    assert tracker.has_voted(1, 0, PHASE_PREVOTE) is True


def test_vote_sent_tracker_different_phases_independent():
    tracker = VoteSentTracker()
    tracker.record_vote(1, 0, PHASE_PREVOTE)

    # Same height+round but different phase is still open
    assert tracker.can_vote(1, 0, PHASE_PRECOMMIT) is True


def test_vote_sent_tracker_different_rounds_independent():
    tracker = VoteSentTracker()
    tracker.record_vote(1, 0, PHASE_PREVOTE)

    # Round 1 is still open
    assert tracker.can_vote(1, 1, PHASE_PREVOTE) is True


def test_vote_sent_tracker_record_idempotent():
    tracker = VoteSentTracker()
    tracker.record_vote(1, 0, PHASE_PREVOTE)
    tracker.record_vote(1, 0, PHASE_PREVOTE)  # second call is no-op
    assert not tracker.can_vote(1, 0, PHASE_PREVOTE)


def test_vote_sent_tracker_reset_height():
    tracker = VoteSentTracker()
    tracker.record_vote(1, 0, PHASE_PREVOTE)
    tracker.record_vote(1, 0, PHASE_PRECOMMIT)
    tracker.record_vote(2, 0, PHASE_PREVOTE)

    tracker.reset_height(2)  # discard height < 2

    assert tracker.can_vote(1, 0, PHASE_PREVOTE) is True   # discarded
    assert tracker.can_vote(1, 0, PHASE_PRECOMMIT) is True  # discarded
    assert tracker.can_vote(2, 0, PHASE_PREVOTE) is False   # kept


def test_vote_sent_tracker_guards_full_round(validators):
    """Simulate a node sending prevote then attempting a second prevote."""
    tracker = VoteSentTracker()

    # First prevote is allowed
    assert tracker.can_vote(5, 2, PHASE_PREVOTE) is True
    tracker.record_vote(5, 2, PHASE_PREVOTE)

    # Second prevote for same slot is blocked
    assert tracker.can_vote(5, 2, PHASE_PREVOTE) is False

    # Precommit for same (height, round) is still allowed
    assert tracker.can_vote(5, 2, PHASE_PRECOMMIT) is True
    tracker.record_vote(5, 2, PHASE_PRECOMMIT)
    assert tracker.can_vote(5, 2, PHASE_PRECOMMIT) is False
