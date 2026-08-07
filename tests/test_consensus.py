import pytest

from src.consensus import (
    ConsensusState,
    select_proposer,
)
from src.block import BlockHeader
from src.identity import load_validator_keys


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


@pytest.fixture(scope="module")
def validators():
    return load_validator_keys()


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