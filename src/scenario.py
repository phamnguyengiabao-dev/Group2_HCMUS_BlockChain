"""
scenario.py

T3-14

Scenario Runner

Responsibilities
----------------
1. Load scenario configuration.
2. Create EventLog.
3. Create deterministic Scheduler using scenario seed.
4. Create FaultInjector.
5. Create Network.
6. Queue initial messages (if any).
7. Run deterministic simulation.
8. Shutdown cleanly.

T3-16
Assert safety / liveness:
    Safety: no two distinct blocks at the same height may both be finalized by correct nodes. 
    Checked by comparing, for every height any registered node has finalized, whether 
    all nodes that reached that height agree on the same block_hash.

    Liveness: the chain must progress. Checked against config's `max_height`.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any

from src.event_log import EventLog, EventType
from src.scheduler import Scheduler
from src.network import Network
from src.fault_injector import FaultInjector
from src.ledger import Ledger


def _config_fingerprint(config: dict[str, Any]) -> str:
    """SHA-256 hex of the canonical sorted-key JSON encoding of `config`."""
    canonical = json.dumps(config, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class SafetyViolation:
    """
    Two or more registered nodes finalized DIFFERENT block_hash values
    at the same height — a direct violation of the safety invariant.
    """

    height: int
    # block_hash -> node_ids that finalized that hash at this height
    # (node_ids in sorted order within each list).
    conflicting_hashes: dict[bytes, list[str]]


@dataclass(frozen=True)
class SafetyResult:
    ok: bool
    violations: list[SafetyViolation] = field(default_factory=list)


@dataclass(frozen=True)
class LivenessResult:
    ok: bool
    min_expected_height: int
    max_finalized_height: int
    # node_id -> that node's finalized_height (sorted node_id order).
    finalized_heights: dict[str, int]


class ScenarioRunner:
    """Top-level deterministic simulation runner."""

    def __init__(
        self,
        scenario_config: dict[str, Any],
        default_config: dict[str, Any] | None = None,
    ) -> None:

        if not isinstance(scenario_config, dict):
            raise TypeError("scenario_config must be dict")
        
        if default_config is None:
            default_config = {}
        if not isinstance(default_config, dict):
            raise TypeError("default_config must be dict")

        self.scenario_config = scenario_config
        self.default_config = default_config

        self.event_log: EventLog | None = None
        self.scheduler: Scheduler | None = None
        self.network: Network | None = None
        self.fault_injector: FaultInjector | None = None

        # Populated by the consensus/node layer once it exists: one ledger per validator node_id. 
        # Empty until then — assert_safety / assert_liveness both tolerate an empty mapping.
        self.ledgers: dict[str, Ledger] = {}

        self.safety_result: SafetyResult | None = None
        self.liveness_result: LivenessResult | None = None

        self._event_no = 0

    def register_ledger(self, node_id: str, ledger: Ledger) -> None:
        """
        Register a node's Ledger so assertions can see it.
        """
        self.ledgers[node_id] = ledger

    def _next_event_no(self) -> int:
        self._event_no += 1
        return self._event_no

    def load(self) -> None:
        """Load configuration and initialize all shared components."""

        scenario_id = self.scenario_config.get("scenario_id", "default")
        run_id = self.scenario_config.get("run_id", "run")
        seed = self.scenario_config.get("seed", 0)
        spec_version = self.default_config.get("spec_version", "0.1")

        self.event_log = EventLog(
            scenario_id=scenario_id,
            run_id=run_id,
        )

        # Must be the very first event written (event_no starts at 1,
        # strictly monotonic — see event_log.py).
        self.event_log.write_event(
            event_no=self._next_event_no(),
            logical_time=0,
            node_id="system",
            event_type=EventType.SCENARIO_START,
            height=0,
            round=0,
            details={
                "config_fingerprint": _config_fingerprint(self.default_config),
                "run_id": run_id,
                "scenario_id": scenario_id,
                "seed": seed,
                "spec_version": spec_version,
            },
        )

        self.scheduler = Scheduler(seed=seed)

        # Share this runner's event_no sequence with Network, so every
        # writer to the same EventLog (this runner and Network both)
        # draws from one strictly-monotonic counter
        self.network = Network(
            event_log=self.event_log,
            scheduler=self.scheduler,
            event_no_counter=self._next_event_no,
        )

        self.fault_injector = FaultInjector(
            scheduler=self.scheduler,
            scenario_config=self.scenario_config,
        )

        # Queue initial messages if present.
        for msg in self.scenario_config.get("messages", []):
            self.network.send(
                sender=msg["sender"],
                receiver=msg["receiver"],
                payload=msg["payload"],
                logical_time=msg.get("logical_time", 0),
                height=msg.get("height", 0),
                round=msg.get("round", 0),
            )

    def run(self) -> list[bytes]:
        """Run until no scheduled envelopes remain."""

        if self.network is None:
            raise RuntimeError("Scenario not loaded")

        return self.network.run()

    # -- Assertions ----------------------------------------------------

    def _assert_safety(self) -> SafetyResult:
        height_to_hash_nodes: dict[int, dict[bytes, list[str]]] = {}

        for node_id in sorted(self.ledgers):
            ledger = self.ledgers[node_id]
            for height in ledger:  # Ledger.__iter__: ascending heights
                entry = ledger.get_entry(height)
                by_hash = height_to_hash_nodes.setdefault(height, {})
                by_hash.setdefault(entry.block_hash, []).append(node_id)

        violations: list[SafetyViolation] = []
        for height in sorted(height_to_hash_nodes):
            by_hash = height_to_hash_nodes[height]
            if len(by_hash) > 1:
                violations.append(
                    SafetyViolation(height=height, conflicting_hashes=dict(by_hash))
                )

        return SafetyResult(ok=not violations, violations=violations)

    def _assert_liveness(self) -> LivenessResult:
        finalized_heights = {
            node_id: self.ledgers[node_id].finalized_height
            for node_id in sorted(self.ledgers)
        }
        max_height_reached = max(finalized_heights.values(), default=0)

        target = self.scenario_config.get("max_height", 0)
        if target <= 0:
            # No-op scenario: no progress was ever expected.
            return LivenessResult(
                ok=True,
                min_expected_height=0,
                max_finalized_height=max_height_reached,
                finalized_heights=finalized_heights,
            )

        return LivenessResult(
            ok=max_height_reached >= target,
            min_expected_height=target,
            max_finalized_height=max_height_reached,
            finalized_heights=finalized_heights,
        )

    def check_assertions(self) -> None:
        """
        Run safety + liveness checks against whatever has been
        registered in `self.ledgers`.

        Results are stored on the runner (not raised as exceptions),
        """
        self.safety_result = self._assert_safety()
        self.liveness_result = self._assert_liveness()

    def shutdown(self) -> None:
        """Write SCENARIO_END, flush and close resources."""

        if self.event_log is not None and not self.event_log._closed:
            self.event_log.write_event(
                event_no=self._next_event_no(),
                logical_time=(
                    self.scheduler.logical_time if self.scheduler is not None else 0
                ),
                node_id="system",
                event_type=EventType.SCENARIO_END,
                height=0,
                round=0,
                details={
                    "scenario_id": self.scenario_config.get("scenario_id", ""),
                    "total_events": self._event_no,
                },
            )
            self.event_log.close()

    def execute(self) -> list[bytes]:
        """Convenience wrapper: load, run, check assertions, shutdown."""

        self.load()

        try:
            result = self.run()
            self.check_assertions()
            return result
        finally:
            self.shutdown()

    def summary(self) -> dict[str, Any]:
        """Return deterministic run summary, including assertion results."""

        if self.event_log is None:
            raise RuntimeError("Scenario not executed")

        return {
            "event_count": self.event_log.event_count,
            "log_path": str(self.event_log.log_path),
            "log_sha256": self.event_log.get_sha256(),
            "logical_time": (
                self.scheduler.logical_time if self.scheduler is not None else 0
            ),
            "safety_ok": (
                self.safety_result.ok if self.safety_result is not None else None
            ),
            "safety_violations": (
                len(self.safety_result.violations)
                if self.safety_result is not None
                else None
            ),
            "liveness_ok": (
                self.liveness_result.ok if self.liveness_result is not None else None
            ),
            "liveness_max_finalized_height": (
                self.liveness_result.max_finalized_height
                if self.liveness_result is not None
                else None
            ),
        }


# ================================================================
# T4-11  Crash simulation
# T4-12  Restart simulation
# ================================================================

@dataclass
class NodeCrashState:
    """
    Tracks whether a node has crashed and what snapshot it had at crash time.

    Fields:
        node_id          Node identifier.
        crashed_at       Logical time the crash was triggered.
        restarted_at     Logical time of restart (None if not yet restarted).
        snapshot_path    Path to the persisted ledger snapshot used for recovery.
    """

    node_id: str
    crashed_at: int
    restarted_at: int | None = None
    snapshot_path: str | None = None


def simulate_crash(
    *,
    node_id: str,
    logical_time: int,
    event_log: EventLog,
    event_no: int,
    in_memory_caches: dict[str, Any] | None = None,
    snapshot_path: str | None = None,
) -> NodeCrashState:
    """
    T4-11: Simulate a node crash.

    Actions performed:
        1. Clear the node's in-memory cache (if supplied).
        2. Write a canonical CRASH event to the event log.
        3. Return a NodeCrashState capturing the crash metadata.

    The persisted ledger snapshot (if any) is intentionally preserved —
    crash recovery (T4-12) loads from it.

    Args:
        node_id:          The node that crashes.
        logical_time:     Logical time of the crash.
        event_log:        Canonical event log.
        event_no:         Monotonic event number to use for the CRASH event.
        in_memory_caches: Optional dict whose value for `node_id` is cleared.
                          Represents any in-memory state (pending blocks,
                          pending votes, consensus state, etc.).
        snapshot_path:    Path to the node's persisted ledger snapshot file,
                          kept intact so restart can load it.

    Returns:
        NodeCrashState describing the crash.
    """
    # 1. Clear in-memory state
    if in_memory_caches is not None and node_id in in_memory_caches:
        cache = in_memory_caches[node_id]
        if hasattr(cache, "clear") and callable(cache.clear):
            cache.clear()
        else:
            in_memory_caches[node_id] = None

    # 2. Log CRASH event
    event_log.write_event(
        event_no=event_no,
        logical_time=logical_time,
        node_id=node_id,
        event_type=EventType.CRASH,
        height=0,
        round=0,
        details={
            "node_id": node_id,
            "snapshot_preserved": snapshot_path is not None,
        },
    )

    return NodeCrashState(
        node_id=node_id,
        crashed_at=logical_time,
        snapshot_path=snapshot_path,
    )


def simulate_restart(
    *,
    crash_state: NodeCrashState,
    logical_time: int,
    event_log: EventLog,
    event_no: int,
    chain_id: str,
) -> "tuple[NodeCrashState, Ledger]":
    """
    T4-12: Simulate a node restart after a crash.

    Actions performed:
        1. Load the finalized ledger snapshot from disk (F-53).
           Unfinalized proposals and votes are discarded — they are not
           in the snapshot and are not reconstructed here.
        2. Write a canonical RESTART event to the event log.
        3. Return an updated NodeCrashState and the recovered Ledger.

    The caller is responsible for rebuilding consensus state by re-processing
    messages received from peers after the restart (network gossip).

    Args:
        crash_state:   The NodeCrashState returned by simulate_crash().
        logical_time:  Logical time of the restart.
        event_log:     Canonical event log.
        event_no:      Monotonic event number to use for the RESTART event.
        chain_id:      Chain identifier for the recovered Ledger.

    Returns:
        (updated_crash_state, recovered_ledger)

    Raises:
        ValueError: If the snapshot is corrupt (propagated from Ledger.load_snapshot).
    """
    from src.ledger import Ledger

    snapshot_path = crash_state.snapshot_path

    # 1. Load from snapshot (or start empty if no snapshot exists yet)
    if snapshot_path is not None:
        recovered_ledger = Ledger.load_snapshot(
            chain_id=chain_id,
            storage_path=snapshot_path,
        )
    else:
        recovered_ledger = Ledger(chain_id=chain_id)

    finalized_height = recovered_ledger.finalized_height

    # 2. Log RESTART event
    event_log.write_event(
        event_no=event_no,
        logical_time=logical_time,
        node_id=crash_state.node_id,
        event_type=EventType.RESTART,
        height=finalized_height,
        round=0,
        details={
            "node_id": crash_state.node_id,
            "recovered_height": finalized_height,
            "snapshot_path": str(snapshot_path) if snapshot_path else None,
        },
    )

    updated_state = NodeCrashState(
        node_id=crash_state.node_id,
        crashed_at=crash_state.crashed_at,
        restarted_at=logical_time,
        snapshot_path=snapshot_path,
    )

    return updated_state, recovered_ledger
