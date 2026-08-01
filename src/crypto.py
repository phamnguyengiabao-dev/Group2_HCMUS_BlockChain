"""
Cryptographic primitives for the blockchain protocol.

T1-05:
- SHA-256 hashing
- hash_bytes(data) -> bytes

T1-06, T1-07:
- Ed25519 signing/verification with domain-separated messages
- Message format: UTF-8(domain) || 0x00 || payload
"""

import hashlib
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

DOMAIN_SEPARATOR = b"\x00"
PUBLIC_KEY_LEN = 32
PRIVATE_KEY_LEN = 32  # Ed25519 seed length
SIGNATURE_LEN = 64


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


def _build_message(domain: str, payload: bytes) -> bytes:
    if not isinstance(domain, str) or not domain:
        raise ValueError("domain must be a non-empty str")
    if not isinstance(payload, (bytes, bytearray)):
        raise ValueError("payload must be bytes")
    return domain.encode("utf-8") + DOMAIN_SEPARATOR + bytes(payload)


def sign(privkey: bytes, domain: str, payload: bytes) -> bytes:
    """
    Sign `payload` under the given domain-separated context.

    Args:
        privkey: 32-byte Ed25519 private key seed.
        domain: Domain-separation context string (e.g. "TX:lab01").
        payload: Canonical-encoded bytes to sign.

    Returns:
        64-byte Ed25519 signature over utf8(domain) || 0x00 || payload.
    """
    if not isinstance(privkey, (bytes, bytearray)) or len(privkey) != PRIVATE_KEY_LEN:
        raise ValueError(f"privkey must be {PRIVATE_KEY_LEN} bytes")

    message = _build_message(domain, payload)
    sk = Ed25519PrivateKey.from_private_bytes(bytes(privkey))
    return sk.sign(message)


def verify(pubkey: bytes, domain: str, payload: bytes, signature: bytes) -> bool:
    """
    Verify a signature under the given domain-separated context.

    Args:
        pubkey: 32-byte Ed25519 public key.
        domain: The domain expected for this message type.
        payload: Canonical-encoded bytes that were signed.
        signature: 64-byte Ed25519 signature to check.

    Returns:
        True if the signature is valid, False for any invalid or malformed input.
    """
    try:
        if not isinstance(pubkey, (bytes, bytearray)) or len(pubkey) != PUBLIC_KEY_LEN:
            return False
        if not isinstance(signature, (bytes, bytearray)) or len(signature) != SIGNATURE_LEN:
            return False

        message = _build_message(domain, payload)
        vk = Ed25519PublicKey.from_public_bytes(bytes(pubkey))
        vk.verify(bytes(signature), message)
        return True
    except (InvalidSignature, ValueError):
        return False
