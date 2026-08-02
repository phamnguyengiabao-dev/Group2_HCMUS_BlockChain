import pytest

from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
)
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    PublicFormat,
)

from src.block import BlockHeader, compute_tx_root
from src.ledger import Ledger
from src.state import State


CHAIN_ID = "test-chain"


def make_key_pair() -> tuple[bytes, bytes]:
    private_key_object = Ed25519PrivateKey.generate()
    private_key = private_key_object.private_bytes_raw()
    public_key = private_key_object.public_key().public_bytes(
        Encoding.Raw, PublicFormat.Raw
    )
    return private_key, public_key


def make_header(
    height: int,
    parent_hash: bytes,
    private_key: bytes,
    public_key: bytes,
    state: State | None = None,
) -> BlockHeader:
    state = state if state is not None else State()

    return BlockHeader.create_signed(
        chain_id=CHAIN_ID,
        height=height,
        round=0,
        parent_hash=parent_hash,
        tx_root=compute_tx_root([]),
        state_hash=state.state_hash(),
        proposer_pubkey=public_key,
        proposer_privkey=private_key,
    )


def make_ledger_with_genesis() -> tuple[Ledger, tuple[bytes, bytes], BlockHeader]:
    """A ledger with height 1 already finalized on an empty state."""
    private_key, public_key = make_key_pair()
    ledger = Ledger(CHAIN_ID)

    header_1 = make_header(1, b"\x00" * 32, private_key, public_key)
    ledger.finalize(
        header=header_1,
        applied_tx_ids=[],
        state=State(),
        nonces={},
    )

    return ledger, (private_key, public_key), header_1


# ============================================================
# Append-only sequencing
# ============================================================

def test_finalize_first_block_at_height_one():
    private_key, public_key = make_key_pair()
    ledger = Ledger(CHAIN_ID)

    header_1 = make_header(1, b"\x00" * 32, private_key, public_key)
    entry = ledger.finalize(
        header=header_1,
        applied_tx_ids=[],
        state=State(),
        nonces={},
    )

    assert entry.height == 1
    assert ledger.finalized_height == 1
    assert ledger.finalized_hash == header_1.block_hash()


def test_finalize_appends_sequential_heights():
    ledger, (private_key, public_key), header_1 = make_ledger_with_genesis()

    header_2 = make_header(
        2, header_1.block_hash(), private_key, public_key
    )
    ledger.finalize(
        header=header_2,
        applied_tx_ids=[],
        state=State(),
        nonces={},
    )

    assert ledger.finalized_height == 2
    assert ledger.finalized_hash == header_2.block_hash()
    assert len(ledger) == 2


def test_rejects_gap_in_height():
    ledger, (private_key, public_key), header_1 = make_ledger_with_genesis()

    header_3 = make_header(
        3, header_1.block_hash(), private_key, public_key
    )

    with pytest.raises(ValueError, match="NON_SEQUENTIAL_HEIGHT"):
        ledger.finalize(
            header=header_3,
            applied_tx_ids=[],
            state=State(),
            nonces={},
        )


def test_rejects_refinalizing_same_height():
    ledger, (private_key, public_key), header_1 = make_ledger_with_genesis()

    duplicate_header_1 = make_header(
        1, b"\x00" * 32, private_key, public_key
    )

    with pytest.raises(ValueError, match="NON_SEQUENTIAL_HEIGHT"):
        ledger.finalize(
            header=duplicate_header_1,
            applied_tx_ids=[],
            state=State(),
            nonces={},
        )

    # The original entry must be untouched.
    assert ledger.finalized_height == 1
    assert ledger.finalized_hash == header_1.block_hash()


def test_rejects_going_backward():
    ledger, (private_key, public_key), header_1 = make_ledger_with_genesis()

    header_2 = make_header(
        2, header_1.block_hash(), private_key, public_key
    )
    ledger.finalize(
        header=header_2, applied_tx_ids=[], state=State(), nonces={}
    )

    stale_header_2 = make_header(
        2, header_1.block_hash(), private_key, public_key
    )

    with pytest.raises(ValueError, match="NON_SEQUENTIAL_HEIGHT"):
        ledger.finalize(
            header=stale_header_2,
            applied_tx_ids=[],
            state=State(),
            nonces={},
        )


def test_rejects_wrong_chain_id():
    ledger = Ledger(CHAIN_ID)
    private_key, public_key = make_key_pair()

    other_chain_header = BlockHeader.create_signed(
        chain_id="other-chain",
        height=1,
        round=0,
        parent_hash=b"\x00" * 32,
        tx_root=compute_tx_root([]),
        state_hash=State().state_hash(),
        proposer_pubkey=public_key,
        proposer_privkey=private_key,
    )

    with pytest.raises(ValueError, match="CHAIN_ID_MISMATCH"):
        ledger.finalize(
            header=other_chain_header,
            applied_tx_ids=[],
            state=State(),
            nonces={},
        )


