"""
Vote object and acceptance guards for the blockchain protocol.

T2-06:
- Vote object
- Canonical unsigned/signed vote encoding
- Ed25519 vote signing
- Acceptance guards (F-40):
    * chain_id
    * validator set membership ("member check")
    * VOTE domain signature
    * height / round / phase match

Note: "hash candidate đã biết" (candidate hash already known) is a VoteSet /
router-level guard (T2-07..T3-11), not part of this object's validation.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Collection

from src.crypto import sign, verify
from src.encoding import (
    encode_bytes,
    encode_optional_hash,
    encode_str,
    encode_uint64,
)


PUBLIC_KEY_SIZE = 32
SIGNATURE_SIZE = 64
HASH_SIZE = 32

# Canonical phase values (match the PREVOTE / PRECOMMIT event types).
PHASE_PREVOTE = "PREVOTE"
PHASE_PRECOMMIT = "PRECOMMIT"


@dataclass(frozen=True, slots=True)
class Vote:
    """
    Canonical vote cast by a validator during consensus.

    Field order:

        chain_id
        height
        round
        phase
        block_hash_or_nil
        validator_pubkey
        signature
    """

    chain_id: str
    height: int
    round: int
    phase: str
    block_hash_or_nil: bytes | None
    validator_pubkey: bytes
    signature: bytes

    def unsigned_bytes(self) -> bytes:
        """
        Return the canonical encoding of the unsigned vote.

        The signature is excluded because this is the data signed by the
        validator.
        """

        return (
            encode_str(self.chain_id)
            + encode_uint64(self.height)
            + encode_uint64(self.round)
            + encode_str(self.phase)
            + encode_optional_hash(self.block_hash_or_nil)
            + encode_bytes(self.validator_pubkey)
        )

    def signed_bytes(self) -> bytes:
        """
        Return the canonical encoding of the complete vote.

        The signature is encoded as a length-prefixed byte string.
        """

        return (
            self.unsigned_bytes()
            + encode_bytes(self.signature)
        )

    def validate(
        self,
        *,
        expected_chain_id: str,
        validator_set: Collection[bytes],
        expected_height: int,
        expected_round: int,
        expected_phase: str,
    ) -> None:
        """
        Validate the vote against the F-40 acceptance guards, in order:

            1. chain_id matches the expected chain
            2. validator_pubkey is a member of the current validator set
            3. signature verifies under the VOTE:<chain_id> domain
            4. height, round, and phase match what the caller expects

        Raises:
            TypeError: If a field has the wrong Python type.
            ValueError: If a guard fails. The message is prefixed with a
                stable rejection code identifying which guard failed.
        """

        # ---------------------------------------------
        # Basic field types
        # ---------------------------------------------

        if not isinstance(self.chain_id, str):
            raise TypeError("chain_id must be a string")

        if not isinstance(self.height, int):
            raise TypeError("height must be an integer")

        if not isinstance(self.round, int):
            raise TypeError("round must be an integer")

        if not isinstance(self.phase, str):
            raise TypeError("phase must be a string")

        if self.block_hash_or_nil is not None and not isinstance(
            self.block_hash_or_nil, bytes
        ):
            raise TypeError("block_hash_or_nil must be bytes or None")

        if not isinstance(self.validator_pubkey, bytes):
            raise TypeError("validator_pubkey must be bytes")

        if not isinstance(self.signature, bytes):
            raise TypeError("signature must be bytes")

        if len(self.validator_pubkey) != PUBLIC_KEY_SIZE:
            raise ValueError(
                "INVALID_VALIDATOR_PUBKEY: "
                "Ed25519 public key must be 32 bytes"
            )

        if len(self.signature) != SIGNATURE_SIZE:
            raise ValueError(
                "INVALID_SIGNATURE_LENGTH: "
                "Ed25519 signature must be 64 bytes"
            )

        # ---------------------------------------------
        # 1. chain_id guard
        # ---------------------------------------------

        if self.chain_id != expected_chain_id:
            raise ValueError(
                "INVALID_CHAIN_ID: "
                f"expected {expected_chain_id!r}, got {self.chain_id!r}"
            )

        # ---------------------------------------------
        # 2. member check
        # ---------------------------------------------

        if self.validator_pubkey not in validator_set:
            raise ValueError(
                "NOT_A_VALIDATOR: "
                f"{self.validator_pubkey.hex()} is not in the validator set"
            )

        # ---------------------------------------------
        # 3. VOTE domain signature
        # ---------------------------------------------

        expected_domain = f"VOTE:{expected_chain_id}"

        is_valid = verify(
            self.validator_pubkey,
            expected_domain,
            self.unsigned_bytes(),
            self.signature,
        )

        if not is_valid:
            raise ValueError("INVALID_SIGNATURE")

        # ---------------------------------------------
        # 4. height / round / phase match
        # ---------------------------------------------

        if self.height != expected_height:
            raise ValueError(
                "INVALID_HEIGHT: "
                f"expected {expected_height}, got {self.height}"
            )

        if self.round != expected_round:
            raise ValueError(
                "INVALID_ROUND: "
                f"expected {expected_round}, got {self.round}"
            )

        if self.phase != expected_phase:
            raise ValueError(
                "INVALID_PHASE: "
                f"expected {expected_phase!r}, got {self.phase!r}"
            )

    @classmethod
    def create_signed(
        cls,
        *,
        chain_id: str,
        height: int,
        round: int,
        phase: str,
        block_hash_or_nil: bytes | None,
        validator_pubkey: bytes,
        validator_privkey: bytes,
    ) -> "Vote":
        """
        Create and sign a vote.

        The signature uses the domain:

            VOTE:<chain_id>
        """

        unsigned_vote = cls(
            chain_id=chain_id,
            height=height,
            round=round,
            phase=phase,
            block_hash_or_nil=block_hash_or_nil,
            validator_pubkey=validator_pubkey,
            signature=b"",
        )

        signature = sign(
            validator_privkey,
            f"VOTE:{chain_id}",
            unsigned_vote.unsigned_bytes(),
        )

        return cls(
            chain_id=chain_id,
            height=height,
            round=round,
            phase=phase,
            block_hash_or_nil=block_hash_or_nil,
            validator_pubkey=validator_pubkey,
            signature=signature,
        )
