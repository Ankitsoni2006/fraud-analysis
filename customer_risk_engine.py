"""
ivc/customer_risk_engine.py
============================
Phase 1 — Customer Risk Engine.

Identifies potentially abusive customers based on historical refund behaviour.
Produces a CustomerRiskProfile for every customer seen in the audit results.
No print statements; structured logging only.
"""

from __future__ import annotations

from collections import defaultdict

from config import DETECTION_CONFIG
from logging_config import get_logger
from models import AuditResult, CustomerRiskProfile, RefundClaim, RefundVerdict, RiskLevel

log = get_logger(__name__)


class CustomerRiskEngine:
    """
    Builds risk profiles for every customer who appears in refund data.

    Scoring weights (all configurable):
      - refund_frequency:   How many claims has this customer made?
      - refund_rate:        Proportion of orders that resulted in refunds.
      - high_value_refunds: How many claims were on high-value items?
      - cumulative_value:   Total INR claimed across all refunds.

    Each component is normalised to 0–100, then combined with weights.
    Final score ≥ 75 → CRITICAL, ≥ 50 → HIGH, ≥ 25 → MEDIUM, else LOW.
    """

    def __init__(
        self,
        refund_claims:  list[RefundClaim],
        audit_results:  list[AuditResult],
        high_value_inr: float | None = None,
        freq_weight:    float = 0.30,
        rate_weight:    float = 0.25,
        hv_weight:      float = 0.25,
        value_weight:   float = 0.20,
    ) -> None:
        self._claims       = refund_claims
        self._audit        = audit_results
        self._hv_threshold = high_value_inr or DETECTION_CONFIG.high_value_threshold_inr
        self._weights      = dict(
            freq_weight=freq_weight,
            rate_weight=rate_weight,
            hv_weight=hv_weight,
            value_weight=value_weight,
        )
        self._profiles: dict[str, CustomerRiskProfile] = {}

    def compute(self) -> dict[str, CustomerRiskProfile]:
        """
        Returns dict[customer_id → CustomerRiskProfile].
        Only customers with ≥ 1 refund claim are profiled.
        """
        if not self._claims:
            log.info("No refund claims — customer risk profiles empty.")
            return {}

        # Build order counts per customer from claims
        # (In production this would come from an orders DB; here we infer)
        orders_per_customer: dict[str, set[str]] = defaultdict(set)
        for claim in self._claims:
            orders_per_customer[claim.customer_id].add(claim.order_id)

        # Aggregate claim stats per customer
        claim_stats: dict[str, dict] = defaultdict(lambda: {
            "refund_count": 0,
            "hv_count": 0,
            "total_value": 0.0,
            "order_ids": set(),
        })

        for claim in self._claims:
            s = claim_stats[claim.customer_id]
            s["refund_count"] += 1
            s["total_value"]  += claim.claimed_value_inr
            s["order_ids"].add(claim.order_id)
            if claim.claimed_value_inr >= self._hv_threshold:
                s["hv_count"] += 1

        # Build profiles
        profiles: dict[str, CustomerRiskProfile] = {}
        for cust_id, stats in claim_stats.items():
            total_orders = len(stats["order_ids"])
            refund_count = stats["refund_count"]
            total_value  = stats["total_value"]
            hv_count     = stats["hv_count"]

            profile = CustomerRiskProfile(
                customer_id             = cust_id,
                refund_count            = refund_count,
                high_value_refund_count = hv_count,
                total_orders            = total_orders,
                refund_rate             = refund_count / max(total_orders, 1),
                total_claim_value       = total_value,
                average_claim_value     = total_value / max(refund_count, 1),
            )
            profile.recompute(**self._weights)
            profiles[cust_id] = profile

        self._profiles = profiles

        critical_count = sum(1 for p in profiles.values() if p.risk_level == RiskLevel.CRITICAL)
        high_count     = sum(1 for p in profiles.values() if p.risk_level == RiskLevel.HIGH)
        log.info(
            "Customer risk engine complete",
            customers_profiled=len(profiles),
            critical=critical_count,
            high=high_count,
        )
        return profiles

    @property
    def profiles(self) -> dict[str, CustomerRiskProfile]:
        return self._profiles

    def top_risky_customers(self, n: int = 10) -> list[CustomerRiskProfile]:
        """Returns top-N customers sorted by risk_score descending."""
        return sorted(self._profiles.values(), key=lambda p: -p.risk_score)[:n]