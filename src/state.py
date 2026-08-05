"""
Sorted key-value state map and its commitment hash (T1-10, T1-11).

The state is the data all correct nodes agree on: a map from string key to
raw byte value, where each value is the latest content written to that key
(PROTOCOL_SPEC.md Section 4).

Two properties matter more than performance here:

1. **Canonical ordering.** Iteration is always in sorted order by the raw
   UTF-8 bytes of the (NFC-normalized) key — never in insertion order and
   never in Python dict order. ARCHITECTURE.md requires that nothing in the
   node iterates a map in its native order, because that is how byte-identical
   replay gets broken.
2. **Semantic key identity.** Keys are NFC-normalized on the way in, exactly
   like `encoding.encode_str`, so two spellings of the same text address the
   same entry instead of creating two.

Nonces are *not* stored here; the executor owns the sender nonce map.
"""

from src.crypto import hash_bytes
import unicodedata

from src.encoding import encode_sorted_map

# Length of a SHA-256 digest, per PROTOCOL_SPEC.md Section 1.
HASH_SIZE = 32


def _normalize_key(key: str) -> str:
    """NFC-normalize a key, rejecting anything that is not a non-empty string."""
    if not isinstance(key, str):
        raise TypeError(f"State key must be a string, got {type(key).__name__}")
    if key == "":
        raise ValueError("State key must not be empty")
    return unicodedata.normalize("NFC", key)


def _check_value(value: bytes) -> bytes:
    """Reject non-bytes values; str and bytearray are not accepted silently."""
    if not isinstance(value, bytes):
        raise TypeError(f"State value must be bytes, got {type(value).__name__}")
    return value


class State:
    """A key-value map that always reads back in canonical sorted order.

    Backed by a plain dict; ordering is imposed at every read path rather than
    by pulling in a third-party sorted container, so the module stays on the
    standard library. State sizes in the simulator are small enough that the
    sort per read is not a concern.
    """

    __slots__ = ("_entries",)

    def __init__(self, entries: dict[str, bytes] | None = None) -> None:
        """Create a state, optionally seeded from an existing map."""
        self._entries: dict[str, bytes] = {}
        if entries:
            for key, value in sorted(entries.items()):
                self.insert(key, value)

    # -- mutation ----------------------------------------------------------

    def insert(self, key: str, value: bytes) -> None:
        """Write `value` at `key`, replacing any previous value.

        This is an upsert: the protocol only ever stores the latest content
        for a key, so writing an existing key is not an error.
        """
        self._entries[_normalize_key(key)] = _check_value(value)

    def delete(self, key: str) -> bool:
        """Remove `key`. Returns True if it existed, False if it did not.

        Deleting an absent key is not an error, but the return value lets the
        caller tell the two cases apart when that distinction matters.
        """
        return self._entries.pop(_normalize_key(key), None) is not None

    def clear(self) -> None:
        """Drop every entry."""
        self._entries.clear()

    # -- reads -------------------------------------------------------------

    def get(self, key: str, default: bytes | None = None) -> bytes | None:
        """Return the value at `key`, or `default` when the key is absent."""
        return self._entries.get(_normalize_key(key), default)

    def has(self, key: str) -> bool:
        """Return True when `key` is present."""
        return _normalize_key(key) in self._entries

    def keys(self) -> list[str]:
        """Keys in canonical order (sorted by raw UTF-8 bytes)."""
        return sorted(self._entries, key=lambda k: k.encode("utf-8"))

    def values(self) -> list[bytes]:
        """Values ordered by their keys' canonical order."""
        return [self._entries[key] for key in self.keys()]

    def items(self) -> list[tuple[str, bytes]]:
        """(key, value) pairs in canonical order."""
        return [(key, self._entries[key]) for key in self.keys()]

    def to_dict(self) -> dict[str, bytes]:
        """A plain dict whose insertion order is the canonical order."""
        return dict(self.items())

    # -- copying -----------------------------------------------------------

    def copy(self) -> "State":
        """An independent copy.

        The executor works on a copy of the parent state so that a block
        containing an invalid transaction can be discarded whole, without
        having to undo the writes it already performed.
        """
        clone = State()
        clone._entries = dict(self._entries)
        return clone

    # -- canonical bytes and commitment ------------------------------------

    def canonical_bytes(self) -> bytes:
        """Canonical encoding of the whole state: entry_count || sorted pairs.

        This is the pre-image the state commitment hashes over (T1-11).
        """
        return encode_sorted_map(self._entries)

    def state_hash(self) -> bytes:
        """The state commitment: `SHA256(entry_count || sorted (key, value) pairs)`.

        Returns the raw 32-byte digest. Every block header commits to the
        post-execution state with this value, so two correct nodes that
        executed the same ordered transactions on the same parent must produce
        the same bytes here (PROTOCOL_SPEC.md Sections 3 and 7).

        The digest is taken over `canonical_bytes()`, which already carries the
        u64 entry count prefix and orders entries by raw UTF-8 key bytes — the
        empty state therefore commits to `SHA256(count=0)`, not to the hash of
        an empty input.
        """
        # TODO(T1-05): delegate to crypto.hash_bytes() once src/crypto.py lands.
        return hash_bytes(self.canonical_bytes())

    def state_hash_hex(self) -> str:
        """The state commitment as lowercase hex.

        Hashes travel as raw bytes inside the protocol; hex is only for log and
        UI boundaries (PROTOCOL_SPEC.md Section 1).
        """
        return self.state_hash().hex()

    # -- dunders -----------------------------------------------------------

    def __setitem__(self, key: str, value: bytes) -> None:
        self.insert(key, value)

    def __getitem__(self, key: str) -> bytes:
        normalized = _normalize_key(key)
        if normalized not in self._entries:
            raise KeyError(key)
        return self._entries[normalized]

    def __delitem__(self, key: str) -> None:
        if not self.delete(key):
            raise KeyError(key)

    def __contains__(self, key: str) -> bool:
        return self.has(key)

    def __len__(self) -> int:
        return len(self._entries)

    def __iter__(self):
        """Iterate keys in canonical order."""
        return iter(self.keys())

    def __eq__(self, other: object) -> bool:
        """Two states are equal when they hold the same entries.

        Ordering plays no part: the map is the value, and canonical ordering
        is a property of how it is read out.
        """
        if not isinstance(other, State):
            return NotImplemented
        return self._entries == other._entries

    def __repr__(self) -> str:
        return f"State({self.to_dict()!r})"
