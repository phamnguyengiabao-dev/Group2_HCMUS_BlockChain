import json

import pytest

from src.encoding import (
    encode_bytes,
    encode_str,
    encode_uint64,
)
from src.event_log import EventLog
from src.network import (
    Envelope,
    Network,
)


def test_envelope_serialization():
    envelope = Envelope(
        sender="node_0",
        receiver="node_1",
        payload=b"hello",
        logical_time=10,
        insertion_seq=2,
    )

    expected = (
        encode_str("node_0")
        + encode_str("node_1")
        + encode_bytes(b"hello")
        + encode_uint64(10)
        + encode_uint64(2)
    )

    assert (
        envelope.serialize()
        == expected
    )


def test_ordering_key():
    envelope = Envelope(
        sender="node_0",
        receiver="node_1",
        payload=b"x",
        logical_time=10,
        insertion_seq=2,
    )

    assert (
        envelope.ordering_key()
        == (10, 2)
    )


def test_network_uses_t3_01_events(
    tmp_path,
    monkeypatch,
):
    monkeypatch.chdir(
        tmp_path
    )

    log = EventLog(
        scenario_id="test",
        run_id="run_1",
    )

    network = Network(
        event_log=log
    )

    envelope = network.send(
        sender="node_0",
        receiver="node_1",
        payload=b"hello",
        logical_time=5,
        height=1,
        round=0,
    )

    payload = network.deliver(
        envelope,
        height=1,
        round=0,
    )

    log.close()

    assert payload == b"hello"

    lines = (
        log.log_path
        .read_text(
            encoding="utf-8"
        )
        .splitlines()
    )

    assert len(lines) == 2

    send_event = json.loads(
        lines[0]
    )

    deliver_event = json.loads(
        lines[1]
    )

    assert (
        send_event["event_type"]
        == "SEND"
    )

    assert (
        deliver_event["event_type"]
        == "DELIVER"
    )


def test_insertion_sequence_increases(
    tmp_path,
    monkeypatch,
):
    monkeypatch.chdir(
        tmp_path
    )

    log = EventLog(
        "test",
        "run_1",
    )

    network = Network(
        log
    )

    first = network.send(
        sender="A",
        receiver="B",
        payload=b"1",
        logical_time=10,
    )

    second = network.send(
        sender="A",
        receiver="B",
        payload=b"2",
        logical_time=10,
    )

    log.close()

    assert (
        first.insertion_seq
        == 0
    )

    assert (
        second.insertion_seq
        == 1
    )


def test_network_scheduler_delivers_same_tick_in_insertion_order(
    tmp_path,
    monkeypatch,
):
    monkeypatch.chdir(tmp_path)
    log = EventLog("test", "run_1")
    network = Network(log, bandwidth_limit_bytes_per_tick=5)

    first = network.send(
        sender="A",
        receiver="B",
        payload=b"123",
        logical_time=0,
    )
    second = network.send(
        sender="A",
        receiver="B",
        payload=b"45",
        logical_time=0,
    )

    assert network.run() == [first.payload, second.payload]
    log.close()
    events = [json.loads(line) for line in log.log_path.read_text().splitlines()]
    deliveries = [event for event in events if event["event_type"] == "DELIVER"]
    assert [event["logical_time"] for event in deliveries] == [0, 0]
    assert [event["details"]["insertion_seq"] for event in deliveries] == [
        first.insertion_seq,
        second.insertion_seq,
    ]


def test_network_bandwidth_defers_overflow_to_next_tick(
    tmp_path,
    monkeypatch,
):
    monkeypatch.chdir(tmp_path)
    log = EventLog("test", "run_1")
    network = Network(log, bandwidth_limit_bytes_per_tick=5)

    first = network.send(
        sender="A",
        receiver="B",
        payload=b"1234",
        logical_time=7,
    )
    second = network.send(
        sender="A",
        receiver="B",
        payload=b"56",
        logical_time=7,
    )

    assert network.run() == [first.payload, second.payload]
    log.close()
    events = [json.loads(line) for line in log.log_path.read_text().splitlines()]
    deliveries = [event for event in events if event["event_type"] == "DELIVER"]
    assert [event["logical_time"] for event in deliveries] == [7, 8]


