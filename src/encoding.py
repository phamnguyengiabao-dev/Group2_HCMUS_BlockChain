"""
canonical encoding for blockchain protocol messages.

All values that are hashed or signed use this canonical byte representation
as defined in PROTOCOL_SPEC.md Section 2 and requirement F-07.
"""

import struct
import unicodedata


def encode_uint64(value: int) -> bytes:
    """Encode unsigned 64-bit integer as 8-byte big-endian.

    Raises ValueError if value is outside [0, 2^64).
    """
    if not (0 <= value < 2**64):
        raise ValueError(f"Value {value} is out of uint64 range [0, 2^64)")
    return struct.pack(">Q", value)


def encode_bool(value: bool) -> bytes:
    """Encode boolean as 1 byte: b'\\x01' for True, b'\\x00' for False."""
    return b"\x01" if value else b"\x00"


def encode_bytes(data: bytes) -> bytes:
    """Encode byte string with u32 big-endian length prefix (4 bytes) followed by raw data."""
    length = len(data)
    if length > 0xFFFFFFFF:
        raise ValueError(f"Byte string length {length} exceeds u32 max (4294967295)")
    return struct.pack(">I", length) + data


def encode_str(text: str) -> bytes:
    """Encode UTF-8 string: NFC-normalize, encode to UTF-8 bytes, then apply encode_bytes."""
    normalized = unicodedata.normalize("NFC", text)
    utf8_bytes = normalized.encode("utf-8")
    return encode_bytes(utf8_bytes)


def encode_optional_hash(hash_bytes: bytes | None) -> bytes:
    """Encode optional 32-byte hash.

    Returns b'\\x00' if None.
    Returns b'\\x01' + 32 bytes if present.
    Raises ValueError if hash_bytes is not None and not exactly 32 bytes.
    """
    if hash_bytes is None:
        return b"\x00"
    if len(hash_bytes) != 32:
        raise ValueError(
            f"hash_bytes must be exactly 32 bytes, got {len(hash_bytes)}"
        )
    return b"\x01" + hash_bytes

#T1-03
def encode_sorted_map(values: dict[str, bytes]) -> bytes:
    """Encode a string-to-bytes map in canonical sorted order.

    Format:
        u64 entry_count
        || encode_str(key_1)
        || encode_bytes(value_1)
        || ...
        || encode_str(key_n)
        || encode_bytes(value_n)

    Keys are NFC-normalized and sorted lexicographically by their UTF-8 bytes.
    """

    normalized_entries: list[tuple[bytes, bytes]] = []

    for key, value in values.items():
        if not isinstance(key, str):
            raise TypeError("Map key must be a string")

        if not isinstance(value, bytes):
            raise TypeError("Map value must be bytes")

        # Normalize exactly like encode_str()
        normalized_key = unicodedata.normalize("NFC", key)

        # Raw UTF-8 bytes are used for sorting
        key_utf8 = normalized_key.encode("utf-8")

        normalized_entries.append((key_utf8, value))

    # Sort lexicographically by raw UTF-8 key bytes
    normalized_entries.sort(key=lambda entry: entry[0])

    result = bytearray()

    # Number of entries
    result.extend(encode_uint64(len(normalized_entries)))

    # Encode each key-value pair in canonical order
    for key_utf8, value in normalized_entries:
        result.extend(encode_bytes(key_utf8))
        result.extend(encode_bytes(value))

    return bytes(result)
