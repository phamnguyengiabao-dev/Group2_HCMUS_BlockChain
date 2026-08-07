"""
gossip.py — Gossip service for relaying finalized blocks and votes.

T4-10:
- After a block is finalized, relay the block header, body, and
  collected votes to all peers via the Network.
- Write SEND events via Network (which logs them canonically).
- All iteration over peers and votes uses sorted order for determinism.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from src.block import BlockHeader
from src.network import Network
from src.transaction import Transaction, encode_transaction_list
from src.vote import Vote
from src.vote_set import VoteSet


@dataclass(frozen=True)
class GossipResult:
    """Summary of one gossip broadcast after finalization."""

    height: int
    round: int
    peers_notified: int
    header_sends: int
    body_sends: int
    vote_sends: int


class GossipService:
    """
    Relay finalized block data and collected votes to peers.

    The service is stateless between calls: every `gossip_finalized` call
    gets a fresh set of peers, votes, and a block to broadcast — nothing
    is cached in the instance.

    All sends use the injected Network so bandwidth limits and event-log
    writes are handled consistently with the rest of the simulation.
    """

    def __init__(
        self,
        network: Network,
        self_node_id: str,
    ) -> None:
        if not isinstance(network, Network):
            raise TypeError("network must be Network")
        if not isinstance(self_node_id, str) or not self_node_id:
            raise ValueError("self_node_id must be a non-empty string")

        self._network = network
        self._self_node_id = self_node_id

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def gossip_finalized(
        self,
        *,
        header: BlockHeader,
        transactions: list[Transaction],
        vote_set: VoteSet,
        peers: Sequence[str],
        logical_time: int,
    ) -> GossipResult:
        """
        Broadcast a finalized block and its supporting votes to `peers`.

        Order of sends per peer:
            1. Block header (signed_bytes)
            2. Block body (encode_transaction_list)
            3. All non-NIL votes for (height, round, PRECOMMIT) in sorted
               validator_pubkey order

        Peers are processed in the order given (caller must sort them for
        determinism).

        Args:
            header:        The finalized block header.
            transactions:  The finalized block's transactions (may be empty).
            vote_set:      The VoteSet holding the precommit quorum.
            peers:         Node IDs to relay to, in caller-determined order.
            logical_time:  The logical time at which sends are scheduled.

        Returns:
            GossipResult summarising how many messages were sent.
        """
        from src.vote import PHASE_PRECOMMIT

        height = header.height
        round_ = header.round

        # Collect votes to relay: all accepted precommits for this
        # (height, round) in deterministic sorted order.
        precommit_votes: list[Vote] = sorted(
            (
                v
                for v in vote_set.votes(height, round_, PHASE_PRECOMMIT)
                if v.block_hash_or_nil is not None
            ),
            key=lambda v: v.validator_pubkey,
        )

        header_payload = header.signed_bytes()
        body_payload = encode_transaction_list(transactions)

        header_sends = 0
        body_sends = 0
        vote_sends = 0

        for peer in peers:
            if peer == self._self_node_id:
                continue  # do not send to self

            # 1. Header
            self._network.send(
                sender=self._self_node_id,
                receiver=peer,
                payload=header_payload,
                logical_time=logical_time,
                height=height,
                round=round_,
            )
            header_sends += 1

            # 2. Body
            self._network.send(
                sender=self._self_node_id,
                receiver=peer,
                payload=body_payload,
                logical_time=logical_time,
                height=height,
                round=round_,
            )
            body_sends += 1

            # 3. Votes (sorted by validator_pubkey for determinism)
            for vote in precommit_votes:
                self._network.send(
                    sender=self._self_node_id,
                    receiver=peer,
                    payload=vote.signed_bytes(),
                    logical_time=logical_time,
                    height=height,
                    round=round_,
                )
                vote_sends += 1

        if False:  # event_log integration handled by Network's SEND/DELIVER events
            pass
        return GossipResult(
            height=height,
            round=round_,
            peers_notified=len([p for p in peers if p != self._self_node_id]),
            header_sends=header_sends,
            body_sends=body_sends,
            vote_sends=vote_sends,
        )

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def node_id(self) -> str:
        return self._self_node_id

    @property
    def network(self) -> Network:
        return self._network


__all__ = [
    "GossipResult",
    "GossipService",
]
