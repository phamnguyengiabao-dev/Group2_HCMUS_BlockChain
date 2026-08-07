"""
Transaction model and validation for the blockchain protocol.

T1-12:
- Transaction object
- Canonical transaction encoding
- Transaction ID
- Validation:
    * chain_id
    * nonce
    * sender namespace
    * key/value size limits
    * Ed25519 signature
"""

from __future__ import annotations

from dataclasses import dataclass
import unicodedata

from src.crypto import hash_bytes, verify
from src.encoding import (
    encode_bytes,
    encode_str,
    encode_uint64,
)


PUBLIC_KEY_LEN = 32
SIGNATURE_LEN = 64

# Need a corresponding decode function to parse it back into list[Transaction] when received.
def encode_transaction_list(transactions: list[Transaction]) -> bytes:
    """
    Count-prefixed list of each transaction's signed_bytes(), mirroring
    compute_tx_root's own count-prefix pattern:

        encode_uint64(count) || encode_bytes(tx[0].signed_bytes())
                              || encode_bytes(tx[1].signed_bytes())
                              || ...

    Each element is length-prefixed (via encode_bytes).
    """
    payload = bytearray(encode_uint64(len(transactions)))
    for tx in transactions:
        payload += encode_bytes(tx.signed_bytes())
    return bytes(payload)


@dataclass(frozen=True, slots=True)
class Transaction:
    """
    A blockchain transaction.

    Canonical field order:

        chain_id
        nonce
        sender_pubkey
        key
        value_bytes
        signature
    """

    chain_id: str
    nonce: int
    sender_pubkey: bytes
    key: str
    value_bytes: bytes
    signature: bytes

    def unsigned_bytes(self) -> bytes:
        """
        Return canonical bytes of the unsigned transaction.

        The signature is not included.
        """

        return (
            encode_str(self.chain_id)
            + encode_uint64(self.nonce)
            + encode_bytes(self.sender_pubkey)
            + encode_str(self.key)
            + encode_bytes(self.value_bytes)
        )

    def signed_bytes(self) -> bytes:
        """
        Return canonical bytes of the complete transaction.

        Field order:

            unsigned transaction fields
            || encoded signature
        """

        return (
            self.unsigned_bytes()
            + encode_bytes(self.signature)
        )

    def tx_id(self) -> bytes:
        """
        Compute the transaction ID.

        tx_id =
            SHA256(
                canonical unsigned transaction
                || signature
            )

        Returns:
            Raw 32-byte SHA-256 digest.
        """

        return hash_bytes(
            self.unsigned_bytes()
            + self.signature
        )

    def expected_namespace(self) -> str:
        """
        Return the namespace required for this sender.

        Format:

            hex(SHA256(sender_pubkey)) + "/"
        """

        return (
            hash_bytes(self.sender_pubkey).hex()
            + "/"
        )

    def validate(
        self,
        *,
        expected_chain_id: str,
        expected_nonce: int,
        max_key_size: int,
        max_value_size: int,
    ) -> None:
        """
        Validate the transaction.

        Raises:
            ValueError:
                If a protocol validation rule fails.

            TypeError:
                If a field has the wrong Python type.
        """

        # ---------------------------------------------
        # 1. Validate basic field types
        # ---------------------------------------------

        if not isinstance(self.chain_id, str):
            raise TypeError(
                "chain_id must be a string"
            )

        if not isinstance(self.nonce, int):
            raise TypeError(
                "nonce must be an integer"
            )

        if not isinstance(
            self.sender_pubkey,
            bytes,
        ):
            raise TypeError(
                "sender_pubkey must be bytes"
            )

        if not isinstance(self.key, str):
            raise TypeError(
                "key must be a string"
            )

        if not isinstance(
            self.value_bytes,
            bytes,
        ):
            raise TypeError(
                "value_bytes must be bytes"
            )

        if not isinstance(
            self.signature,
            bytes,
        ):
            raise TypeError(
                "signature must be bytes"
            )

        # ---------------------------------------------
        # 2. Validate chain ID
        # ---------------------------------------------

        if self.chain_id != expected_chain_id:
            raise ValueError(
                "INVALID_CHAIN_ID: "
                f"expected {expected_chain_id!r}, "
                f"got {self.chain_id!r}"
            )

        # ---------------------------------------------
        # 3. Validate nonce
        # ---------------------------------------------

        if self.nonce != expected_nonce:
            raise ValueError(
                "INVALID_NONCE: "
                f"expected {expected_nonce}, "
                f"got {self.nonce}"
            )

        # Check uint64 range too.
        if not (
            0 <= self.nonce < 2**64
        ):
            raise ValueError(
                "INVALID_NONCE_RANGE"
            )

        # ---------------------------------------------
        # 4. Validate public key length
        # ---------------------------------------------

        if len(self.sender_pubkey) != PUBLIC_KEY_LEN:
            raise ValueError(
                "INVALID_SENDER_PUBKEY: "
                "Ed25519 public key "
                "must be 32 bytes"
            )

        # ---------------------------------------------
        # 5. Validate signature length
        # ---------------------------------------------

        if len(self.signature) != SIGNATURE_LEN:
            raise ValueError(
                "INVALID_SIGNATURE_LENGTH: "
                "Ed25519 signature "
                "must be 64 bytes"
            )

        # ---------------------------------------------
        # 6. Validate key size
        # ---------------------------------------------

        normalized_key = (
            unicodedata.normalize(
                "NFC",
                self.key,
            )
        )

        key_size = len(
            normalized_key.encode("utf-8")
        )

        if key_size > max_key_size:
            raise ValueError(
                "KEY_TOO_LARGE: "
                f"{key_size} bytes exceeds "
                f"maximum {max_key_size}"
            )

        # ---------------------------------------------
        # 7. Validate value size
        # ---------------------------------------------

        value_size = len(
            self.value_bytes
        )

        if value_size > max_value_size:
            raise ValueError(
                "VALUE_TOO_LARGE: "
                f"{value_size} bytes exceeds "
                f"maximum {max_value_size}"
            )

        # ---------------------------------------------
        # 8. Validate sender namespace
        # ---------------------------------------------

        namespace = (
            self.expected_namespace()
        )

        if not normalized_key.startswith(
            namespace
        ):
            raise ValueError(
                "INVALID_NAMESPACE: "
                f"key must start with "
                f"{namespace!r}"
            )

        # ---------------------------------------------
        # 9. Verify Ed25519 signature
        # ---------------------------------------------

        expected_domain = (
            f"TX:{expected_chain_id}"
        )

        is_valid = verify(
            self.sender_pubkey,
            expected_domain,
            self.unsigned_bytes(),
            self.signature,
        )

        if not is_valid:
            raise ValueError(
                "INVALID_SIGNATURE"
            )