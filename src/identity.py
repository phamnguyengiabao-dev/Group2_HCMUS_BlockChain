"""
Validator identity management for the blockchain protocol.

T1-9:
- Load and validate 8 fixed validator key pairs from config/validator_keys.json
- ValidatorIdentity dataclass holding index, public_key, private_key
- load_validator_keys() to parse and cross-validate all keys
- get_validator(index) shortcut
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

# Default config path relative to project root (parent of src/)
_DEFAULT_CONFIG = Path(__file__).parent.parent / "config" / "validator_keys.json"

_KEY_HEX_LEN = 64   # 64 hex chars == 32 bytes
_KEY_BYTES_LEN = 32

# Module-level cache so get_validator() is cheap after first call
_cached_validators: list[ValidatorIdentity] | None = None


@dataclass(frozen=True)
class ValidatorIdentity:
    """Immutable container for a single validator's Ed25519 key pair."""
    index: int
    public_key: bytes   # 32 bytes
    private_key: bytes  # 32 bytes (Ed25519 seed)


def _derive_public_key(private_key_bytes: bytes) -> bytes:
    """Derive the 32-byte Ed25519 public key from a 32-byte private seed."""
    sk = Ed25519PrivateKey.from_private_bytes(private_key_bytes)
    pk = sk.public_key()
    # public_bytes() requires encoding; use raw bytes via Raw encoding
    from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
    return pk.public_bytes(Encoding.Raw, PublicFormat.Raw)


def load_validator_keys(config_path: str | Path | None = None) -> list[ValidatorIdentity]:
    """
    Load and validate all validator key pairs from the JSON config file.

    Args:
        config_path: Path to validator_keys.json.  Defaults to
                     ``config/validator_keys.json`` relative to project root.

    Returns:
        List of ValidatorIdentity objects ordered by their index field.

    Raises:
        FileNotFoundError: If the config file does not exist.
        ValueError: If any entry is malformed or the public key does not match
                    the one derived from the private key.
        KeyError: If required JSON fields are missing.
    """
    path = Path(config_path) if config_path is not None else _DEFAULT_CONFIG

    if not path.exists():
        raise FileNotFoundError(f"Validator keys config not found: {path}")

    with path.open("r", encoding="utf-8") as fh:
        data = json.load(fh)

    entries = data["validator_keys"]  # KeyError propagates naturally
    validators: list[ValidatorIdentity] = []

    for entry in entries:
        idx: int = entry["index"]

        pub_hex: str = entry["public_key_hex"]
        priv_hex: str = entry["private_key_hex"]

        # --- Length validation ---
        if len(pub_hex) != _KEY_HEX_LEN:
            raise ValueError(
                f"Validator {idx}: public_key_hex must be {_KEY_HEX_LEN} hex chars, "
                f"got {len(pub_hex)}"
            )
        if len(priv_hex) != _KEY_HEX_LEN:
            raise ValueError(
                f"Validator {idx}: private_key_hex must be {_KEY_HEX_LEN} hex chars, "
                f"got {len(priv_hex)}"
            )

        try:
            pub_bytes = bytes.fromhex(pub_hex)
        except ValueError:
            raise ValueError(f"Validator {idx}: public_key_hex is not valid hex")

        try:
            priv_bytes = bytes.fromhex(priv_hex)
        except ValueError:
            raise ValueError(f"Validator {idx}: private_key_hex is not valid hex")

        # --- Byte-length sanity check ---
        if len(pub_bytes) != _KEY_BYTES_LEN:
            raise ValueError(
                f"Validator {idx}: public key must be {_KEY_BYTES_LEN} bytes"
            )
        if len(priv_bytes) != _KEY_BYTES_LEN:
            raise ValueError(
                f"Validator {idx}: private key must be {_KEY_BYTES_LEN} bytes"
            )

        # --- Cross-check: derive public key from private key ---
        derived_pub = _derive_public_key(priv_bytes)
        if derived_pub != pub_bytes:
            raise ValueError(
                f"Validator {idx}: derived public key "
                f"{derived_pub.hex()} does not match stored public key {pub_hex}"
            )

        validators.append(ValidatorIdentity(
            index=idx,
            public_key=pub_bytes,
            private_key=priv_bytes,
        ))

    # Sort by index so the list position is predictable
    validators.sort(key=lambda v: v.index)
    return validators


def get_validator(index: int) -> ValidatorIdentity:
    """
    Return the ValidatorIdentity for the given index.

    The validator list is loaded (and cached) on the first call.

    Args:
        index: Zero-based validator index (0–7 for the default fixture).

    Returns:
        The corresponding ValidatorIdentity.

    Raises:
        IndexError: If index is out of range.
    """
    global _cached_validators
    if _cached_validators is None:
        _cached_validators = load_validator_keys()

    if index < 0 or index >= len(_cached_validators):
        raise IndexError(
            f"Validator index {index} out of range "
            f"(0–{len(_cached_validators) - 1})"
        )
    return _cached_validators[index]
