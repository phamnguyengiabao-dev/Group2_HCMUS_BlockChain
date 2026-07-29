"""
test_encoding.py — Unit tests for the canonical encoder (T1-01, T1-02, T1-03, T1-04).

Central property under test: **semantically equal values must produce
byte-identical output**, and semantically different values must never collide.
This is what makes hashes and signatures reproducible across nodes
(PROTOCOL_SPEC.md Section 2, requirement F-07).
"""

import pytest

from src.encoding import (
    encode_bool,
    encode_bytes,
    encode_optional_hash,
    encode_sorted_map,
    encode_str,
    encode_uint64,
)

# ---------------------------------------------------------------------------
# encode_uint64 — 8-byte big-endian
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "value,expected",
    [
        (0, b"\x00\x00\x00\x00\x00\x00\x00\x00"),
        (1, b"\x00\x00\x00\x00\x00\x00\x00\x01"),
        (255, b"\x00\x00\x00\x00\x00\x00\x00\xff"),
        (256, b"\x00\x00\x00\x00\x00\x00\x01\x00"),
        (2**64 - 1, b"\xff\xff\xff\xff\xff\xff\xff\xff"),
    ],
)
def test_uint64_known_vectors(value, expected):
    """Fixed big-endian vectors pin the wire format down."""
    assert encode_uint64(value) == expected


def test_uint64_is_always_eight_bytes():
    """Width is fixed regardless of magnitude — no length prefix is needed."""
    for value in (0, 1, 42, 2**32, 2**64 - 1):
        assert len(encode_uint64(value)) == 8


def test_uint64_equal_values_from_different_literals_are_byte_identical():
    """42, 0x2A and int("42") are the same number, so they must be the same bytes."""
    assert encode_uint64(42) == encode_uint64(0x2A) == encode_uint64(int("42"))


def test_uint64_big_endian_preserves_numeric_order():
    """Big-endian means byte order matches numeric order — relied on by sorted encodings."""
    encoded = [encode_uint64(v) for v in (0, 1, 256, 2**32, 2**64 - 1)]
    assert encoded == sorted(encoded)


@pytest.mark.parametrize("value", [-1, 2**64, 2**64 + 1])
def test_uint64_rejects_out_of_range(value):
    """Out-of-range values must raise instead of silently wrapping."""
    with pytest.raises(ValueError):
        encode_uint64(value)


# ---------------------------------------------------------------------------
# encode_bool — 1 byte
# ---------------------------------------------------------------------------


def test_bool_known_vectors():
    assert encode_bool(True) == b"\x01"
    assert encode_bool(False) == b"\x00"


def test_bool_is_always_one_byte():
    assert len(encode_bool(True)) == 1
    assert len(encode_bool(False)) == 1


def test_bool_true_and_false_never_collide():
    assert encode_bool(True) != encode_bool(False)


def test_bool_equal_truth_values_are_byte_identical():
    """True == 1 and False == 0 in Python, so their encodings must match too."""
    assert encode_bool(True) == encode_bool(1)
    assert encode_bool(False) == encode_bool(0)


# ---------------------------------------------------------------------------
# encode_bytes — u32 big-endian length prefix || raw data
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "data,expected",
    [
        (b"", b"\x00\x00\x00\x00"),
        (b"A", b"\x00\x00\x00\x01A"),
        (b"abc", b"\x00\x00\x00\x03abc"),
        (b"\x00", b"\x00\x00\x00\x01\x00"),
    ],
)
def test_bytes_known_vectors(data, expected):
    assert encode_bytes(data) == expected


def test_bytes_equal_content_from_different_constructions_is_byte_identical():
    """A literal, a bytes() call and a decoded hex string are the same value."""
    assert (
        encode_bytes(b"\x01\x02\x03")
        == encode_bytes(bytes([1, 2, 3]))
        == encode_bytes(bytes.fromhex("010203"))
    )


def test_bytes_length_prefix_removes_concatenation_ambiguity():
    """("ab", "c") and ("a", "bc") share raw bytes but must not share an encoding."""
    left = encode_bytes(b"ab") + encode_bytes(b"c")
    right = encode_bytes(b"a") + encode_bytes(b"bc")
    assert left != right


def test_bytes_empty_is_distinguishable_from_absent_field():
    """An empty byte string still occupies its 4-byte prefix."""
    assert encode_bytes(b"") == b"\x00\x00\x00\x00"
    assert len(encode_bytes(b"")) == 4


def test_bytes_prefix_matches_actual_length():
    data = b"\xde\xad\xbe\xef" * 64  # 256 bytes
    encoded = encode_bytes(data)
    assert encoded[:4] == encode_uint64(len(data))[4:]  # low 4 bytes of the same number
    assert encoded[4:] == data


# ---------------------------------------------------------------------------
# encode_str — NFC normalize || UTF-8 || encode_bytes
# ---------------------------------------------------------------------------


def test_str_known_vectors():
    assert encode_str("") == b"\x00\x00\x00\x00"
    assert encode_str("abc") == b"\x00\x00\x00\x03abc"


def test_str_nfc_normalization_makes_equal_text_byte_identical():
    """Precomposed U+00E9 and decomposed (e + U+0301) are the same text."""
    precomposed = "é"
    decomposed = "é"  # e + combining acute

    assert precomposed != decomposed  # different code points...
    assert encode_str(precomposed) == encode_str(decomposed)  # ...same canonical bytes


