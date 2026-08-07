import pytest

from src.fault_injector import FaultInjector
from src.scheduler import Scheduler


def test_no_faults():
    scheduler = Scheduler(seed=123)

    injector = FaultInjector(
        scheduler,
        {
            "faults": {
                "drop_probability": 0.0,
                "delay_probability": 0.0,
                "duplicate_probability": 0.0,
                "reorder_probability": 0.0,
            }
        },
    )

    result = injector.apply()

    assert result.dropped is False
    assert result.delay == 0
    assert result.duplicate_count == 0
    assert result.reorder is False
    assert result.total_copies == 1


def test_always_drop():
    scheduler = Scheduler(seed=123)

    injector = FaultInjector(
        scheduler,
        {
            "faults": {
                "drop_probability": 1.0,
            }
        },
    )

    result = injector.apply()

    assert result.dropped is True
    assert result.total_copies == 0


def test_always_delay():
    scheduler = Scheduler(seed=123)

    injector = FaultInjector(
        scheduler,
        {
            "faults": {
                "delay_probability": 1.0,
                "max_delay": 5,
            }
        },
    )

    result = injector.apply()

    assert result.dropped is False
    assert 1 <= result.delay <= 5


def test_always_duplicate():
    scheduler = Scheduler(seed=123)

    injector = FaultInjector(
        scheduler,
        {
            "faults": {
                "duplicate_probability": 1.0,
                "max_duplicates": 3,
            }
        },
    )

    result = injector.apply()

    assert (
        1
        <= result.duplicate_count
        <= 3
    )

    assert (
        result.total_copies
        == 1 + result.duplicate_count
    )


def test_always_reorder():
    scheduler = Scheduler(seed=123)

    injector = FaultInjector(
        scheduler,
        {
            "faults": {
                "reorder_probability": 1.0,
            }
        },
    )

    result = injector.apply()

    assert result.reorder is True


def test_same_seed_same_faults():
    config = {
        "faults": {
            "drop_probability": 0.2,
            "delay_probability": 0.6,
            "max_delay": 10,
            "duplicate_probability": 0.4,
            "max_duplicates": 2,
            "reorder_probability": 0.5,
        }
    }

    injector_a = FaultInjector(
        Scheduler(seed=999),
        config,
    )

    injector_b = FaultInjector(
        Scheduler(seed=999),
        config,
    )

    results_a = [
        injector_a.apply()
        for _ in range(100)
    ]

    results_b = [
        injector_b.apply()
        for _ in range(100)
    ]

    assert results_a == results_b


def test_scheduler_without_seed():
    scheduler = Scheduler()

    injector = FaultInjector(
        scheduler,
        {
            "faults": {
                "drop_probability": 0.5,
            }
        },
    )

    with pytest.raises(
        RuntimeError,
    ):
        injector.apply()


def test_invalid_probability():
    with pytest.raises(
        ValueError,
    ):
        FaultInjector(
            Scheduler(seed=1),
            {
                "faults": {
                    "drop_probability": 1.1,
                }
            },
        )