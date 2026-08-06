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
"""

from __future__ import annotations

from typing import Any

from src.event_log import EventLog
from src.scheduler import Scheduler
from src.network import Network
from src.fault_injector import FaultInjector


class ScenarioRunner:
    """Top-level deterministic simulation runner."""

    def __init__(self, config: dict[str, Any]) -> None:
        if not isinstance(config, dict):
            raise TypeError("config must be dict")

        self.config = config

        self.event_log: EventLog | None = None
        self.scheduler: Scheduler | None = None
        self.network: Network | None = None
        self.fault_injector: FaultInjector | None = None

    def load(self) -> None:
        """Load configuration and initialize all shared components."""

        scenario_id = self.config.get("scenario_id", "default")
        run_id = self.config.get("run_id", "run")
        seed = self.config.get("seed", 0)

        self.event_log = EventLog(
            scenario_id=scenario_id,
            run_id=run_id,
        )

        self.scheduler = Scheduler(seed=seed)

        self.network = Network(
            event_log=self.event_log,
            scheduler=self.scheduler,
        )

        self.fault_injector = FaultInjector(
            scheduler=self.scheduler,
            scenario_config=self.config,
        )

        # Queue initial messages if present.
        for msg in self.config.get("messages", []):
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

    def shutdown(self) -> None:
        """Flush and close resources."""

        if self.event_log is not None:
            self.event_log.close()

    def execute(self) -> list[bytes]:
        """Convenience wrapper."""

        self.load()

        try:
            return self.run()
        finally:
            self.shutdown()

    def summary(self) -> dict[str, Any]:
        """Return deterministic run summary."""

        if self.event_log is None:
            raise RuntimeError("Scenario not executed")

        return {
            "event_count": self.event_log.event_count,
            "log_path": str(self.event_log.log_path),
            "log_sha256": self.event_log.get_sha256(),
            "logical_time": (
                self.scheduler.logical_time
                if self.scheduler is not None
                else 0
            ),
        }