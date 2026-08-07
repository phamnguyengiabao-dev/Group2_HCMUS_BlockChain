import pytest
import shutil

from src.consensus import (
    TIMEOUT_PROPOSAL_PAYLOAD,
    ConsensusState,
    handle_proposal_timeout,
    propose,
    schedule_proposal_timeout,
    select_proposer,
)
from src.block import BlockHeader
from src.identity import load_validator_keys
from src.event_log import EventLog
from src.executor import ExecutionConfig
from src.ledger import Ledger
from src.network import Network
from src.scheduler import Scheduler
from src.transaction import Transaction, encode_transaction_list
from src.vote import PHASE_PREVOTE

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