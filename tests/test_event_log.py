import json

import pytest

from src.event_log import (
    CANONICAL_EVENT_TYPES,
    EVENT_FIELD_ORDER,
    EventLog,
    EventType,
)


def test_exactly_18_event_types():
    assert len(EventType) == 21

    assert len(
        CANONICAL_EVENT_TYPES
    ) == 21


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
        "SCENARIO_START",
        "SCENARIO_END",
        "NODE_INIT",
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


def test_no_extra_whitespace_in_output(tmp_path, monkeypatch):
    """F-49: canonical JSON Lines must not contain whitespace beyond the
    single trailing newline -- no space after ':' or ',', no indentation."""

    monkeypatch.chdir(tmp_path)

    log = EventLog("scenario_1", "run_1")

    log.write_event(
        event_no=1,
        logical_time=5,
        node_id="node_0",
        event_type="LOCK",
        height=1,
        round=0,
        details={"z": [1, 2, 3], "a": None, "m": True},
    )

    log.close()

    line = log.log_path.read_text(encoding="utf-8")

    assert line.endswith("\n")
    assert not line[:-1].endswith("\n")

    body = line[:-1]
    assert " " not in body
    assert "\t" not in body

    expected_record = {
        "event_no": 1,
        "logical_time": 5,
        "node_id": "node_0",
        "event_type": "LOCK",
        "height": 1,
        "round": 0,
        "details": {"a": None, "m": True, "z": [1, 2, 3]},
    }
    expected_body = json.dumps(
        expected_record,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    assert body == expected_body


def test_output_is_utf8_and_preserves_non_ascii(tmp_path, monkeypatch):
    """F-49: canonical UTF-8 -- non-ASCII text is written as literal UTF-8
    bytes, not \\uXXXX escapes, and the file carries no BOM."""

    monkeypatch.chdir(tmp_path)

    log = EventLog("scenario_1", "run_1")

    log.write_event(
        event_no=1,
        logical_time=0,
        node_id="nut_viet",
        event_type="REJECT",
        height=1,
        round=0,
        details={"ghi_chu": "kiểm tra chuẩn UTF-8"},
    )

    log.close()

    raw_bytes = log.log_path.read_bytes()

    # No UTF-8 BOM.
    assert not raw_bytes.startswith(b"\xef\xbb\xbf")

    # Round-trips as valid UTF-8.
    text = raw_bytes.decode("utf-8")

    # The Vietnamese text appears literally, not as \u escapes.
    assert "kiểm tra chuẩn UTF-8" in text
    assert "\\u" not in text

    record = json.loads(text)
    assert record["details"]["ghi_chu"] == "kiểm tra chuẩn UTF-8"


def test_newline_after_every_event_and_only_lf(tmp_path, monkeypatch):
    """F-49: exactly one newline after each event, using bare '\\n'."""

    monkeypatch.chdir(tmp_path)

    log = EventLog("scenario_1", "run_1")

    for event_no in (1, 2, 3):
        log.write_event(
            event_no=event_no,
            logical_time=event_no,
            node_id="node_0",
            event_type="TIMEOUT",
            height=1,
            round=0,
            details={},
        )

    log.close()

    raw_bytes = log.log_path.read_bytes()

    # No CR anywhere -- lines are terminated by bare LF, not CRLF.
    assert b"\r" not in raw_bytes

    text = raw_bytes.decode("utf-8")
    lines = text.split("\n")

    # 3 events -> 3 content lines + one trailing empty string after the
    # final newline.
    assert len(lines) == 4
    assert lines[-1] == ""
    for line in lines[:-1]:
        assert line != ""
        json.loads(line)


def test_fixed_key_order_holds_across_multiple_events(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    log = EventLog("scenario_1", "run_1")

    for event_no in (1, 2):
        log.write_event(
            event_no=event_no,
            logical_time=event_no,
            node_id="node_0",
            event_type="SEND",
            height=1,
            round=0,
            details={"y": 1, "b": 2},
        )

    log.close()

    lines = log.log_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2

    for line in lines:
        record = json.loads(line)
        assert list(record.keys()) == list(EVENT_FIELD_ORDER)
        assert list(record["details"].keys()) == ["b", "y"]


# ============================================================
# T3-03: event_no monotonic
# ============================================================

def test_event_no_must_start_at_one(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    log = EventLog("scenario_1", "run_1")

    with pytest.raises(ValueError, match="NON_MONOTONIC_EVENT_NO"):
        log.write_event(
            event_no=2,
            logical_time=0,
            node_id="node_0",
            event_type="SEND",
            height=1,
            round=0,
            details={},
        )

    log.close()


def test_event_no_increments_by_one_across_events(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    log = EventLog("scenario_1", "run_1")

    for event_no in (1, 2, 3):
        log.write_event(
            event_no=event_no,
            logical_time=0,
            node_id="node_0",
            event_type="SEND",
            height=1,
            round=0,
            details={},
        )

    log.close()

    assert log.event_count == 3


def test_event_no_gap_is_rejected(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    log = EventLog("scenario_1", "run_1")

    log.write_event(
        event_no=1,
        logical_time=0,
        node_id="node_0",
        event_type="SEND",
        height=1,
        round=0,
        details={},
    )

    with pytest.raises(ValueError, match="NON_MONOTONIC_EVENT_NO"):
        log.write_event(
            event_no=3,
            logical_time=0,
            node_id="node_0",
            event_type="SEND",
            height=1,
            round=0,
            details={},
        )

    log.close()


def test_event_no_duplicate_is_rejected(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    log = EventLog("scenario_1", "run_1")

    log.write_event(
        event_no=1,
        logical_time=0,
        node_id="node_0",
        event_type="SEND",
        height=1,
        round=0,
        details={},
    )

    with pytest.raises(ValueError, match="NON_MONOTONIC_EVENT_NO"):
        log.write_event(
            event_no=1,
            logical_time=0,
            node_id="node_0",
            event_type="SEND",
            height=1,
            round=0,
            details={},
        )

    log.close()


def test_event_no_going_backward_is_rejected(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    log = EventLog("scenario_1", "run_1")

    for event_no in (1, 2):
        log.write_event(
            event_no=event_no,
            logical_time=0,
            node_id="node_0",
            event_type="SEND",
            height=1,
            round=0,
            details={},
        )

    with pytest.raises(ValueError, match="NON_MONOTONIC_EVENT_NO"):
        log.write_event(
            event_no=2,
            logical_time=0,
            node_id="node_0",
            event_type="SEND",
            height=1,
            round=0,
            details={},
        )

    log.close()


def test_event_no_wrong_type_raises_type_error(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    log = EventLog("scenario_1", "run_1")

    with pytest.raises(TypeError, match="event_no"):
        log.write_event(
            event_no="1",
            logical_time=0,
            node_id="node_0",
            event_type="SEND",
            height=1,
            round=0,
            details={},
        )

    log.close()


def test_event_no_bool_is_rejected_as_type_error(tmp_path, monkeypatch):
    """bool is a subclass of int in Python -- must not silently pass as
    a valid event_no."""

    monkeypatch.chdir(tmp_path)

    log = EventLog("scenario_1", "run_1")

    with pytest.raises(TypeError, match="event_no"):
        log.write_event(
            event_no=True,
            logical_time=0,
            node_id="node_0",
            event_type="SEND",
            height=1,
            round=0,
            details={},
        )

    log.close()


# ============================================================
# T3-03: logical_time accuracy
# ============================================================

def test_logical_time_negative_is_rejected(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    log = EventLog("scenario_1", "run_1")

    with pytest.raises(ValueError, match="INVALID_LOGICAL_TIME"):
        log.write_event(
            event_no=1,
            logical_time=-1,
            node_id="node_0",
            event_type="SEND",
            height=1,
            round=0,
            details={},
        )

    log.close()


def test_logical_time_may_repeat_across_events(tmp_path, monkeypatch):
    """Multiple events can share the same logical tick (e.g. several
    messages delivered at the same simulated time)."""

    monkeypatch.chdir(tmp_path)

    log = EventLog("scenario_1", "run_1")

    for event_no in (1, 2, 3):
        log.write_event(
            event_no=event_no,
            logical_time=5,
            node_id="node_0",
            event_type="SEND",
            height=1,
            round=0,
            details={},
        )

    log.close()

    assert log.event_count == 3


def test_logical_time_going_backward_is_rejected(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    log = EventLog("scenario_1", "run_1")

    log.write_event(
        event_no=1,
        logical_time=5,
        node_id="node_0",
        event_type="SEND",
        height=1,
        round=0,
        details={},
    )

    with pytest.raises(ValueError, match="NON_MONOTONIC_LOGICAL_TIME"):
        log.write_event(
            event_no=2,
            logical_time=4,
            node_id="node_0",
            event_type="SEND",
            height=1,
            round=0,
            details={},
        )

    log.close()


def test_logical_time_wrong_type_raises_type_error(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    log = EventLog("scenario_1", "run_1")

    with pytest.raises(TypeError, match="logical_time"):
        log.write_event(
            event_no=1,
            logical_time=1.5,
            node_id="node_0",
            event_type="SEND",
            height=1,
            round=0,
            details={},
        )

    log.close()


def test_logical_time_bool_is_rejected_as_type_error(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    log = EventLog("scenario_1", "run_1")

    with pytest.raises(TypeError, match="logical_time"):
        log.write_event(
            event_no=1,
            logical_time=False,
            node_id="node_0",
            event_type="SEND",
            height=1,
            round=0,
            details={},
        )

    log.close()


# ============================================================
# T3-03: guard ordering
# ============================================================

def test_event_no_check_runs_before_logical_time_check(tmp_path, monkeypatch):
    """Both event_no and logical_time are invalid -- event_no should be
    reported first since it is checked first."""

    monkeypatch.chdir(tmp_path)

    log = EventLog("scenario_1", "run_1")

    with pytest.raises(ValueError, match="NON_MONOTONIC_EVENT_NO"):
        log.write_event(
            event_no=5,
            logical_time=-1,
            node_id="node_0",
            event_type="SEND",
            height=1,
            round=0,
            details={},
        )

    log.close()


def test_type_checks_run_before_monotonic_checks(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    log = EventLog("scenario_1", "run_1")

    # event_no is the wrong type AND would also violate monotonicity if
    # coerced -- the TypeError must win.
    with pytest.raises(TypeError, match="event_no"):
        log.write_event(
            event_no="99",
            logical_time=0,
            node_id="node_0",
            event_type="SEND",
            height=1,
            round=0,
            details={},
        )

    log.close()


def test_rejected_event_does_not_advance_state(tmp_path, monkeypatch):
    """A failed write_event() call must not consume the event_no /
    logical_time sequence -- the next valid call still expects event_no=1."""

    monkeypatch.chdir(tmp_path)

    log = EventLog("scenario_1", "run_1")

    with pytest.raises(ValueError, match="INVALID_LOGICAL_TIME"):
        log.write_event(
            event_no=1,
            logical_time=-1,
            node_id="node_0",
            event_type="SEND",
            height=1,
            round=0,
            details={},
        )

    # Still expects event_no=1 -- the rejected call did not count.
    log.write_event(
        event_no=1,
        logical_time=0,
        node_id="node_0",
        event_type="SEND",
        height=1,
        round=0,
        details={},
    )

    log.close()

    assert log.event_count == 1


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