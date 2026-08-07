"""
verify_determinism.py — Determinism verification script.

Requirement (Lab01.pdf §8):
  Re-running the same configuration must yield byte-identical logs and
  the same final state hash.  Logs are the primary evidence of
  correctness and include every consensus or network event that
  influences the outcome.

This script runs the T8 scenario (real consensus with fault injection:
delay, duplicate, reorder) TWICE with the same seed and configuration,
then verifies:
  1. Log file bytes are identical.
  2. SHA-256 of the log files match.
  3. Final state_hash at every node is identical.
  4. Finalized (height, block_hash) at every node is identical.

Consensus events logged per run:
  SCENARIO_START, NODE_INIT,
  SEND, DELIVER (all network messages),
  PROPOSE, PREVOTE, LOCK, PRECOMMIT (one per validator per phase),
  FINALIZE (one per validator),
  SCENARIO_END

Exit code: 0 = PASS, 1 = FAIL.

Usage:
    python tests/verify_determinism.py
    python tests/verify_determinism.py --scenario t1_normal   # alternate scenario
"""

from __future__ import annotations

import json
import os
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from src.consensus import (  # noqa: E402
    ConsensusState,
    apply_lock,
    make_precommit,
    make_prevote,
    propose,
    select_proposer,
    try_finalize,
)
from src.crypto import hash_bytes, sign  # noqa: E402
from src.event_log import EventType  # noqa: E402
from src.executor import ExecutionConfig  # noqa: E402
from src.identity import load_validator_keys  # noqa: E402
from src.ledger import Ledger  # noqa: E402
from src.scenario import ScenarioRunner  # noqa: E402
from src.transaction import Transaction, encode_transaction_list  # noqa: E402
from src.vote import Vote  # noqa: E402

CONFIG_DIR = REPO_ROOT / "config"


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class RunResult:
    """All observable outputs of one simulation run."""

    log_path: Path
    log_bytes: bytes
    log_sha256: str
    total_events: int

    # per-node final state
    state_hashes: dict[str, bytes] = field(default_factory=dict)
    finalized_heights: dict[str, int] = field(default_factory=dict)
    finalized_hashes: dict[str, bytes] = field(default_factory=dict)

    # fault statistics (for sanity — ensures non-trivial run)
    delayed: int = 0
    duplicated: int = 0
    reordered: int = 0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def _make_transaction(sender, *, chain_id: str, nonce: int = 0) -> Transaction:
    """Build a valid signed transaction for the given sender."""
    key = f"{hash_bytes(sender.public_key).hex()}/verify-determinism"
    unsigned = Transaction(
        chain_id=chain_id,
        nonce=nonce,
        sender_pubkey=sender.public_key,
        key=key,
        value_bytes=b"determinism-check",
        signature=b"",
    )
    sig = sign(sender.private_key, f"TX:{chain_id}", unsigned.unsigned_bytes())
    return Transaction(
        chain_id=chain_id,
        nonce=nonce,
        sender_pubkey=sender.public_key,
        key=key,
        value_bytes=b"determinism-check",
        signature=sig,
    )


def _schedule_with_faults(
    runner: ScenarioRunner,
    *,
    sender: str,
    receiver: str,
    payload: bytes,
    logical_time: int,
    height: int,
    round_: int,
    result: RunResult,
) -> None:
    """Apply fault injector decisions and send (possibly multiple) copies."""
    fault = runner.fault_injector.apply()
    if fault.dropped:
        return
    if fault.delay:
        result.delayed += 1
    copies = 1 + fault.duplicate_count
    if fault.duplicate_count:
        result.duplicated += fault.duplicate_count
    if fault.reorder:
        result.reordered += 1
    deliver_time = logical_time + fault.delay
    for _ in range(copies):
        runner.network.send(
            sender=sender,
            receiver=receiver,
            payload=payload,
            logical_time=deliver_time,
            height=height,
            round=round_,
        )


