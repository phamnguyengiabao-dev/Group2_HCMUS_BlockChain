"""
network.py — Deterministic simulated network.

T3-04:
- Define the canonical Envelope type:
    (sender, receiver, payload, logical_time, insertion_seq)
- Serialize fields in exactly that order.
- Integrate with the canonical event schema from T3-01.

T3-01 dependency:
- EventLog writes canonical JSONL records.
- EventType defines the allowed event names.
- Network emits SEND and DELIVER events through EventLog.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.encoding import (
    encode_bytes,
    encode_str,
    encode_uint64,
)
from src.event_log import (
    EventLog,
    EventType,
)


@dataclass(
    frozen=True,
    slots=True,
)
class Envelope:
    """
    Canonical network message envelope.

    Required field order:

        sender
        receiver
        payload
        logical_time
        insertion_seq

    Scheduler ordering:

        (logical_time, insertion_seq)

    `insertion_seq` is the deterministic tie-breaker when multiple
    messages have the same logical delivery time.
    """

    sender: str
    receiver: str
    payload: bytes
    logical_time: int
    insertion_seq: int

    def __post_init__(self) -> None:
        """Validate the envelope fields."""

        if not isinstance(
            self.sender,
            str,
        ):
            raise TypeError(
                "sender must be str, "
                f"got {type(self.sender).__name__}"
            )

        if self.sender == "":
            raise ValueError(
                "sender must not be empty"
            )

        if not isinstance(
            self.receiver,
            str,
        ):
            raise TypeError(
                "receiver must be str, "
                f"got {type(self.receiver).__name__}"
            )

        if self.receiver == "":
            raise ValueError(
                "receiver must not be empty"
            )

        if not isinstance(
            self.payload,
            bytes,
        ):
            raise TypeError(
                "payload must be bytes, "
                f"got {type(self.payload).__name__}"
            )

        if (
            not isinstance(
                self.logical_time,
                int,
            )
            or isinstance(
                self.logical_time,
                bool,
            )
        ):
            raise TypeError(
                "logical_time must be int"
            )

        if not (
            0
            <= self.logical_time
            < 2**64
        ):
            raise ValueError(
                "logical_time must be "
                "in uint64 range"
            )

        if (
            not isinstance(
                self.insertion_seq,
                int,
            )
            or isinstance(
                self.insertion_seq,
                bool,
            )
        ):
            raise TypeError(
                "insertion_seq must be int"
            )

        if not (
            0
            <= self.insertion_seq
            < 2**64
        ):
            raise ValueError(
                "insertion_seq must be "
                "in uint64 range"
            )

    def serialize(self) -> bytes:
        """
        Serialize using the exact canonical field order.

        Order:

            sender
            receiver
            payload
            logical_time
            insertion_seq
        """

        return (
            encode_str(
                self.sender
            )
            + encode_str(
                self.receiver
            )
            + encode_bytes(
                self.payload
            )
            + encode_uint64(
                self.logical_time
            )
            + encode_uint64(
                self.insertion_seq
            )
        )

    def to_bytes(self) -> bytes:
        """Alias for serialize()."""

        return self.serialize()

    def ordering_key(
        self,
    ) -> tuple[int, int]:
        """
        Deterministic network ordering key.

        Earlier logical_time is delivered first.
        insertion_seq breaks ties deterministically.
        """

        return (
            self.logical_time,
            self.insertion_seq,
        )


class Network:
    """
    Minimal deterministic network for T3-04.

    This class integrates Envelope with T3-01's EventLog.

    T3-04 currently:
    - creates envelopes
    - assigns deterministic insertion sequence numbers
    - emits SEND events
    - emits DELIVER events

    Delay, drop, duplication, peer blocking, and fault injection
    belong to later network tasks.
    """

    def __init__(
        self,
        event_log: EventLog,
    ) -> None:
        if not isinstance(
            event_log,
            EventLog,
        ):
            raise TypeError(
                "event_log must be EventLog"
            )

        self._event_log = event_log

        self._next_insertion_seq = 0

        self._next_event_no = 0

    def _write_event(
        self,
        *,
        logical_time: int,
        node_id: str,
        event_type: EventType,
        height: int,
        round: int,
        details: dict[str, Any],
    ) -> None:
        """Write one T3-01 canonical event."""

        self._next_event_no += 1

        self._event_log.write_event(
            event_no=(
                self._next_event_no
            ),
            logical_time=logical_time,
            node_id=node_id,
            event_type=event_type,
            height=height,
            round=round,
            details=details,
        )

    def send(
        self,
        *,
        sender: str,
        receiver: str,
        payload: bytes,
        logical_time: int,
        height: int = 0,
        round: int = 0,
    ) -> Envelope:
        """
        Create an envelope and emit a canonical SEND event.

        The insertion sequence is generated internally so it is
        deterministic and monotonically increasing.
        """

        envelope = Envelope(
            sender=sender,
            receiver=receiver,
            payload=payload,
            logical_time=logical_time,
            insertion_seq=(
                self._next_insertion_seq
            ),
        )

        self._next_insertion_seq += 1

        self._write_event(
            logical_time=logical_time,
            node_id=sender,
            event_type=EventType.SEND,
            height=height,
            round=round,
            details={
                "receiver": receiver,
                "insertion_seq": (
                    envelope.insertion_seq
                ),
                "payload_size": (
                    len(payload)
                ),
            },
        )

        return envelope

    def deliver(
        self,
        envelope: Envelope,
        *,
        height: int = 0,
        round: int = 0,
    ) -> bytes:
        """
        Deliver an envelope and emit a canonical DELIVER event.

        T3-04 returns the raw payload. Actual node dispatch can be
        added by later tasks.
        """

        if not isinstance(
            envelope,
            Envelope,
        ):
            raise TypeError(
                "envelope must be Envelope"
            )

        self._write_event(
            logical_time=(
                envelope.logical_time
            ),
            node_id=(
                envelope.receiver
            ),
            event_type=(
                EventType.DELIVER
            ),
            height=height,
            round=round,
            details={
                "sender": (
                    envelope.sender
                ),
                "insertion_seq": (
                    envelope.insertion_seq
                ),
                "payload_size": (
                    len(
                        envelope.payload
                    )
                ),
            },
        )

        return envelope.payload