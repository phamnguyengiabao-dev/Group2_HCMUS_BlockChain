"""
Block data structures for the blockchain protocol.

T2-01:
- BlockHeader object
- Canonical unsigned header encoding
- Canonical signed header encoding
- Ed25519 header signing
- block_hash computation
"""

from __future__ import annotations

from dataclasses import dataclass

from src.crypto import hash_bytes, sign
from src.encoding import (
    encode_bytes,
    encode_str,
    encode_uint64,
)


HASH_SIZE = 32
PUBLIC_KEY_SIZE = 32
SIGNATURE_SIZE = 64


@dataclass(frozen=True, slots=True)
class BlockHeader:
    """
    Canonical block header.

    Field order:

        chain_id
        height
        round
        parent_hash
        tx_root
        state_hash
        proposer_pubkey
        signature
    """

    chain_id: str
    height: int
    round: int
    parent_hash: bytes
    tx_root: bytes
    state_hash: bytes
    proposer_pubkey: bytes
    signature: bytes

    def unsigned_bytes(self) -> bytes:
        """
        Return the canonical encoding of the unsigned header.

        The signature is excluded because this is the data
        signed by the proposer.
        """

        return (
            encode_str(self.chain_id)
            + encode_uint64(self.height)
            + encode_uint64(self.round)
            + encode_bytes(self.parent_hash)
            + encode_bytes(self.tx_root)
            + encode_bytes(self.state_hash)
            + encode_bytes(self.proposer_pubkey)
        )

    def signed_bytes(self) -> bytes:
        """
        Return the canonical encoding of the complete header.

        The signature is encoded as a length-prefixed byte string.
        """

        return (
            self.unsigned_bytes()
            + encode_bytes(self.signature)
        )

    def block_hash(self) -> bytes:
        """
        Compute the block hash.

        block_hash =
            SHA256(canonical signed header)

        Returns:
            Raw 32-byte SHA-256 digest.
        """

        return hash_bytes(
            self.signed_bytes()
        )

    def block_hash_hex(self) -> str:
        """
        Return the block hash as lowercase hexadecimal.

        Hex is only used for logs or UI.
        """

        return self.block_hash().hex()

    @classmethod
    def create_signed(
        cls,
        *,
        chain_id: str,
        height: int,
        round: int,
        parent_hash: bytes,
        tx_root: bytes,
        state_hash: bytes,
        proposer_pubkey: bytes,
        proposer_privkey: bytes,
    ) -> "BlockHeader":
        """
        Create and sign a block header.

        The signature uses the domain:

            HEADER:<chain_id>
        """

        unsigned_header = cls(
            chain_id=chain_id,
            height=height,
            round=round,
            parent_hash=parent_hash,
            tx_root=tx_root,
            state_hash=state_hash,
            proposer_pubkey=proposer_pubkey,
            signature=b"",
        )

        signature = sign(
            proposer_privkey,
            f"HEADER:{chain_id}",
            unsigned_header.unsigned_bytes(),
        )

        return cls(
            chain_id=chain_id,
            height=height,
            round=round,
            parent_hash=parent_hash,
            tx_root=tx_root,
            state_hash=state_hash,
            proposer_pubkey=proposer_pubkey,
            signature=signature,
        )