def _distribute_votes(
    runner: ScenarioRunner,
    *,
    votes: list[Vote],
    node_ids: list[str],
    states: dict[str, ConsensusState],
    vote_set_name: str,
    logical_time: int,
    height: int,
    round_: int,
    result: RunResult,
) -> None:
    """Gossip votes to all peers under fault injection, then drain network."""
    for recv_idx, receiver in enumerate(node_ids):
        plan: list[Vote] = []
        should_reorder = False

        for send_idx, sender in enumerate(node_ids):
            if send_idx == recv_idx:
                continue  # own vote already applied locally
            vote = votes[send_idx]

            fault = runner.fault_injector.apply()
            if fault.dropped:
                continue
            if fault.delay:
                result.delayed += 1
            copies = 1 + fault.duplicate_count
            if fault.duplicate_count:
                result.duplicated += fault.duplicate_count
            if fault.reorder:
                result.reordered += 1
                should_reorder = True
            deliver_time = logical_time + fault.delay

            for _ in range(copies):
                runner.network.send(
                    sender=sender,
                    receiver=receiver,
                    payload=vote.signed_bytes(),
                    logical_time=deliver_time,
                    height=height,
                    round=round_,
                )
            plan.extend([vote] * copies)

        if should_reorder and len(plan) > 1:
            plan = runner.scheduler.rng_shuffle_copy(plan)

        vs = getattr(states[receiver], vote_set_name)
        for v in plan:
            vs.add(v)

    runner.network.run()


# ---------------------------------------------------------------------------
# Core: run one full consensus simulation for max_height heights
# ---------------------------------------------------------------------------

