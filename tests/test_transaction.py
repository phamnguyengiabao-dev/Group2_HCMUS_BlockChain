import pytest

from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
)
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    PublicFormat,
)

from src.crypto import hash_bytes, sign
from src.transaction import Transaction


CHAIN_ID = "test-chain"

MAX_KEY_SIZE = 512
MAX_VALUE_SIZE = 1024


def make_key_pair() -> tuple[bytes, bytes]:
    """
    Create an Ed25519 key pair.

    Returns:
        private_key_seed: 32 bytes
        public_key: 32 bytes
    """

    private_key_object = Ed25519PrivateKey.generate()

    private_key_seed = private_key_object.private_bytes_raw()

    public_key = (
        private_key_object.public_key()
        .public_bytes(
            Encoding.Raw,
            PublicFormat.Raw,
        )
    )

    return private_key_seed, public_key


def make_valid_transaction(
    private_key: bytes,
    public_key: bytes,
    nonce: int = 1,
    key_suffix: str = "balance",
    value: bytes = b"100",
) -> Transaction:
    """
    Create a correctly signed transaction.
    """

    namespace = (
        hash_bytes(public_key).hex()
        + "/"
    )

    key = namespace + key_suffix

    # Create unsigned transaction first.
    unsigned_tx = Transaction(
        chain_id=CHAIN_ID,
        nonce=nonce,
        sender_pubkey=public_key,
        key=key,
        value_bytes=value,
        signature=b"",
    )

    # Sign the canonical unsigned transaction.
    signature = sign(
        private_key,
        f"TX:{CHAIN_ID}",
        unsigned_tx.unsigned_bytes(),
    )

    # Create final signed transaction.
    return Transaction(
        chain_id=CHAIN_ID,
        nonce=nonce,
        sender_pubkey=public_key,
        key=key,
        value_bytes=value,
        signature=signature,
    )


def validate_transaction(
    transaction: Transaction,
    expected_nonce: int = 1,
) -> None:
    """
    Helper to validate a transaction with test limits.
    """

    transaction.validate(
        expected_chain_id=CHAIN_ID,
        expected_nonce=expected_nonce,
        max_key_size=MAX_KEY_SIZE,
        max_value_size=MAX_VALUE_SIZE,
    )


# ============================================================
# Valid transaction
# ============================================================

def test_valid_transaction():
    private_key, public_key = make_key_pair()

    transaction = make_valid_transaction(
        private_key,
        public_key,
    )

    # Test passes if no exception is raised.
    validate_transaction(transaction)


# ============================================================
# Transaction ID
# ============================================================

def test_transaction_id_is_32_bytes():
    private_key, public_key = make_key_pair()

    transaction = make_valid_transaction(
        private_key,
        public_key,
    )

    transaction_id = transaction.tx_id()

    assert isinstance(transaction_id, bytes)
    assert len(transaction_id) == 32


def test_transaction_id_is_deterministic():
    private_key, public_key = make_key_pair()

    transaction = make_valid_transaction(
        private_key,
        public_key,
    )

    assert (
        transaction.tx_id()
        == transaction.tx_id()
    )


# ============================================================
# Invalid chain ID
# ============================================================

def test_rejects_wrong_chain_id():
    private_key, public_key = make_key_pair()

    transaction = make_valid_transaction(
        private_key,
        public_key,
    )

    with pytest.raises(
        ValueError,
        match="INVALID_CHAIN_ID",
    ):
        transaction.validate(
            expected_chain_id="another-chain",
            expected_nonce=1,
            max_key_size=MAX_KEY_SIZE,
            max_value_size=MAX_VALUE_SIZE,
        )


# ============================================================
# Invalid nonce
# ============================================================

def test_rejects_wrong_nonce():
    private_key, public_key = make_key_pair()

    transaction = make_valid_transaction(
        private_key,
        public_key,
        nonce=5,
    )

    with pytest.raises(
        ValueError,
        match="INVALID_NONCE",
    ):
        validate_transaction(
            transaction,
            expected_nonce=1,
        )


# ============================================================
# Invalid namespace
# ============================================================

def test_rejects_wrong_namespace():
    private_key, public_key = make_key_pair()

    namespace = (
        hash_bytes(public_key).hex()
        + "/"
    )

    # Create transaction with invalid key.
    unsigned_tx = Transaction(
        chain_id=CHAIN_ID,
        nonce=1,
        sender_pubkey=public_key,
        key="wrong_namespace/balance",
        value_bytes=b"100",
        signature=b"",
    )

    signature = sign(
        private_key,
        f"TX:{CHAIN_ID}",
        unsigned_tx.unsigned_bytes(),
    )

    transaction = Transaction(
        chain_id=CHAIN_ID,
        nonce=1,
        sender_pubkey=public_key,
        key="wrong_namespace/balance",
        value_bytes=b"100",
        signature=signature,
    )

    with pytest.raises(
        ValueError,
        match="INVALID_NAMESPACE",
    ):
        validate_transaction(transaction)


# ============================================================
# Invalid signature
# ============================================================

def test_rejects_invalid_signature():
    private_key, public_key = make_key_pair()

    transaction = make_valid_transaction(
        private_key,
        public_key,
    )

    # Change one byte in the signature.
    bad_signature = (
        transaction.signature[:-1]
        + bytes([
            transaction.signature[-1] ^ 1
        ])
    )

    invalid_transaction = Transaction(
        chain_id=transaction.chain_id,
        nonce=transaction.nonce,
        sender_pubkey=transaction.sender_pubkey,
        key=transaction.key,
        value_bytes=transaction.value_bytes,
        signature=bad_signature,
    )

    with pytest.raises(
        ValueError,
        match="INVALID_SIGNATURE",
    ):
        validate_transaction(
            invalid_transaction
        )


# ============================================================
# Value too large
# ============================================================

def test_rejects_value_too_large():
    private_key, public_key = make_key_pair()

    transaction = make_valid_transaction(
        private_key,
        public_key,
        value=b"x" * 2000,
    )

    with pytest.raises(
        ValueError,
        match="VALUE_TOO_LARGE",
    ):
        validate_transaction(
            transaction
        )


# ============================================================
# Key too large
# ============================================================

def test_rejects_key_too_large():
    private_key, public_key = make_key_pair()

    transaction = make_valid_transaction(
        private_key,
        public_key,
        key_suffix="x" * 1000,
    )

    with pytest.raises(
        ValueError,
        match="KEY_TOO_LARGE",
    ):
        validate_transaction(
            transaction
        )