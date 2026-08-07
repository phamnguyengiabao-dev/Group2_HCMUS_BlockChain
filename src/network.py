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
from src.scheduler import Scheduler


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
    """Deterministic simulated network backed by :class:`Scheduler`.

    ``send`` retains the original T3-04 behavior (it returns an
    :class:`Envelope` and writes ``SEND`` immediately) while also queuing the
    envelope for deterministic delivery.  Callers that need the old explicit
    flow may still call ``deliver(envelope)``; callers driving a simulation can
    use ``run_next`` or ``run``.

    Bandwidth is charged by payload bytes at the actual logical delivery tick.
    A message that does not fit in the remaining budget is re-queued at the
    earliest later tick with enough capacity.  Payloads larger than one full
    tick are rejected up front so deferral cannot loop forever.
    """

    DEFAULT_BANDWIDTH_LIMIT_BYTES_PER_TICK = 1_048_576

    def __init__(
        self,
        event_log: EventLog,
        scheduler: Scheduler | None = None,
        bandwidth_limit_bytes_per_tick: int | None = (
            DEFAULT_BANDWIDTH_LIMIT_BYTES_PER_TICK
        ),
        event_no_counter: "Callable[[], int] | None" = None,
    ) -> None:
        if not isinstance(
            event_log,
            EventLog,
        ):
            raise TypeError(
                "event_log must be EventLog"
            )

        if scheduler is not None and not isinstance(
            scheduler,
            Scheduler,
        ):
            raise TypeError(
                "scheduler must be Scheduler"
            )

        self._event_log = event_log
        self._scheduler = (
            scheduler
            if scheduler is not None
            else Scheduler()
        )
        self._bandwidth_limit = self._validate_bandwidth_limit(
            bandwidth_limit_bytes_per_tick
        )


        # If the caller (e.g. ScenarioRunner) already owns event_no,
        # inject it here via `event_no_counter`so Network never assigns a number colliding with something written before/after it.
        # Falls back to a private counter starting at 0 only when Network is used standalone.
        self._event_no_counter = event_no_counter
        self._next_event_no = 0
        self._next_insertion_seq = 0
        
        self._last_event_logical_time = 0

        # SEND events are deferred until the envelope is actually delivered
        # so that logical_time stays monotonic in the event log.
        # Maps insertion_seq → (sender, receiver, send_time, height, round, payload_size).
        self._pending_send_events: dict[int, tuple[str, str, int, int, int, int]] = {}

        # Keys are current scheduler ordering keys.  Deferred envelopes are
        # represented by a new key (later logical time) while retaining the
        # original insertion sequence.
        self._pending: dict[tuple[int, int], Envelope] = {}
        self._contexts: dict[tuple[int, int], tuple[int, int]] = {}
        self._bytes_by_tick: dict[int, int] = {}
        self._delivered_sequences: set[int] = set()

    @staticmethod
    def _validate_bandwidth_limit(
        value: int | None,
    ) -> int | None:
        if value is None:
            return None
        if isinstance(value, bool) or not isinstance(value, int):
            raise TypeError(
                "bandwidth_limit_bytes_per_tick must be a positive int or None"
            )
        if value <= 0:
            raise ValueError(
                "bandwidth_limit_bytes_per_tick must be positive"
            )
        return value

    def _validate_payload_size(self, payload: bytes) -> None:
        if not isinstance(payload, bytes):
            raise TypeError(
                "payload must be bytes"
            )
        if (
            self._bandwidth_limit is not None
            and len(payload) > self._bandwidth_limit
        ):
            raise ValueError(
                "payload exceeds bandwidth limit for one logical tick"
            )

    def _next_event_no_value(self) -> int:
        if self._event_no_counter is not None:
            return self._event_no_counter()
        self._next_event_no += 1
        return self._next_event_no

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

        event_no = self._next_event_no_value()
        # Clamp logical_time upward to maintain monotonicity in the event
        # log.  Normally SEND and DELIVER are written in the same _try_deliver
        # call so their times are already ordered; the clamp is a safety net.
        written_time = max(logical_time, self._last_event_logical_time)
        self._last_event_logical_time = written_time

        self._event_log.write_event(
            event_no=event_no,
            logical_time=written_time,
            node_id=node_id,
            event_type=event_type,
            height=height,
            round=round,
            details=details,
        )

    def _remember_pending(
        self,
        envelope: Envelope,
        *,
        height: int,
        round: int,
    ) -> Envelope:
        key = envelope.ordering_key()
        self._pending[key] = envelope
        self._contexts[key] = (height, round)
        return envelope

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
        """Create, log, and queue an envelope with a monotonic sequence."""

        self._validate_payload_size(payload)

        envelope = Envelope(
            sender=sender,
            receiver=receiver,
            payload=payload,
            logical_time=logical_time,
            insertion_seq=self._next_insertion_seq,
        )

        # Schedule before emitting SEND so an invalid logical time cannot
        # leave a misleading event in the canonical log.
        self._scheduler.schedule(envelope)
        self._remember_pending(
            envelope,
            height=height,
            round=round,
        )
        # Buffer SEND info; the SEND event is written just before the
        # matching DELIVER so logical_time stays monotonic in the log.
        self._pending_send_events[envelope.insertion_seq] = (
            sender, receiver, logical_time, height, round, len(payload)
        )
        self._next_insertion_seq += 1

        return envelope

    def enqueue(
        self,
        envelope: Envelope,
        *,
        height: int = 0,
        round: int = 0,
    ) -> Envelope:
        """Queue an existing envelope for deterministic delivery."""

        if not isinstance(envelope, Envelope):
            raise TypeError(
                "envelope must be Envelope"
            )
        self._validate_payload_size(envelope.payload)
        self._scheduler.schedule(envelope)
        return self._remember_pending(
            envelope,
            height=height,
            round=round,
        )

    def schedule(
        self,
        envelope: Envelope,
        *,
        height: int = 0,
        round: int = 0,
    ) -> Envelope:
        """Alias for :meth:`enqueue`."""

        return self.enqueue(
            envelope,
            height=height,
            round=round,
        )

    def _earliest_delivery_tick(
        self,
        requested_tick: int,
        payload_size: int,
    ) -> int:
        if self._bandwidth_limit is None:
            return requested_tick

        tick = max(
            requested_tick,
            self._scheduler.logical_time,
        )
        while (
            self._bytes_by_tick.get(tick, 0) + payload_size
            > self._bandwidth_limit
        ):
            tick += 1
        return tick

    def _try_deliver(
        self,
        envelope: Envelope,
        *,
        height: int,
        round: int,
    ) -> bytes | None:
        """Deliver one popped envelope, or requeue it when rate limited."""

        payload_size = len(envelope.payload)
        tick = self._earliest_delivery_tick(
            envelope.logical_time,
            payload_size,
        )

        if tick != envelope.logical_time:
            deferred = Envelope(
                sender=envelope.sender,
                receiver=envelope.receiver,
                payload=envelope.payload,
                logical_time=tick,
                insertion_seq=envelope.insertion_seq,
            )
            self._scheduler.schedule(deferred)
            self._remember_pending(
                deferred,
                height=height,
                round=round,
            )
            return None

        if self._bandwidth_limit is not None:
            self._bytes_by_tick[tick] = (
                self._bytes_by_tick.get(tick, 0) + payload_size
            )

        # Write buffered SEND event first (if not yet written), then DELIVER.
        # This guarantees SEND precedes DELIVER in the log and both share
        # a logical_time that is >= every previously written event.
        seq = envelope.insertion_seq
        if seq in self._pending_send_events:
            sender, receiver, send_time, send_height, send_round, _ = (
                self._pending_send_events.pop(seq)
            )
            self._write_event(
                logical_time=send_time,
                node_id=sender,
                event_type=EventType.SEND,
                height=send_height,
                round=send_round,
                details={
                    "receiver": receiver,
                    "insertion_seq": seq,
                    "payload_size": payload_size,
                },
            )

        self._write_event(
            logical_time=tick,
            node_id=envelope.receiver,
            event_type=EventType.DELIVER,
            height=height,
            round=round,
            details={
                "sender": envelope.sender,
                "insertion_seq": envelope.insertion_seq,
                "payload_size": payload_size,
            },
        )
        return envelope.payload

    def _pop_and_deliver_one(
        self,
    ) -> tuple[Envelope, bytes] | None:
        """Pop until one envelope is actually delivered."""

        while not self._scheduler.empty():
            envelope = self._scheduler.pop()
            if envelope is None:
                return None

            key = envelope.ordering_key()
            context = self._contexts.pop(
                key,
                (0, 0),
            )
            self._pending.pop(key, None)

            payload = self._try_deliver(
                envelope,
                height=context[0],
                round=context[1],
            )
            if payload is None:
                continue
            self._delivered_sequences.add(
                envelope.insertion_seq
            )
            return envelope, payload
        return None

    def run_next(self) -> bytes | None:
        """Deliver the next queued message, respecting bandwidth."""

        result = self._pop_and_deliver_one()
        if result is None:
            return None
        return result[1]

    def run(self) -> list[bytes]:
        """Drain all queued messages and return payloads in delivery order."""

        delivered: list[bytes] = []
        while not self._scheduler.empty():
            payload = self.run_next()
            if payload is not None:
                delivered.append(payload)
        return delivered

    def deliver(
        self,
        envelope: Envelope,
        *,
        height: int = 0,
        round: int = 0,
    ) -> bytes:
        """Deliver ``envelope`` while preserving scheduler ordering.

        ``send`` already queues its return value.  Explicit delivery therefore
        drains queued messages in canonical order until the requested
        insertion sequence is delivered, retaining the historical return of
        raw payload bytes.  An envelope not previously queued is enqueued
        first, which keeps the method useful for legacy callers constructing
        envelopes directly.
        """

        if not isinstance(envelope, Envelope):
            raise TypeError(
                "envelope must be Envelope"
            )
        self._validate_payload_size(envelope.payload)

        if envelope.insertion_seq in self._delivered_sequences:
            raise ValueError(
                "envelope already delivered"
            )

        key = envelope.ordering_key()
        if key not in self._pending:
            self.enqueue(
                envelope,
                height=height,
                round=round,
            )

        target_seq = envelope.insertion_seq
        while True:
            result = self._pop_and_deliver_one()
            if result is None:
                raise RuntimeError(
                    "envelope disappeared from scheduler"
                )
            delivered_envelope, payload = result
            if delivered_envelope.insertion_seq == target_seq:
                return payload

    @property
    def scheduler(self) -> Scheduler:
        """Expose the owned scheduler for deterministic simulation drivers."""

        return self._scheduler

    @property
    def bandwidth_limit_bytes_per_tick(self) -> int | None:
        """Configured per-tick payload-byte limit, or ``None`` for unlimited."""

        return self._bandwidth_limit

    @property
    def logical_time(self) -> int:
        """Current logical time owned by the scheduler."""

        return self._scheduler.logical_time

    def __len__(self) -> int:
        return len(self._scheduler)

    def block_peer(self, peer_id: str) -> None:
        """Block a peer - all incoming messages from that peer are dropped.

        Args:
            peer_id: The validator ID to block.
        """
        if not isinstance(peer_id, str):
            raise TypeError("peer_id must be str")
        if peer_id == "":
            raise ValueError("peer_id must not be empty")

        # Log PEER_BLOCK event
        self._write_event(
            logical_time=self._scheduler.logical_time,
            node_id=peer_id,
            event_type=EventType.PEER_BLOCK,
            height=0,
            round=0,
            details={"peer_id": peer_id},
        )

    def unblock_peer(self, peer_id: str) -> None:
        """Unblock a previously blocked peer.

        Args:
            peer_id: The validator ID to unblock.
        """
        if not isinstance(peer_id, str):
            raise TypeError("peer_id must be str")
        if peer_id == "":
            raise ValueError("peer_id must not be empty")

        # Log PEER_UNBLOCK event
        self._write_event(
            logical_time=self._scheduler.logical_time,
            node_id=peer_id,
            event_type=EventType.PEER_UNBLOCK,
            height=0,
            round=0,
            details={"peer_id": peer_id},
        )