def _run_once(scenario_config: dict, default_config: dict, run_id: str) -> RunResult:
    """
    Run a full consensus simulation and return all observable outputs.

    Every consensus and network event is written to the canonical log:
      - SCENARIO_START / NODE_INIT / SCENARIO_END  (lifecycle)
      - SEND / DELIVER                              (all network messages)
      - PROPOSE                                     (one per proposer)
      - PREVOTE                                     (one per validator)
      - LOCK                                        (one per validator when quorum reached)
      - PRECOMMIT                                   (one per validator)
      - FINALIZE                                    (one per validator)
    """
    chain_id: str = default_config["chain_id"]
    max_height: int = scenario_config.get("max_height", 1)
    validators = load_validator_keys()
    node_ids = [f"validator_{v.index}" for v in validators]
    validator_count = len(validators)

    exec_config = ExecutionConfig(
        chain_id=chain_id,
        max_key_size=default_config["network"]["max_key_size_bytes"],
        max_value_size=default_config["network"]["max_value_size_bytes"],
    )

    runner = ScenarioRunner(scenario_config, default_config)
    runner.load()

    # Write NODE_INIT events for each validator
    for idx, node_id in enumerate(node_ids):
        runner.event_log.write_event(
            event_no=runner._next_event_no(),
            logical_time=0,
            node_id=node_id,
            event_type=EventType.NODE_INIT,
            height=0,
            round=0,
            details={"node_id": node_id, "validator_index": idx},
        )

    states = {nid: ConsensusState(height=1) for nid in node_ids}
    ledgers = {nid: Ledger(chain_id=chain_id) for nid in node_ids}
    result = RunResult(
        log_path=Path(runner.event_log.log_path),
        log_bytes=b"",
        log_sha256="",
        total_events=0,
    )

    # Build one transaction per height (sender = validators[0])
    # Using sender index 0 — nonce increments each height.
    pending_txs_by_height: dict[int, list[Transaction]] = {}
    sender_v = validators[0]
    for h in range(1, max_height + 1):
        tx = _make_transaction(sender_v, chain_id=chain_id, nonce=h - 1)
        pending_txs_by_height[h] = [tx]

    logical_time = 1

    for height in range(1, max_height + 1):
        round_ = 0
        pending_txs = pending_txs_by_height[height]

        proposer = select_proposer(height, round_)
        proposer_nid = node_ids[proposer.index]
        peers = [nid for nid in node_ids if nid != proposer_nid]

        # -- Propose --
        proposal = propose(
            states[proposer_nid],
            network=runner.network,
            ledger=ledgers[proposer_nid],
            self_identity=proposer,
            validator_node_ids=node_ids,
            peers=peers,
            pending_transactions=pending_txs,
            chain_id=chain_id,
            exec_config=exec_config,
            logical_time=logical_time,
        )
        assert proposal.success, f"height={height} propose failed: {proposal.reason}"
        header = proposal.header
        block_hash = header.block_hash()

        # Log PROPOSE event (use max to stay monotonic after network SEND/DELIVER)
        _log_time = max(logical_time, runner.network.logical_time)
        runner.event_log.write_event(
            event_no=runner._next_event_no(),
            logical_time=_log_time,
            node_id=proposer_nid,
            event_type=EventType.PROPOSE,
            height=height,
            round=round_,
            details={
                "block_hash": block_hash.hex(),
                "proposer": proposer_nid,
                "tx_count": len(pending_txs),
            },
        )

        # Distribute header + body to peers under fault injection
        for receiver in peers:
            _schedule_with_faults(
                runner,
                sender=proposer_nid,
                receiver=receiver,
                payload=header.signed_bytes(),
                logical_time=logical_time,
                height=height,
                round_=round_,
                result=result,
            )
            _schedule_with_faults(
                runner,
                sender=proposer_nid,
                receiver=receiver,
                payload=encode_transaction_list(pending_txs),
                logical_time=logical_time,
                height=height,
                round_=round_,
                result=result,
            )
        runner.network.run()
        logical_time = runner.network.logical_time + 1

        # Store header + body at every node (header-first rule)
        for nid in node_ids:
            states[nid].block_store.store_header(header)
            states[nid].block_store.store_body(block_hash, pending_txs)

        # -- Prevote --
        prevotes = []
        for validator in validators:
            nid = node_ids[validator.index]
            vote = make_prevote(
                states[nid],
                chain_id=chain_id,
                self_identity=validator,
                proposed_block_hash=block_hash,
                validator_count=validator_count,
            )
            prevotes.append(vote)
            # Log PREVOTE event
            runner.event_log.write_event(
                event_no=runner._next_event_no(),
                logical_time=logical_time,
                node_id=nid,
                event_type=EventType.PREVOTE,
                height=height,
                round=round_,
                details={
                    "block_hash": (
                        vote.block_hash_or_nil.hex()
                        if vote.block_hash_or_nil is not None
                        else "nil"
                    ),
                    "validator": nid,
                },
            )

        _distribute_votes(
            runner,
            votes=prevotes,
            node_ids=node_ids,
            states=states,
            vote_set_name="prevotes",
            logical_time=logical_time,
            height=height,
            round_=round_,
            result=result,
        )
        logical_time = runner.network.logical_time + 1

        # -- Lock --
        for nid in node_ids:
            locked = apply_lock(states[nid], round=round_, validator_count=validator_count)
            if locked is not None:
                runner.event_log.write_event(
                    event_no=runner._next_event_no(),
                    logical_time=logical_time,
                    node_id=nid,
                    event_type=EventType.LOCK,
                    height=height,
                    round=round_,
                    details={
                        "block_hash": locked.hex(),
                        "locked_round": round_,
                        "validator": nid,
                    },
                )

        logical_time = runner.network.logical_time + 1

        # -- Precommit --
        precommits = []
        for validator in validators:
            nid = node_ids[validator.index]
            pc_result = make_precommit(
                states[nid],
                chain_id=chain_id,
                self_identity=validator,
                validator_count=validator_count,
                network=runner.network,
                validator_node_ids=node_ids,
                peers=[p for p in node_ids if p != nid],
                logical_time=logical_time,
            )
            precommits.append(pc_result.vote)
            # Log PRECOMMIT event
            runner.event_log.write_event(
                event_no=runner._next_event_no(),
                logical_time=logical_time,
                node_id=nid,
                event_type=EventType.PRECOMMIT,
                height=height,
                round=round_,
                details={
                    "block_hash": (
                        pc_result.block_hash_or_nil.hex()
                        if pc_result.block_hash_or_nil is not None
                        else "nil"
                    ),
                    "validator": nid,
                },
            )

        _distribute_votes(
            runner,
            votes=precommits,
            node_ids=node_ids,
            states=states,
            vote_set_name="precommits",
            logical_time=logical_time,
            height=height,
            round_=round_,
            result=result,
        )
        logical_time = runner.network.logical_time + 1

        # -- Finalize --
        for nid in node_ids:
            fin = try_finalize(
                states[nid],
                ledger=ledgers[nid],
                chain_id=chain_id,
                exec_config=exec_config,
                validator_count=validator_count,
            )
            assert fin.success, f"height={height} node={nid} finalize failed: {fin.reason}"
            state_hash_hex = fin.entry.state.state_hash().hex()
            runner.event_log.write_event(
                event_no=runner._next_event_no(),
                logical_time=logical_time,
                node_id=nid,
                event_type=EventType.FINALIZE,
                height=height,
                round=round_,
                details={
                    "block_hash": block_hash.hex(),
                    "state_hash": state_hash_hex,
                    "validator": nid,
                },
            )

        logical_time = runner.network.logical_time + 1

    # Register ledgers and assert safety/liveness
    for nid in node_ids:
        runner.register_ledger(nid, ledgers[nid])
    runner.check_assertions()
    assert runner.safety_result.ok, f"Safety violation: {runner.safety_result.violations}"
    assert runner.liveness_result.ok, (
        f"Liveness failure: max_height={runner.liveness_result.max_finalized_height}"
    )

    # Write SCENARIO_END
    runner.event_log.write_event(
        event_no=runner._next_event_no(),
        logical_time=logical_time,
        node_id="system",
        event_type=EventType.SCENARIO_END,
        height=0,
        round=0,
        details={
            "scenario_id": scenario_config.get("scenario_id", "unknown"),
            "total_events": runner.event_log.event_count + 1,
        },
    )
    runner.shutdown()

    # Collect final state
    for nid in node_ids:
        fh = ledgers[nid].finalized_height
        result.state_hashes[nid] = (
            ledgers[nid].get_state(fh).state_hash() if fh > 0 else b""
        )
        result.finalized_heights[nid] = fh
        result.finalized_hashes[nid] = ledgers[nid].finalized_hash or b""

    log_bytes = result.log_path.read_bytes()
    result.log_bytes = log_bytes
    result.log_sha256 = runner.event_log.get_sha256()
    result.total_events = runner.event_log.event_count
    return result