def test_network_bandwidth_exact_fit_and_independent_ticks(
    tmp_path,
    monkeypatch,
):
    monkeypatch.chdir(tmp_path)
    log = EventLog("test", "run_1")
    network = Network(log, bandwidth_limit_bytes_per_tick=5)

    network.send(sender="A", receiver="B", payload=b"123", logical_time=2)
    network.send(sender="A", receiver="B", payload=b"45", logical_time=2)
    network.send(sender="A", receiver="B", payload=b"67890", logical_time=3)

    assert len(network.run()) == 3
    log.close()
    events = [json.loads(line) for line in log.log_path.read_text().splitlines()]
    deliveries = [event for event in events if event["event_type"] == "DELIVER"]
    assert [event["logical_time"] for event in deliveries] == [2, 2, 3]


def test_network_rejects_oversized_payload_and_invalid_bandwidth_limit(
    tmp_path,
    monkeypatch,
):
    monkeypatch.chdir(tmp_path)
    for invalid in (0, -1, True, 1.5):
        invalid_log = EventLog("test", f"run_{invalid}")
        with pytest.raises((TypeError, ValueError)):
            Network(
                invalid_log,
                bandwidth_limit_bytes_per_tick=invalid,
            )
        invalid_log.close()

    log = EventLog("test", "run_ok")
    network = Network(log, bandwidth_limit_bytes_per_tick=3)
    with pytest.raises(ValueError, match="payload"):
        network.send(sender="A", receiver="B", payload=b"1234", logical_time=0)
    log.close()


def test_network_repeated_explicit_delivery_is_rejected(
    tmp_path,
    monkeypatch,
):
    monkeypatch.chdir(tmp_path)
    log = EventLog("test", "run_repeat")
    network = Network(log, bandwidth_limit_bytes_per_tick=5)
    envelope = network.send(
        sender="A",
        receiver="B",
        payload=b"ok",
        logical_time=0,
    )

    assert network.deliver(envelope) == b"ok"
    with pytest.raises(ValueError, match="already delivered"):
        network.deliver(envelope)

    log.close()
    events = [json.loads(line) for line in log.log_path.read_text().splitlines()]
    assert [event["event_type"] for event in events] == [
        "SEND",
        "DELIVER",
    ]


def test_block_peer_logs_event(
    tmp_path,
    monkeypatch,
):
    monkeypatch.chdir(tmp_path)
    log = EventLog("test", "run_block")
    network = Network(log)

    network.block_peer("validator_00000001")

    log.close()
    events = [json.loads(line) for line in log.log_path.read_text().splitlines()]
    assert len(events) == 1
    assert events[0]["event_type"] == "PEER_BLOCK"
    assert events[0]["node_id"] == "validator_00000001"
    assert events[0]["details"]["peer_id"] == "validator_00000001"


def test_unblock_peer_logs_event(
    tmp_path,
    monkeypatch,
):
    monkeypatch.chdir(tmp_path)
    log = EventLog("test", "run_unblock")
    network = Network(log)

    network.unblock_peer("validator_00000002")

    log.close()
    events = [json.loads(line) for line in log.log_path.read_text().splitlines()]
    assert len(events) == 1
    assert events[0]["event_type"] == "PEER_UNBLOCK"
    assert events[0]["node_id"] == "validator_00000002"
    assert events[0]["details"]["peer_id"] == "validator_00000002"


def test_block_peer_validation(
    tmp_path,
    monkeypatch,
):
    monkeypatch.chdir(tmp_path)
    log = EventLog("test", "run_validation")
    network = Network(log)

    with pytest.raises(TypeError, match="peer_id must be str"):
        network.block_peer(123)

    with pytest.raises(ValueError, match="peer_id must not be empty"):
        network.block_peer("")

    log.close()


def test_unblock_peer_validation(
    tmp_path,
    monkeypatch,
):
    monkeypatch.chdir(tmp_path)
    log = EventLog("test", "run_unblock_validation")
    network = Network(log)

    with pytest.raises(TypeError, match="peer_id must be str"):
        network.unblock_peer(456)

    with pytest.raises(ValueError, match="peer_id must not be empty"):
        network.unblock_peer("")

    log.close()


def test_block_unblock_sequence(
    tmp_path,
    monkeypatch,
):
    monkeypatch.chdir(tmp_path)
    log = EventLog("test", "run_sequence")
    network = Network(log)

    network.block_peer("validator_00000003")
    network.unblock_peer("validator_00000003")
    network.block_peer("validator_00000003")

    log.close()
    events = [json.loads(line) for line in log.log_path.read_text().splitlines()]
    assert [e["event_type"] for e in events] == [
        "PEER_BLOCK",
        "PEER_UNBLOCK",
        "PEER_BLOCK",
    ]
