import json

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