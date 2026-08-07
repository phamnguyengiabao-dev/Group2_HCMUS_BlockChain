"""Deterministic routing and validation for signed protocol messages.

The network envelope carries opaque bytes, while the protocol validators work
on typed :class:`BlockHeader` and :class:`Vote` objects.  ``MessageRouter`` is
the boundary between those two layers: callers provide the already decoded
object and the router proves that it is exactly the object represented by the
envelope payload before doing any protocol or identity checks.

Only validated messages are handed to the injected dispatch callback.  Every
failed guard returns one immutable ``RouteResult`` and writes one canonical
``REJECT`` event; the router never mutates protocol state itself.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import TypeAlias

from src.block import BlockHeader
from src.block_validator import validate_header
from src.event_log import EventLog, EventType
from src.network import Envelope
from src.vote import Vote


RoutableMessage: TypeAlias = BlockHeader | Vote


@dataclass(frozen=True, slots=True)
class RouterContext:
    """Expected protocol state used for one routing decision.

    ``validator_set`` is a sequence for headers because its order determines
    the expected proposer.  If a set is supplied, it is sorted by raw public
    key bytes so that callers cannot accidentally introduce hash-order
    nondeterminism.  A tuple is stored in the frozen context, making the
    context safe to share across repeated deterministic runs.
    """

    expected_chain_id: str
    expected_height: int
    expected_round: int
    expected_parent_hash: bytes | None = None
    expected_phase: str | None = None
    validator_set: tuple[bytes, ...] = ()

    def __post_init__(self) -> None:
        validators = self.validator_set
        if validators is None:
            validators = ()
        if isinstance(validators, (set, frozenset)):
            validators = tuple(sorted(validators))
        else:
            validators = tuple(validators)
        object.__setattr__(self, "validator_set", validators)


@dataclass(frozen=True, slots=True)
class RouteResult:
    """Immutable outcome of one routing attempt."""

    accepted: bool
    rejection_code: str | None = None
    rejection_detail: str | None = None


class MessageRouter:
    """Validate and dispatch signed headers and votes deterministically.

    Args:
        event_log: The canonical event log receiving ``REJECT`` records.
        sender_registry: Mapping from untrusted envelope sender IDs to the
            public key that identity is expected to use.
        dispatch: Callback invoked exactly once for an accepted message.
        context: Expected chain/height/round/parent/phase and validators.

    The constructor intentionally keeps the boundary explicit: one event log,
    one sender registry, one dispatch callback, and one immutable context.
    """

    def __init__(
        self,
        event_log: EventLog,
        sender_registry: Mapping[str, bytes],
        dispatch: Callable[[RoutableMessage], object],
        context: RouterContext,
    ) -> None:
        if not isinstance(event_log, EventLog):
            raise TypeError("event_log must be EventLog")

        if not isinstance(sender_registry, Mapping):
            raise TypeError("sender_registry must be a mapping")

        normalized_registry: dict[str, bytes] = {}
        for sender in sorted(sender_registry):
            public_key = sender_registry[sender]
            if not isinstance(sender, str):
                raise TypeError("sender_registry keys must be strings")
            if not isinstance(public_key, bytes):
                raise TypeError("sender_registry values must be bytes")
            normalized_registry[sender] = public_key

        if not callable(dispatch):
            raise TypeError("dispatch must be callable")

        if not isinstance(context, RouterContext):
            raise TypeError("context must be RouterContext")

        self._event_log = event_log
        self._sender_registry = normalized_registry
        self._dispatch = dispatch
        self._context = context

    @property
    def context(self) -> RouterContext:
        """Return the immutable expected-state context."""

        return self._context

    @property
    def sender_registry(self) -> Mapping[str, bytes]:
        """Return a read-only view of the trusted sender registry."""

        # A fresh mapping keeps the router's private copy immutable to callers
        # without relying on an implementation-specific proxy type.
        return dict(self._sender_registry)

    def route(
        self,
        envelope: Envelope,
        message: object,
    ) -> RouteResult:
        """Validate one typed message and dispatch it if every guard passes."""

        # Guard 1: ensure the untrusted envelope and decoded object have the
        # supported shape before touching any message fields.
        if not isinstance(envelope, Envelope):
            return self._reject(
                None,
                "INVALID_ENVELOPE",
                "envelope must be an Envelope",
            )
        if not isinstance(message, (BlockHeader, Vote)):
            return self._reject(
                envelope,
                "UNSUPPORTED_MESSAGE_TYPE",
                f"unsupported message type {type(message).__name__}",
            )

        # Guard 2: bind the decoded typed object to the exact network bytes.
        try:
            signed_bytes = message.signed_bytes()
        except (TypeError, ValueError, OverflowError) as exc:
            return self._reject(
                envelope,
                "INVALID_MESSAGE_SHAPE",
                str(exc),
            )
        if not isinstance(signed_bytes, bytes):
            return self._reject(
                envelope,
                "INVALID_MESSAGE_SHAPE",
                "signed_bytes() must return bytes",
            )
        if envelope.payload != signed_bytes:
            return self._reject(
                envelope,
                "PAYLOAD_MISMATCH",
                "envelope payload does not match message.signed_bytes()",
            )

        # Guard 3: chain identity is checked before sender metadata so an
        # off-chain object cannot use a trusted sender ID to influence logs or
        # callback state.
        if message.chain_id != self._context.expected_chain_id:
            return self._reject(
                envelope,
                "CHAIN_ID_MISMATCH",
                f"expected {self._context.expected_chain_id!r}, got {message.chain_id!r}",
            )

        # Guard 4: sender metadata must resolve in the trusted registry.
        expected_public_key = self._sender_registry.get(envelope.sender)
        if expected_public_key is None:
            return self._reject(
                envelope,
                "UNKNOWN_SENDER",
                f"sender {envelope.sender!r} is not registered",
            )

        # Guard 5: metadata never establishes identity; the object signer must
        # be exactly the key registered for the sender ID.
        signer = (
            message.proposer_pubkey
            if isinstance(message, BlockHeader)
            else message.validator_pubkey
        )
        if signer != expected_public_key:
            return self._reject(
                envelope,
                "SENDER_SIGNER_MISMATCH",
                "sender registry key does not match message signer",
            )

        # Guard 6: delegate protocol-specific guards to the existing,
        # canonical validators.  Their stable rejection codes are preserved.
        if isinstance(message, BlockHeader):
            try:
                validation = validate_header(
                    message,
                    expected_chain_id=self._context.expected_chain_id,
                    expected_height=self._context.expected_height,
                    expected_round=self._context.expected_round,
                    expected_parent_hash=self._context.expected_parent_hash,
                    validator_set=list(self._context.validator_set),
                )
            except (TypeError, ValueError, AttributeError) as exc:
                return self._reject(
                    envelope,
                    self._stable_exception_code(exc, "INVALID_HEADER"),
                    str(exc),
                )
            if not validation.success:
                rejection = validation.rejection
                if rejection is None:
                    return self._reject(
                        envelope,
                        "INVALID_HEADER",
                        "header validation failed",
                    )
                return self._reject(
                    envelope,
                    rejection.code,
                    rejection.detail,
                )
        else:
            try:
                message.validate(
                    expected_chain_id=self._context.expected_chain_id,
                    validator_set=self._context.validator_set,
                    expected_height=self._context.expected_height,
                    expected_round=self._context.expected_round,
                    expected_phase=self._context.expected_phase,
                )
            except (TypeError, ValueError, AttributeError) as exc:
                return self._reject(
                    envelope,
                    self._stable_exception_code(exc, "INVALID_VOTE"),
                    str(exc),
                )

        # All guards passed.  The callback is deliberately the final action so
        # rejected messages are never relayed and accepted messages are sent
        # exactly once.
        self._dispatch(message)
        return RouteResult(accepted=True)

    @staticmethod
    def _stable_exception_code(exc: Exception, fallback: str) -> str:
        text = str(exc)
        prefix = text.split(":", 1)[0].strip()
        if prefix and all(char.isupper() or char.isdigit() or char == "_" for char in prefix):
            return prefix
        return fallback

    def _reject(
        self,
        envelope: Envelope | None,
        code: str,
        detail: str,
    ) -> RouteResult:
        """Write exactly one canonical rejection event and return its result."""

        if envelope is None:
            logical_time = 0
            node_id = "router"
        else:
            logical_time = envelope.logical_time
            node_id = envelope.receiver

        self._event_log.write_event(
            event_no=self._event_log.event_count + 1,
            logical_time=logical_time,
            node_id=node_id,
            event_type=EventType.REJECT,
            height=self._context.expected_height,
            round=self._context.expected_round,
            details={"code": code},
        )
        return RouteResult(
            accepted=False,
            rejection_code=code,
            rejection_detail=detail,
        )


__all__ = [
    "MessageRouter",
    "RouteResult",
    "RouterContext",
]