# ---------------------------------------------------------------------------
# Comparison and reporting
# ---------------------------------------------------------------------------

def _compare(run_a: RunResult, run_b: RunResult) -> list[str]:
    """Return a list of failure messages; empty = PASS."""
    failures: list[str] = []

    if run_a.log_bytes != run_b.log_bytes:
        failures.append("LOG BYTES DIFFER")
        # Find first differing line for diagnostics
        lines_a = run_a.log_bytes.decode("utf-8").splitlines()
        lines_b = run_b.log_bytes.decode("utf-8").splitlines()
        for i, (la, lb) in enumerate(zip(lines_a, lines_b), start=1):
            if la != lb:
                failures.append(f"  First diff at line {i}:")
                failures.append(f"    A: {la[:200]}")
                failures.append(f"    B: {lb[:200]}")
                break
        if len(lines_a) != len(lines_b):
            failures.append(
                f"  Line count: A={len(lines_a)}, B={len(lines_b)}"
            )

    if run_a.log_sha256 != run_b.log_sha256:
        failures.append(
            f"SHA-256 MISMATCH:\n  A: {run_a.log_sha256}\n  B: {run_b.log_sha256}"
        )

    if run_a.state_hashes != run_b.state_hashes:
        for nid in sorted(run_a.state_hashes):
            ha = run_a.state_hashes.get(nid, b"").hex()
            hb = run_b.state_hashes.get(nid, b"").hex()
            if ha != hb:
                failures.append(f"STATE HASH MISMATCH at {nid}: A={ha} B={hb}")

    if run_a.finalized_hashes != run_b.finalized_hashes:
        for nid in sorted(run_a.finalized_hashes):
            ha = run_a.finalized_hashes.get(nid, b"").hex()
            hb = run_b.finalized_hashes.get(nid, b"").hex()
            if ha != hb:
                failures.append(f"FINALIZED HASH MISMATCH at {nid}: A={ha} B={hb}")

    if run_a.finalized_heights != run_b.finalized_heights:
        failures.append(
            f"FINALIZED HEIGHT MISMATCH: A={run_a.finalized_heights} B={run_b.finalized_heights}"
        )

    return failures


