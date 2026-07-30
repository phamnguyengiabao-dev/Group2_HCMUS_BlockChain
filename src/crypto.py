"""
Cryptographic primitives for the blockchain protocol.

T1-05:
- SHA-256 hashing
- hash_bytes(data) -> bytes
"""

import hashlib


def hash_bytes(data: bytes) -> bytes:
    """
    Compute the SHA-256 hash of raw bytes.

    Args:
        data: Input data as bytes.

    Returns:
        The SHA-256 digest as exactly 32 raw bytes.

    Raises:
        TypeError: If data is not a bytes object.
    """
    if not isinstance(data, bytes):
        raise TypeError(
            f"data must be bytes, got {type(data).__name__}"
        )

    digest = hashlib.sha256(data).digest()

    # SHA-256 must always produce exactly 32 bytes.
    if len(digest) != 32:
        raise RuntimeError(
            f"SHA-256 returned {len(digest)} bytes; expected 32"
        )

    return digest