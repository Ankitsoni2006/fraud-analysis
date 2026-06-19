"""
ivc/analytics_engine.py
=======================
Phase 3 — Operational Analytics Engine.

Computes structured analytics from pipeline outputs.
Returns typed OperationalAnalytics — no print statements.
"""

from __future__ import annotations

from collections import Counter, defaultdict

import pandas as pd

from config import DETECTION_CONFIG
from logging_config import get_logger
from models import (
    AuditResult,
    HesitationViolation,
    OperationalAnalytics,
    PackerRiskProfile,
    Product,
    RefundClaim,
    RefundVerdict,
    ScanEvent,
    SpeedViolation,
)

log = get_logger(__name__)


class OperationalAnalyticsEngine:
    """
    Derives operational and risk analytics from all pipeline outputs.

    All computation is pure (no side effects except logging).
    Returns a single OperationalAnalytics dataclass instance.
    """

    def __init__(
        self,
        scan_events:           list[ScanEvent],
        validated_df:          pd.DataFrame,
        speed_violations:      list[SpeedViolation],
        hesitation_violations: list[HesitationViolation],
        refund_claims:         list[RefundClaim],
        audit_results:         list[AuditResult],
        packer_profiles:       dict[str, PackerRiskProfile],
        product_catalogue:     dict[str, Product],
    ) -> None:
        self._events     = scan_events
        self._df         = validated_df
        self._speed      = speed_violations
        self._hesit      = hesitation_violations
        self._claims     = refund_claims
        self._audit      = audit_results
        self._packers    = packer_profiles
        self._products   = product_catalogue

    def compute(self) -> OperationalAnalytics:
        """Compute and return a fully-populated OperationalAnalytics object."""
        analytics = OperationalAnalytics()

        total_orders = self._df["order_id"].nunique() if not self._df.empty else 0
        total_scans  = len(self._df)
        analytics.total_orders = total_orders
        analytics.total_scans  = total_scans

        # Revenue
        analytics.total_revenue_processed = self._compute_revenue()
        analytics.average_order_value     = (
            analytics.total_revenue_processed / max(total_orders, 1)
        )

        # Revenue leakage estimate = value of approved refunds where injected_fraud=True
        analytics.revenue_leakage_estimate = sum(
            r.claimed_value_inr for r in self._audit
            if r.verdict == RefundVerdict.APPROVE and r.was_injected_fraud
        )

        # Pack time
        analytics.average_pack_time_s = self._average_pack_time()

        # Anomaly rates
        total_anomalies = len(self._speed) + len(self._hesit)
        analytics.anomaly_rate_overall = total_anomalies / max(total_scans, 1)

        # Refund abuse rate: rejected refunds / total claims
        blocked = sum(1 for r in self._audit if r.verdict == RefundVerdict.REJECT)
        analytics.refund_abuse_rate = blocked / max(len(self._audit), 1)

        # High-value anomaly rate
        hv_anomalies = sum(
            1 for v in self._hesit
            if v.value_inr >= DETECTION_CONFIG.high_value_threshold_inr
        )
        hv_scans = sum(
            1 for e in self._events
            if self._products.get(e.item_id, None) is not None
            and self._products[e.item_id].is_high_value
        )
        analytics.high_value_anomaly_rate = hv_anomalies / max(hv_scans, 1)

        # Per-store anomaly rates
        analytics.anomaly_rate_by_store  = self._anomaly_rate_by_store()
        analytics.anomaly_rate_by_packer = self._anomaly_rate_by_packer()

        # Risky SKUs and categories
        analytics.top_risky_skus       = self._top_risky_skus(n=10)
        analytics.top_risky_categories = self._top_risky_categories(n=10)
        analytics.revenue_by_category  = self._revenue_by_category()

        log.info(
            "Operational analytics computed",
            total_orders=total_orders,
            anomaly_rate=round(analytics.anomaly_rate_overall, 4),
            refund_abuse_rate=round(analytics.refund_abuse_rate, 4),
            revenue_leakage=round(analytics.revenue_leakage_estimate, 2),
        )
        return analytics

    # ── Private helpers ───────────────────────────────────────────────────────

    def _compute_revenue(self) -> float:
        total = 0.0
        for event in self._events:
            p = self._products.get(event.item_id)
            if p:
                total += p.value_inr
        return round(total, 2)

    def _average_pack_time(self) -> float:
        """Average seconds from first to last scan per order."""
        if self._df.empty:
            return 0.0
        times = (
            self._df.groupby("order_id")["timestamp"]
            .agg(lambda x: (x.max() - x.min()).total_seconds())
        )
        return round(float(times.mean()), 2)

    def _anomaly_rate_by_store(self) -> dict[str, float]:
        order_store: dict[str, str] = {}
        store_orders: dict[str, set[str]] = defaultdict(set)
        for e in self._events:
            order_store[e.order_id] = e.store_id
            store_orders[e.store_id].add(e.order_id)

        anomaly_counts: dict[str, int] = defaultdict(int)
        for v in self._speed:
            sid = order_store.get(v.order_id)
            if sid:
                anomaly_counts[sid] += 1
        for v in self._hesit:
            sid = order_store.get(v.order_id)
            if sid:
                anomaly_counts[sid] += 1

        result: dict[str, float] = {}
        for sid, orders in store_orders.items():
            result[sid] = round(anomaly_counts[sid] / max(len(orders), 1), 4)
        return result

    def _anomaly_rate_by_packer(self) -> dict[str, float]:
        packer_orders: dict[str, set[str]] = defaultdict(set)
        for e in self._events:
            packer_orders[e.packer_id].add(e.order_id)

        anomaly_counts: dict[str, int] = defaultdict(int)
        for v in self._speed:
            anomaly_counts[v.packer_id] += 1
        for v in self._hesit:
            anomaly_counts[v.packer_id] += 1

        result: dict[str, float] = {}
        for pid, orders in packer_orders.items():
            result[pid] = round(anomaly_counts[pid] / max(len(orders), 1), 4)
        return result

    def _top_risky_skus(self, n: int = 10) -> list[tuple[str, int]]:
        counter: Counter = Counter()
        for v in self._speed:
            counter[v.item_id] += 1
        for v in self._hesit:
            counter[v.item_id] += 1
        return counter.most_common(n)

    def _top_risky_categories(self, n: int = 10) -> list[tuple[str, int]]:
        counter: Counter = Counter()
        for v in self._hesit:
            counter[v.category] += 1
        for v in self._speed:
            p = self._products.get(v.item_id)
            if p:
                counter[p.category] += 1
        return counter.most_common(n)

    def _revenue_by_category(self) -> dict[str, float]:
        totals: dict[str, float] = defaultdict(float)
        for event in self._events:
            p = self._products.get(event.item_id)
            if p:
                totals[p.category] += p.value_inr
        return {k: round(v, 2) for k, v in sorted(totals.items(), key=lambda x: -x[1])}