def _print_summary(label: str, run: RunResult) -> None:
    print(f"\n{label}:")
    print(f"  Log path    : {run.log_path}")
    print(f"  Total events: {run.total_events}")
    print(f"  SHA-256     : {run.log_sha256}")

    # Show per-node finalized state
    for nid in sorted(run.finalized_heights):
        fh = run.finalized_heights[nid]
        fhash = run.finalized_hashes[nid].hex()[:16] + "..."
        shash = run.state_hashes[nid].hex()[:16] + "..." if run.state_hashes[nid] else "(empty)"
        print(f"  {nid}: height={fh}  block_hash={fhash}  state_hash={shash}")

    # Show event type breakdown from log
    event_counts: dict[str, int] = {}
    with run.log_path.open("r", encoding="utf-8") as fh_file:
        for line in fh_file:
            try:
                rec = json.loads(line.strip())
                et = rec.get("event_type", "?")
                event_counts[et] = event_counts.get(et, 0) + 1
            except json.JSONDecodeError:
                pass
    for et in sorted(event_counts):
        print(f"    {et:20s}: {event_counts[et]}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    # Parse optional --scenario argument
    scenario_name = "scenario_t8.json"
    for i, arg in enumerate(sys.argv[1:]):
        if arg == "--scenario" and i + 1 < len(sys.argv) - 1:
            scenario_name = sys.argv[i + 2]
            if not scenario_name.endswith(".json"):
                scenario_name += ".json"
            if not scenario_name.startswith("scenario_"):
                scenario_name = f"scenario_{scenario_name}"

    original_cwd = os.getcwd()
    os.chdir(REPO_ROOT)

    try:
        scenario_config = _load_json(CONFIG_DIR / scenario_name)
        default_config = _load_json(CONFIG_DIR / "default.json")
        scenario_id = scenario_config.get("scenario_id", "unknown")

        print(f"Scenario : {scenario_id}  ({scenario_name})")
        print(f"seed     : {scenario_config.get('seed')}")
        print(f"max_height: {scenario_config.get('max_height', 0)}")
        print(f"validators: {scenario_config.get('num_validators', 8)}")
        print()

        # Clean up previous runs so logs are fresh
        shutil.rmtree(f"logs/{scenario_id}", ignore_errors=True)

        # Use identical run_id on both executions — it is part of the
        # SCENARIO_START event and therefore part of the canonical log bytes.
        run_id = "verify_run"

        print("Running simulation A ...")
        run_a = _run_once(
            {**scenario_config, "run_id": run_id},
            default_config,
            run_id=run_id + "_a",
        )

        print("Running simulation B ...")
        run_b = _run_once(
            {**scenario_config, "run_id": run_id},
            default_config,
            run_id=run_id + "_b",
        )

        _print_summary("Run A", run_a)
        _print_summary("Run B", run_b)

        failures = _compare(run_a, run_b)

        print()
        if not failures:
            print(
                f"PASS — both runs produced byte-identical logs "
                f"(SHA-256: {run_a.log_sha256}) "
                f"and identical final state hashes."
            )
            # Fault sanity check
            if run_a.delayed == 0 and run_a.duplicated == 0 and run_a.reordered == 0:
                print(
                    "  (Note: no faults were injected — "
                    "consider using a scenario with faults for stronger evidence)"
                )
            else:
                print(
                    f"  Faults injected — delayed={run_a.delayed}, "
                    f"duplicated={run_a.duplicated}, reordered={run_a.reordered}"
                )
            sys.exit(0)
        else:
            print("FAIL — runs produced DIFFERENT outputs:")
            for msg in failures:
                print(f"  {msg}")
            sys.exit(1)

    finally:
        os.chdir(original_cwd)


if __name__ == "__main__":
    main()