def test_str_nfc_normalization_applies_to_vietnamese_text():
    """The report and log fields carry Vietnamese; both input forms must agree."""
    precomposed = "Nguyễn"
    decomposed = "Nguyễn"  # e + combining circumflex + combining tilde

    assert precomposed != decomposed
    assert encode_str(precomposed) == encode_str(decomposed)


def test_str_length_prefix_counts_utf8_bytes_not_characters():
    text = "é"  # 1 character, 2 UTF-8 bytes
    encoded = encode_str(text)
    assert encoded[:4] == b"\x00\x00\x00\x02"
    assert encoded[4:] == b"\xc3\xa9"


def test_str_is_encode_bytes_over_normalized_utf8():
    """encode_str must stay a thin, predictable wrapper over encode_bytes."""
    import unicodedata

    for text in ("", "abc", "é", "Nguyễn", "key/with/slash"):
        expected = encode_bytes(unicodedata.normalize("NFC", text).encode("utf-8"))
        assert encode_str(text) == expected


def test_str_different_text_never_collides():
    assert encode_str("a") != encode_str("b")
    assert encode_str("ab") != encode_str("a")


# ---------------------------------------------------------------------------
# encode_optional_hash — presence byte (|| 32-byte hash)
# ---------------------------------------------------------------------------

HASH_A = bytes(range(32))
HASH_B = bytes(32)  # 32 zero bytes


def test_optional_hash_none_is_single_zero_byte():
    assert encode_optional_hash(None) == b"\x00"


def test_optional_hash_present_is_presence_byte_plus_hash():
    encoded = encode_optional_hash(HASH_A)
    assert encoded == b"\x01" + HASH_A
    assert len(encoded) == 33


def test_optional_hash_equal_hashes_from_different_constructions_are_byte_identical():
    """NIL vs a real block hash is a consensus-critical distinction — pin both forms."""
    assert encode_optional_hash(bytes(range(32))) == encode_optional_hash(
        bytes.fromhex("".join(f"{i:02x}" for i in range(32)))
    )


def test_optional_hash_nil_never_collides_with_a_present_hash():
    """A NIL vote must never encode like a vote for an actual block."""
    assert encode_optional_hash(None) != encode_optional_hash(HASH_A)
    assert encode_optional_hash(None) != encode_optional_hash(HASH_B)


def test_optional_hash_different_hashes_never_collide():
    assert encode_optional_hash(HASH_A) != encode_optional_hash(HASH_B)


@pytest.mark.parametrize("bad_length", [0, 1, 31, 33, 64])
def test_optional_hash_rejects_wrong_size(bad_length):
    """Only exactly 32 bytes are accepted; anything else must raise."""
    with pytest.raises(ValueError):
        encode_optional_hash(bytes(bad_length))


# ---------------------------------------------------------------------------
# encode_sorted_map — u64 count || sorted (key, value) pairs   [T1-03]
# ---------------------------------------------------------------------------


def test_sorted_map_is_deterministic():
    map_a = {
        "banana": b"B",
        "apple": b"A",
    }

    map_b = {
        "apple": b"A",
        "banana": b"B",
    }

    assert encode_sorted_map(map_a) == encode_sorted_map(map_b)


def test_sorted_map_encodes_keys_in_utf8_order():
    values = {
        "z": b"Z",
        "a": b"A",
    }

    encoded = encode_sorted_map(values)

    expected = (
        # entry_count = 2
        b"\x00\x00\x00\x00\x00\x00\x00\x02"

        # key = "a"
        b"\x00\x00\x00\x01"
        b"a"

        # value = b"A"
        b"\x00\x00\x00\x01"
        b"A"

        # key = "z"
        b"\x00\x00\x00\x01"
        b"z"

        # value = b"Z"
        b"\x00\x00\x00\x01"
        b"Z"
    )

    assert encoded == expected


def test_sorted_map_empty():
    encoded = encode_sorted_map({})

    expected = (
        b"\x00\x00\x00\x00"
        b"\x00\x00\x00\x00"
    )

    assert encoded == expected


# ---------------------------------------------------------------------------
# Cross-cutting determinism
# ---------------------------------------------------------------------------


def test_encoders_are_pure_and_repeatable():
    """Repeated calls in one process must return identical bytes (no hidden state)."""
    calls = [
        (encode_uint64, 12345),
        (encode_bool, True),
        (encode_bytes, b"payload"),
        (encode_str, "Nguyễn"),
        (encode_optional_hash, HASH_A),
        (encode_optional_hash, None),
    ]

    for func, argument in calls:
        first = func(argument)
        assert all(func(argument) == first for _ in range(5)), (
            f"{func.__name__} is not deterministic for {argument!r}"
        )


def test_all_encoders_return_bytes():
    """Callers concatenate results directly — every encoder must return real bytes."""
    results = [
        encode_uint64(1),
        encode_bool(False),
        encode_bytes(b"x"),
        encode_str("x"),
        encode_optional_hash(None),
        encode_sorted_map({"k": b"v"}),
    ]

    for result in results:
        assert isinstance(result, bytes), f"Expected bytes, got {type(result).__name__}"
