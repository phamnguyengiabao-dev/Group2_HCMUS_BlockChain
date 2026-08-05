"""
event_log.py — Canonical JSONL event logger for blockchain simulator.

T3-01:
- Define exactly 18 canonical event types.
- Use one fixed top-level field order for every event:
    event_no,
    logical_time,
    node_id,
    event_type,
    height,
    round,
    details
- Sort all details keys alphabetically.
- Reject unknown event types.

Each event is written as exactly one JSON line.
"""

from __future__ import annotations

import hashlib
import json
from enum import Enum
from pathlib import Path
from typing import Any


class EventType(str, Enum):
    """
    The 18 canonical event types defined by T3-01.

    Using str + Enum allows values to be used directly as JSON strings.
    """

    SEND = "SEND"
    DELIVER = "DELIVER"
    DROP = "DROP"
    DELAY = "DELAY"
    DUPLICATE = "DUPLICATE"

    PEER_BLOCK = "PEER_BLOCK"
    PEER_UNBLOCK = "PEER_UNBLOCK"

    REJECT = "REJECT"

    PROPOSE = "PROPOSE"
    PREVOTE = "PREVOTE"
    PRECOMMIT = "PRECOMMIT"
    LOCK = "LOCK"

    TIMEOUT = "TIMEOUT"
    ROUND_CHANGE = "ROUND_CHANGE"

    FINALIZE = "FINALIZE"
    EQUIVOCATION = "EQUIVOCATION"

    CRASH = "CRASH"
    RESTART = "RESTART"


# Canonical event type names in fixed order.
#
# This tuple is useful for:
# - schema inspection
# - deterministic documentation
# - tests
# - validating that exactly 18 event types exist
CANONICAL_EVENT_TYPES: tuple[str, ...] = (
    "SEND",
    "DELIVER",
    "DROP",
    "DELAY",
    "DUPLICATE",
    "PEER_BLOCK",
    "PEER_UNBLOCK",
    "REJECT",
    "PROPOSE",
    "PREVOTE",
    "PRECOMMIT",
    "LOCK",
    "TIMEOUT",
    "ROUND_CHANGE",
    "FINALIZE",
    "EQUIVOCATION",
    "CRASH",
    "RESTART",
)


# Fixed top-level key order required for every JSONL event.
EVENT_FIELD_ORDER: tuple[str, ...] = (
    "event_no",
    "logical_time",
    "node_id",
    "event_type",
    "height",
    "round",
    "details",
)


def normalize_event_type(
    event_type: EventType | str,
) -> str:
    """
    Validate and normalize an event type.

    Args:
        event_type:
            An EventType member or one of the 18 canonical strings.

    Returns:
        The canonical event type string.

    Raises:
        TypeError:
            If event_type is not EventType or str.

        ValueError:
            If event_type is not one of the 18 canonical event types.
    """

    if isinstance(event_type, EventType):
        return event_type.value

    if not isinstance(event_type, str):
        raise TypeError(
            "event_type must be EventType or str, "
            f"got {type(event_type).__name__}"
        )

    if event_type not in CANONICAL_EVENT_TYPES:
        raise ValueError(
            "UNKNOWN_EVENT_TYPE: "
            f"{event_type!r}"
        )

    return event_type


def _validate_schema() -> None:
    """
    Verify the T3-01 schema definition.

    This runs once when the module is imported.
    """

    if len(CANONICAL_EVENT_TYPES) != 18:
        raise RuntimeError(
            "T3-01 requires exactly 18 event types, "
            f"got {len(CANONICAL_EVENT_TYPES)}"
        )

    if len(set(CANONICAL_EVENT_TYPES)) != 18:
        raise RuntimeError(
            "Canonical event types contain duplicates"
        )

    if len(EventType) != 18:
        raise RuntimeError(
            "EventType must contain exactly 18 values, "
            f"got {len(EventType)}"
        )

    if tuple(
        event.value
        for event in EventType
    ) != CANONICAL_EVENT_TYPES:
        raise RuntimeError(
            "EventType order does not match "
            "CANONICAL_EVENT_TYPES"
        )

    expected_field_order = (
        "event_no",
        "logical_time",
        "node_id",
        "event_type",
        "height",
        "round",
        "details",
    )

    if EVENT_FIELD_ORDER != expected_field_order:
        raise RuntimeError(
            "Invalid canonical event field order"
        )


_validate_schema()


class EventLog:
    """
    Writes deterministic JSONL event logs.

    Output path:

        logs/<scenario_id>/<run_id>.jsonl

    Every event has:
    - one fixed top-level key order
    - one validated canonical event type
    - alphabetically sorted details keys
    - compact deterministic JSON formatting
    """

    def __init__(
        self,
        scenario_id: str,
        run_id: str,
    ) -> None:
        self.scenario_id = scenario_id
        self.run_id = run_id

        log_dir = (
            Path("logs")
            / scenario_id
        )

        log_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        self.log_path = (
            log_dir
            / f"{run_id}.jsonl"
        )

        self._file = open(
            self.log_path,
            "w",
            encoding="utf-8",
            newline="\n",
        )

        self._event_count = 0

        self._closed = False

    def write_event(
        self,
        event_no: int,
        logical_time: int,
        node_id: str,
        event_type: EventType | str,
        height: int,
        round: int,  # noqa: A002
        details: dict[str, Any],
    ) -> None:
        """
        Write one canonical JSON event line.

        Top-level key order is always:

            event_no
            logical_time
            node_id
            event_type
            height
            round
            details

        Details keys are sorted alphabetically.
        """

        if self._closed:
            raise ValueError(
                "EVENT_LOG_CLOSED"
            )

        canonical_event_type = (
            normalize_event_type(
                event_type
            )
        )

        if not isinstance(
            details,
            dict,
        ):
            raise TypeError(
                "details must be a dict, "
                f"got {type(details).__name__}"
            )

        sorted_details = {
            key: details[key]
            for key in sorted(
                details
            )
        }

        # Python preserves insertion order in dictionaries.
        # Therefore this creates the required fixed JSON key order.
        record = {
            "event_no": event_no,
            "logical_time": logical_time,
            "node_id": node_id,
            "event_type": canonical_event_type,
            "height": height,
            "round": round,
            "details": sorted_details,
        }

        self._file.write(
            json.dumps(
                record,
                ensure_ascii=False,
                separators=(",", ":"),
            )
            + "\n"
        )

        self._event_count += 1

    def close(self) -> None:
        """
        Flush and close the log file.

        Calling close() more than once is safe.
        """

        if self._closed:
            return

        self._file.flush()
        self._file.close()

        self._closed = True

    def get_sha256(self) -> str:
        """
        Return the SHA-256 hex digest of the complete log file.

        The file is flushed first so the digest includes events that
        have been written but not yet followed by close().
        """

        if not self._closed:
            self._file.flush()

        digest = hashlib.sha256()

        with open(
            self.log_path,
            "rb",
        ) as file:

            for chunk in iter(
                lambda: file.read(65536),
                b"",
            ):
                digest.update(
                    chunk
                )

        return digest.hexdigest()

    @property
    def event_count(self) -> int:
        """Return the number of events written."""

        return self._event_count

    def __enter__(self) -> "EventLog":
        """Support use with a context manager."""

        return self

    def __exit__(
        self,
        exc_type: object,
        exc_value: object,
        traceback: object,
    ) -> None:
        """Close the file when leaving a with block."""

        self.close()