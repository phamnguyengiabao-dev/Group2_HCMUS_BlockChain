"""Deterministic logical-time scheduler for simulated network envelopes.

The scheduler is deliberately single-threaded: callers enqueue immutable
``Envelope`` instances and consume them in the canonical order
``(logical_time, insertion_seq)``.  No wall clock or process-global state is
used, so replaying the same inputs produces the same delivery sequence.

T3-06: Seeded PRNG
    Create Random(seed) with seed owned by scenario runner
    Never call random.random() 
"""

from __future__ import annotations

import heapq
import random
from typing import Any, Callable, Sequence, TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - imported only for static type checkers
    from src.network import Envelope


class Scheduler:
    """Priority queue ordered by logical time and insertion sequence, 
    plus an optional seeded PRNG owned by the scheduler for deterministic
    network-fault decisions (delay jitter, drop, duplicate, etc.)."""

    def __init__(self, seed: int | None = None) -> None:
        self._queue: list[tuple[int, int, "Envelope"]] = []
        self._active: dict[tuple[int, int], "Envelope"] = {}
        self._seen_keys: set[tuple[int, int]] = set()
        self._logical_time = 0
        self._last_ordering_key: tuple[int, int] | None = None

        self._seed = seed
        self._rng = random.Random(seed) if seed is not None else None


    # ---- seeded PRNG: the only source of randomness for network decisions-----------------------------
    @property
    def seed(self) -> int | None:
        return self._seed

    def _require_rng(self) -> random.Random:
        if self._rng is None:
            raise RuntimeError(
                "Scheduler has no seed; PRNG-driven network conditions are disabled."
                "Construct Scheduler(seed=...) to enable them."
            )
        return self._rng
    
    def rng_random(self) -> float:
        """
        A float in [0.0, 1.0) from the SEEDED instance - this is
        Random(seed).random(), never the module-level random.random(). 
        """
        return self._require_rng().random()

    def rng_roll(self, probability: float) -> bool:
        """
        Deterministic Bernoulli draw: True with given probability
        for simple yes/no gates.
        """
        if not (0.0 <= probability <= 1.0):
            raise ValueError("probability must be in [0.0, 1.0]")
        if probability == 0.0:
            return False
        if probability == 1.0:
            return True
        return self.rng_random() < probability

    def rng_randint(self, a: int, b: int) -> int:
        """Inclusive [a, b], e.g. a random delay in logical-time units."""
        if b < a:
            raise ValueError("rng_randint requires b >= a")
        if a == b:
            return a
        return self._require_rng().randint(a, b)

    def rng_choice_sorted(self, sorted_sequence: list) -> Any:
        """
        Pick one element from an already-sorted sequence. Takes a
        pre-sorted sequence rather than sorting internally, 
        so the caller is forced to iterate peers/validators/etc.
        This function cannot silently hide an unsorted input.
        """
        if not sorted_sequence:
            raise ValueError("sorted_sequence must not be empty")
        return self._require_rng().choice(sorted_sequence)

    def rng_shuffle_copy(self, sorted_sequence: list) -> list:
        """
        Return a new, deterministically shuffled copy; input unmodified.
        """
        copy = list(sorted_sequence)
        self._require_rng().shuffle(copy)
        return copy


    @staticmethod
    def _require_envelope(envelope: object) -> "Envelope":
        # Import lazily to avoid the scheduler/network module cycle.  The
        # runtime check remains strict: duck-typed objects are not accepted.
        from src.network import Envelope

        if not isinstance(envelope, Envelope):
            raise TypeError(
                "envelope must be Envelope"
            )
        return envelope

    def schedule(self, envelope: "Envelope") -> "Envelope":
        """Enqueue an envelope and return it.

        Envelopes scheduled before the first pop may be supplied in any order;
        the heap determines the canonical sequence.  Once logical time has
        advanced, an envelope from an earlier tick is rejected rather than
        moving the clock backwards.  A key may be used only once for the
        lifetime of a scheduler, including after cancellation.
        """

        envelope = self._require_envelope(envelope)
        key = envelope.ordering_key()

        if envelope.logical_time < self._logical_time:
            raise ValueError(
                "cannot schedule envelope in the past"
            )

        if (
            self._last_ordering_key is not None
            and envelope.logical_time == self._logical_time
            and key < self._last_ordering_key
        ):
            raise ValueError(
                "cannot schedule ordering key in the past"
            )

        if key in self._seen_keys:
            raise ValueError(
                f"duplicate ordering key: {key!r}"
            )

        self._seen_keys.add(key)
        self._active[key] = envelope
        heapq.heappush(
            self._queue,
            (envelope.logical_time, envelope.insertion_seq, envelope),
        )
        return envelope

    def enqueue(self, envelope: "Envelope") -> "Envelope":
        """Alias for :meth:`schedule` used by queue-oriented callers."""

        return self.schedule(envelope)

    def _discard_stale_heads(self) -> None:
        while self._queue:
            logical_time, insertion_seq, envelope = self._queue[0]
            key = (logical_time, insertion_seq)
            if self._active.get(key) is envelope:
                return
            heapq.heappop(self._queue)

    def peek(self) -> "Envelope | None":
        """Return the next envelope without advancing logical time."""

        self._discard_stale_heads()
        if not self._queue:
            return None
        return self._queue[0][2]

    def pop(self) -> "Envelope | None":
        """Remove and return the next envelope, or ``None`` when empty."""

        self._discard_stale_heads()
        if not self._queue:
            return None

        logical_time, insertion_seq, envelope = heapq.heappop(self._queue)
        key = (logical_time, insertion_seq)
        # The active check in _discard_stale_heads guarantees this is the
        # currently queued instance.
        del self._active[key]

        if logical_time < self._logical_time:
            # This should be unreachable because schedule() rejects past
            # entries, but retaining the guard prevents accidental clock
            # regression if internals are changed later.
            raise RuntimeError(
                "scheduler logical time would move backwards"
            )

        self._logical_time = logical_time
        self._last_ordering_key = key
        return envelope

    def pop_next(self) -> "Envelope | None":
        """Alias for :meth:`pop`."""

        return self.pop()

    def run_next(
        self,
        handler: Callable[["Envelope"], object] | None = None,
    ) -> "Envelope | None":
        """Pop one envelope and optionally pass it to ``handler``.

        The popped envelope is returned regardless of whether a handler is
        supplied.  This keeps queue progression observable and deterministic.
        """

        if handler is not None and not callable(handler):
            raise TypeError(
                "handler must be callable"
            )

        envelope = self.pop()
        if envelope is None:
            return None

        if handler is not None:
            handler(envelope)
        return envelope

    def run(
        self,
        handler: Callable[["Envelope"], object] | None = None,
    ) -> list["Envelope"]:
        """Drain the queue in canonical order and return popped envelopes."""

        result: list["Envelope"] = []
        while not self.empty():
            envelope = self.run_next(handler)
            if envelope is not None:
                result.append(envelope)
        return result

    def cancel(self, envelope: "Envelope") -> bool:
        """Remove a queued envelope without reusing its ordering key.

        Cancellation is primarily an integration aid for ``Network.deliver``
        when a caller explicitly delivers an envelope that ``send`` already
        queued.  The key remains in ``_seen_keys`` so replay cannot enqueue the
        same ordering key twice.
        """

        envelope = self._require_envelope(envelope)
        key = envelope.ordering_key()
        active = self._active.get(key)
        if active is not envelope:
            return False
        del self._active[key]
        return True

    def empty(self) -> bool:
        """Return whether no active envelopes remain queued."""

        self._discard_stale_heads()
        return not self._queue

    def is_empty(self) -> bool:
        """Alias for :meth:`empty`."""

        return self.empty()

    @property
    def logical_time(self) -> int:
        """Current logical time (initially tick zero)."""

        return self._logical_time

    @property
    def current_time(self) -> int:
        """Alias for :attr:`logical_time`."""

        return self._logical_time

    def __len__(self) -> int:
        self._discard_stale_heads()
        return len(self._active)

