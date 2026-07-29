from src.encoding import encode_sorted_map

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