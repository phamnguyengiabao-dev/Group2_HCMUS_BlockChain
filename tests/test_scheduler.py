import pytest

from src.network import Envelope
from src.scheduler import Scheduler


def _envelope(logical_time: int, insertion_seq: int) -> Envelope:
    return Envelope(
        sender="sender",
        receiver="receiver",
        payload=f"{insertion_seq}".encode("ascii"),
        logical_time=logical_time,
        insertion_seq=insertion_seq,
    )


def test_scheduler_orders_by_logical_time_then_insertion_sequence():
    scheduler = Scheduler()

    scheduler.enqueue(_envelope(2, 8))
    scheduler.enqueue(_envelope(1, 2))
    scheduler.enqueue(_envelope(1, 1))

    assert [scheduler.pop().ordering_key() for _ in range(3)] == [
        (1, 1),
        (1, 2),
        (2, 8),
    ]
    assert scheduler.logical_time == 2
    assert scheduler.empty()


def test_scheduler_empty_operations_are_deterministic():
    scheduler = Scheduler()

    assert len(scheduler) == 0
    assert scheduler.empty()
    assert scheduler.peek() is None
    assert scheduler.pop() is None
    assert scheduler.run_next() is None


def test_scheduler_rejects_wrong_type_duplicate_key_and_past_time():
    scheduler = Scheduler()
    first = _envelope(3, 4)

    with pytest.raises(TypeError):
        scheduler.schedule("not an envelope")

    scheduler.schedule(first)

    with pytest.raises(ValueError, match="duplicate"):
        scheduler.schedule(_envelope(3, 4))

    assert scheduler.pop() == first

    with pytest.raises(ValueError, match="past"):
        scheduler.schedule(_envelope(2, 9))


def test_scheduler_run_next_invokes_handler_in_queue_order():
    scheduler = Scheduler()
    first = _envelope(0, 1)
    second = _envelope(1, 2)
    seen: list[Envelope] = []

    scheduler.schedule(first)
    scheduler.schedule(second)

    assert scheduler.run_next(seen.append) == first
    assert scheduler.run_next(seen.append) == second
    assert seen == [first, second]

