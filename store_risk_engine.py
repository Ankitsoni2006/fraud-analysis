"""
ivc/store_risk_engine.py
========================
Phase 2 — Dark Store Risk Engine.

Profiles each of the 10 dark stores based on their operational risk signals.
Produces a StoreRiskProfile per store and a ranked store leaderboard.
"""

from __future__ import annotations

from collections import defaultdict

from logging_config import get_logger
from models import (
    AuditResult,
    HesitationViolation,
    RefundClaim,
    ScanEvent,
    SpeedViolation,
    StoreRiskProfile,
    RiskLevel,
)

log = get_logger(__name__)


class DarkStoreRiskEngine:
    """
    Aggregates all fraud signals by store_id and computes per-store risk scores.

    Fields tracked:
      - orders_processed: distinct order count for the store.
      - refund_claims:    number of refund claims tied to orders from the store.
      - type_a_events:    speed violations on orders from the store.
      - type_b_events:    hesitation violations on orders from the store.
      - revenue_at_risk:  total refund claim value attributed to the store.
      - store_risk_score: weighted composite score (0–100).
    """

    def __init__(
        self,
        scan_events:           list[ScanEvent],
        speed_violations:      list[SpeedViolation],
        hesitation_violations: list[HesitationViolation],
        refund_claims:         list[RefundClaim],
    ) -> None:
        self._events    = scan_events
        self._speed     = speed_violations
        self._hesit     = hesitation_violations
        self._claims    = refund_claims
        self._profiles: dict[str, StoreRiskProfile] = {}

    def compute(self) -> dict[str, StoreRiskProfile]:
        """Returns dict[store_id → StoreRiskProfile]."""

        # Build order → store_id map
        order_store: dict[str, str] = {}
        for event in self._events:
            order_store.setdefault(event.order_id, event.store_id)

        # Gather all store IDs (including stores with zero incidents)
        all_stores: set[str] = {e.store_id for e in self._events}

        # Initialise profiles for every store
        profiles: dict[str, StoreRiskProfile] = {
            sid: StoreRiskProfile(store_id=sid) for sid in all_stores
        }

        # Orders per store
        orders_by_store: dict[str, set[str]] = defaultdict(set)
        for event in self._events:
            orders_by_store[event.store_id].add(event.order_id)
        for sid, orders in orders_by_store.items():
            profiles[sid].orders_processed = len(orders)

        # Type-A violations (look up order → store)
        for v in self._speed:
            sid = order_store.get(v.order_id)
            if sid and sid in profiles:
                profiles[sid].type_a_events += 1

        # Type-B violations
        for v in self._hesit:
            sid = order_store.get(v.order_id)
            if sid and sid in profiles:
                profiles[sid].type_b_events += 1

        # Refund claims
        for claim in self._claims:
            sid = order_store.get(claim.order_id)
            if sid and sid in profiles:
                profiles[sid].refund_claims     += 1
                profiles[sid].revenue_at_risk   += claim.claimed_value_inr

        # Recompute risk scores
        for profile in profiles.values():
            profile.recompute()

        self._profiles = profiles

        critical_count = sum(1 for p in profiles.values() if p.risk_level == RiskLevel.CRITICAL)
        high_count     = sum(1 for p in profiles.values() if p.risk_level == RiskLevel.HIGH)
        log.info(
            "Dark store risk engine complete",
            stores_profiled=len(profiles),
            critical=critical_count,
            high=high_count,
        )
        return profiles

    @property
    def profiles(self) -> dict[str, StoreRiskProfile]:
        return self._profiles

    def ranked_stores(self) -> list[StoreRiskProfile]:
        """Returns all stores sorted by store_risk_score descending (highest risk first)."""
        return sorted(self._profiles.values(), key=lambda p: -p.store_risk_score)

    def safest_stores(self, n: int = 3) -> list[StoreRiskProfile]:
        """Returns the N stores with the lowest risk scores."""
        return sorted(self._profiles.values(), key=lambda p: p.store_risk_score)[:n]

    def highest_risk_stores(self, n: int = 3) -> list[StoreRiskProfile]:
        """Returns the N stores with the highest risk scores."""
        return self.ranked_stores()[:n]