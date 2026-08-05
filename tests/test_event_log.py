import json

import pytest

from src.event_log import (
    CANONICAL_EVENT_TYPES,
    EVENT_FIELD_ORDER,
    EventLog,
    EventType,
)


def test_exactly_18_event_types():
    assert len(EventType) == 18

    assert len(
        CANONICAL_EVENT_TYPES
    ) == 18


def test_event_type_order():
    assert CANONICAL_EVENT_TYPES == (
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


def test_fixed_top_level_field_order():
    assert EVENT_FIELD_ORDER == (
        "event_no",
        "logical_time",
        "node_id",
        "event_type",
        "height",
        "round",
        "details",
    )


def test_write_canonical_event(
    tmp_path,
    monkeypatch,
):
    monkeypatch.chdir(
        tmp_path
    )

    log = EventLog(
        "scenario_1",
        "run_1",
    )

    log.write_event(
        event_no=1,
        logical_time=10,
        node_id="node_0",
        event_type="PROPOSE",
        height=2,
        round=3,
        details={
            "z": 1,
            "a": 2,
            "m": 3,
        },
    )

    log.close()

    line = (
        log.log_path
        .read_text(
            encoding="utf-8"
        )
        .strip()
    )

    record = json.loads(
        line
    )

    assert list(
        record.keys()
    ) == [
        "event_no",
        "logical_time",
        "node_id",
        "event_type",
        "height",
        "round",
        "details",
    ]

    assert list(
        record["details"].keys()
    ) == [
        "a",
        "m",
        "z",
    ]


def test_unknown_event_type_rejected(
    tmp_path,
    monkeypatch,
):
    monkeypatch.chdir(
        tmp_path
    )

    log = EventLog(
        "scenario_1",
        "run_1",
    )

    with pytest.raises(
        ValueError,
        match="UNKNOWN_EVENT_TYPE",
    ):
        log.write_event(
            event_no=1,
            logical_time=1,
            node_id="node_0",
            event_type="INVALID",
            height=1,
            round=0,
            details={},
        )

    log.close()


def test_event_type_enum_accepted(
    tmp_path,
    monkeypatch,
):
    monkeypatch.chdir(
        tmp_path
    )

    log = EventLog(
        "scenario_1",
        "run_1",
    )

    log.write_event(
        event_no=1,
        logical_time=1,
        node_id="node_0",
        event_type=EventType.CRASH,
        height=1,
        round=0,
        details={},
    )

    log.close()

    record = json.loads(
        log.log_path.read_text(
            encoding="utf-8"
        )
    )

    assert (
        record["event_type"]
        == "CRASH"
    )