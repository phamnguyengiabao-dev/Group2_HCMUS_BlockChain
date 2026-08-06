"""
fault_injector.py — Deterministic network fault injection.

T3-07:
- DROP messages
- DELAY messages
- DUPLICATE messages
- REORDER messages
- Read fault settings from scenario configuration
- Use the seeded PRNG supplied by T3-06 Scheduler

The fault injector never creates its own random generator.
All random decisions go through Scheduler:
    - scheduler.rng_roll()
    - scheduler.rng_randint()
    - scheduler.rng_shuffle_copy()
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from src.scheduler import Scheduler


@dataclass(frozen=True, slots=True)
class FaultResult:
    """
    Result of applying deterministic network faults.

    Attributes:
        dropped:
            True if the message must be discarded.

        delay:
            Number of logical-time ticks added to the message.

        duplicate_count:
            Number of additional copies.

            0 means:
                original only

            1 means:
                original + 1 duplicate

        reorder:
            True if the message should be reordered.
    """

    dropped: bool = False
    delay: int = 0
    duplicate_count: int = 0
    reorder: bool = False

    @property
    def total_copies(self) -> int:
        """Return the total number of deliverable copies."""

        if self.dropped:
            return 0

        return 1 + self.duplicate_count


class FaultInjector:
    """
    Deterministic fault injector using the T3-06 Scheduler PRNG.

    Supported configuration:

    {
        "faults": {
            "drop_probability": 0.10,
            "delay_probability": 0.20,
            "max_delay": 5,
            "duplicate_probability": 0.05,
            "max_duplicates": 1,
            "reorder_probability": 0.10
        }
    }

    The configuration can also use:

        drop_rate
        delay_rate
        duplicate_rate
        reorder_rate

    instead of the corresponding *_probability names.
    """

    __slots__ = (
        "_scheduler",
        "_drop_probability",
        "_delay_probability",
        "_max_delay",
        "_duplicate_probability",
        "_max_duplicates",
        "_reorder_probability",
    )

    def __init__(
        self,
        scheduler: "Scheduler",
        scenario_config: dict[str, Any] | None = None,
    ) -> None:
        """
        Create a fault injector.

        Args:
            scheduler:
                T3-06 Scheduler containing the seeded PRNG.

            scenario_config:
                Scenario configuration containing fault settings.
        """

        if scheduler is None:
            raise TypeError(
                "scheduler must not be None"
            )

        # Check the T3-06 PRNG API.
        if not callable(
            getattr(
                scheduler,
                "rng_roll",
                None,
            )
        ):
            raise TypeError(
                "scheduler must provide rng_roll()"
            )

        if not callable(
            getattr(
                scheduler,
                "rng_randint",
                None,
            )
        ):
            raise TypeError(
                "scheduler must provide rng_randint()"
            )

        if scenario_config is None:
            scenario_config = {}

        if not isinstance(
            scenario_config,
            dict,
        ):
            raise TypeError(
                "scenario_config must be a dict"
            )

        faults = scenario_config.get(
            "faults",
            scenario_config,
        )

        if not isinstance(
            faults,
            dict,
        ):
            raise TypeError(
                "faults must be a dict"
            )

        self._scheduler = scheduler

        self._drop_probability = (
            self._read_probability(
                faults,
                "drop_probability",
                aliases=(
                    "drop_rate",
                ),
            )
        )

        self._delay_probability = (
            self._read_probability(
                faults,
                "delay_probability",
                aliases=(
                    "delay_rate",
                ),
            )
        )

        self._max_delay = (
            self._read_non_negative_int(
                faults,
                "max_delay",
                default=0,
            )
        )

        self._duplicate_probability = (
            self._read_probability(
                faults,
                "duplicate_probability",
                aliases=(
                    "duplicate_rate",
                ),
            )
        )

        self._max_duplicates = (
            self._read_non_negative_int(
                faults,
                "max_duplicates",
                default=1,
            )
        )

        self._reorder_probability = (
            self._read_probability(
                faults,
                "reorder_probability",
                aliases=(
                    "reorder_rate",
                ),
            )
        )

    @staticmethod
    def _read_value(
        config: dict[str, Any],
        name: str,
        aliases: tuple[str, ...],
        default: Any,
    ) -> Any:
        """Read a value by canonical name or alias."""

        if name in config:
            return config[name]

        for alias in aliases:
            if alias in config:
                return config[alias]

        return default

    @classmethod
    def _read_probability(
        cls,
        config: dict[str, Any],
        name: str,
        *,
        aliases: tuple[str, ...] = (),
    ) -> float:
        """Read and validate a probability in [0.0, 1.0]."""

        value = cls._read_value(
            config,
            name,
            aliases,
            0.0,
        )

        if (
            not isinstance(
                value,
                (int, float),
            )
            or isinstance(
                value,
                bool,
            )
        ):
            raise TypeError(
                f"{name} must be a number"
            )

        probability = float(value)

        if not (
            0.0
            <= probability
            <= 1.0
        ):
            raise ValueError(
                f"{name} must be "
                "between 0.0 and 1.0"
            )

        return probability

    @staticmethod
    def _read_non_negative_int(
        config: dict[str, Any],
        name: str,
        *,
        default: int,
    ) -> int:
        """Read and validate a non-negative integer."""

        value = config.get(
            name,
            default,
        )

        if (
            not isinstance(
                value,
                int,
            )
            or isinstance(
                value,
                bool,
            )
        ):
            raise TypeError(
                f"{name} must be an integer"
            )

        if value < 0:
            raise ValueError(
                f"{name} must be >= 0"
            )

        return value

    def apply(self) -> FaultResult:
        """
        Apply deterministic faults.

        Fixed decision order:

            1. DROP
            2. DELAY
            3. DUPLICATE
            4. REORDER

        This order must not change because changing it changes
        the PRNG consumption sequence and breaks deterministic replay.

        If DROP occurs, the remaining fault decisions are skipped.
        """

        # 1. DROP
        if self._scheduler.rng_roll(
            self._drop_probability
        ):
            return FaultResult(
                dropped=True
            )

        # 2. DELAY
        delay = 0

        if (
            self._max_delay > 0
            and self._scheduler.rng_roll(
                self._delay_probability
            )
        ):
            delay = (
                self._scheduler.rng_randint(
                    1,
                    self._max_delay,
                )
            )

        # 3. DUPLICATE
        duplicate_count = 0

        if (
            self._max_duplicates > 0
            and self._scheduler.rng_roll(
                self._duplicate_probability
            )
        ):
            duplicate_count = (
                self._scheduler.rng_randint(
                    1,
                    self._max_duplicates,
                )
            )

        # 4. REORDER
        reorder = (
            self._scheduler.rng_roll(
                self._reorder_probability
            )
        )

        return FaultResult(
            dropped=False,
            delay=delay,
            duplicate_count=(
                duplicate_count
            ),
            reorder=reorder,
        )

    def inject(self) -> FaultResult:
        """Alias for apply()."""

        return self.apply()

    def should_reorder(self) -> bool:
        """
        Make one deterministic reorder decision.

        Useful when Network applies reordering to a batch.
        """

        return self._scheduler.rng_roll(
            self._reorder_probability
        )