def test_rejects_parent_hash_mismatch():
    ledger, (private_key, public_key), header_1 = make_ledger_with_genesis()

    forked_header_2 = make_header(
        2, b"\xff" * 32, private_key, public_key
    )

    with pytest.raises(ValueError, match="PARENT_HASH_MISMATCH"):
        ledger.finalize(
            header=forked_header_2,
            applied_tx_ids=[],
            state=State(),
            nonces={},
        )


# ============================================================
# No delete/update API
# ============================================================

def test_ledger_exposes_no_mutation_methods():
    for forbidden in ("delete", "remove", "pop", "clear", "update", "rollback"):
        assert not hasattr(Ledger, forbidden)


# ============================================================
# State snapshot behavior
# ============================================================

def test_get_state_reflects_state_at_finalize_time():
    ledger = Ledger(CHAIN_ID)
    private_key, public_key = make_key_pair()

    state = State()
    state.insert("k", b"v")

    header_1 = make_header(1, b"\x00" * 32, private_key, public_key, state)
    ledger.finalize(
        header=header_1, applied_tx_ids=[], state=state, nonces={}
    )

    stored_state = ledger.get_state(1)
    assert stored_state.get("k") == b"v"
    assert stored_state.state_hash() == state.state_hash()


def test_mutating_caller_state_after_finalize_does_not_affect_ledger():
    ledger = Ledger(CHAIN_ID)
    private_key, public_key = make_key_pair()

    state = State()
    header_1 = make_header(1, b"\x00" * 32, private_key, public_key, state)
    original_hash = state.state_hash()

    ledger.finalize(
        header=header_1, applied_tx_ids=[], state=state, nonces={}
    )

    # Mutate the caller's copy after the fact.
    state.insert("late", b"write")

    assert ledger.get_state(1).state_hash() == original_hash
    assert not ledger.get_state(1).has("late")


def test_mutating_returned_state_does_not_affect_ledger():
    ledger, _, _ = make_ledger_with_genesis()

    returned_state = ledger.get_state(1)
    returned_state.insert("hack", b"value")

    assert not ledger.get_state(1).has("hack")


def test_mutating_returned_nonces_does_not_affect_ledger():
    ledger = Ledger(CHAIN_ID)
    private_key, public_key = make_key_pair()

    header_1 = make_header(1, b"\x00" * 32, private_key, public_key)
    ledger.finalize(
        header=header_1,
        applied_tx_ids=[],
        state=State(),
        nonces={public_key: 3},
    )

    returned_nonces = ledger.get_nonces(1)
    returned_nonces[public_key] = 999

    assert ledger.get_nonces(1)[public_key] == 3


def test_applied_tx_ids_are_stored_and_immutable_type():
    ledger = Ledger(CHAIN_ID)
    private_key, public_key = make_key_pair()

    header_1 = make_header(1, b"\x00" * 32, private_key, public_key)
    fake_tx_id = b"\x11" * 32

    entry = ledger.finalize(
        header=header_1,
        applied_tx_ids=[fake_tx_id],
        state=State(),
        nonces={},
    )

    assert entry.applied_tx_ids == (fake_tx_id,)
    assert isinstance(entry.applied_tx_ids, tuple)


# ============================================================
# Read accessors
# ============================================================

def test_is_finalized_and_contains():
    ledger, _, _ = make_ledger_with_genesis()

    assert ledger.is_finalized(1)
    assert 1 in ledger
    assert not ledger.is_finalized(2)
    assert 2 not in ledger


def test_get_entry_missing_height_raises_key_error():
    ledger, _, _ = make_ledger_with_genesis()

    with pytest.raises(KeyError):
        ledger.get_entry(2)


def test_empty_ledger_has_no_finalized_hash():
    ledger = Ledger(CHAIN_ID)

    assert ledger.finalized_height == 0
    assert ledger.finalized_hash is None
    assert len(ledger) == 0


def test_iteration_is_in_ascending_height_order():
    ledger, (private_key, public_key), header_1 = make_ledger_with_genesis()

    header_2 = make_header(2, header_1.block_hash(), private_key, public_key)
    ledger.finalize(
        header=header_2, applied_tx_ids=[], state=State(), nonces={}
    )
    header_3 = make_header(3, header_2.block_hash(), private_key, public_key)
    ledger.finalize(
        header=header_3, applied_tx_ids=[], state=State(), nonces={}
    )

    assert list(ledger) == [1, 2, 3]
