import shutil
from pathlib import Path

from src.scenario import ScenarioRunner


def teardown_function():
    """Clean logs created by tests."""
    shutil.rmtree("logs", ignore_errors=True)


def test_load():
    config = {
        "scenario_id": "test_scenario",
        "run_id": "run1",
        "seed": 12345,
    }

    runner = ScenarioRunner(config)
    runner.load()

    assert runner.event_log is not None
    assert runner.scheduler is not None
    assert runner.network is not None
    assert runner.fault_injector is not None

    runner.shutdown()


def test_execute_empty():
    config = {
        "scenario_id": "empty",
        "run_id": "run1",
        "seed": 1,
    }

    runner = ScenarioRunner(config)

    payloads = runner.execute()

    assert payloads == []

    summary = runner.summary()

    assert summary["event_count"] == 0
    assert Path(summary["log_path"]).exists()
    assert len(summary["log_sha256"]) == 64
    assert summary["logical_time"] == 0


def test_execute_with_messages():
    config = {
        "scenario_id": "messages",
        "run_id": "run1",
        "seed": 99,
        "messages": [
            {
                "sender": "A",
                "receiver": "B",
                "payload": b"hello",
                "logical_time": 5,
            },
            {
                "sender": "B",
                "receiver": "C",
                "payload": b"world",
                "logical_time": 7,
            },
        ],
    }

    runner = ScenarioRunner(config)

    payloads = runner.execute()

    assert payloads == [
        b"hello",
        b"world",
    ]

    summary = runner.summary()

    # 2 SEND + 2 DELIVER
    assert summary["event_count"] == 4
    assert summary["logical_time"] == 7