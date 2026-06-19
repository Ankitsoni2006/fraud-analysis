"""
historical_intelligence/network_health_engine.py
================================================
Computes and monitors the overall platform Network Health Score.
"""

from __future__ import annotations

from historical_intelligence.historical_models import DailySnapshot, NetworkHealthReport


class NetworkHealthEngine:
    """
    Computes Network Health Score based on:
      - Anomaly volume (Type-A + Type-B counts)
      - Revenue exposure (revenue at risk)
      - Critical entities count (stores/packers/customers in critical risk tiers)
      - Refund abuse rate
    """

    def __init__(self) -> None:
        pass

    def compute_health(self, snapshot: DailySnapshot) -> float:
        """
        Calculates a score between 0.0 (critical threat) and 100.0 (perfectly clean).
        """
        # 1. Anomaly volume penalty (Type-A + Type-B counts)
        # Normal baseline: ~10 anomalies. Spike of 40+ should take significant penalty.
        anom_penalty = min(snapshot.total_anomalies * 0.4, 25.0)

        # 2. Revenue exposure penalty
        # Cap at ₹50,000 for full 25 points penalty.
        rev_penalty = min(snapshot.revenue_at_risk / 2000.0, 25.0)

        # 3. Critical entities count penalty
        # Packers threshold: >=10; Stores threshold: >=70; Customers: >=75.
        num_crit_stores = sum(1 for m in snapshot.store_metrics.values() if m.get("risk_score", 0.0) >= 70.0)
        num_crit_packers = sum(1 for m in snapshot.packer_metrics.values() if m.get("risk_score", 0.0) >= 10.0)
        num_crit_customers = sum(1 for m in snapshot.customer_metrics.values() if m.get("risk_score", 0.0) >= 75.0)
        total_crit = num_crit_stores + num_crit_packers + num_crit_customers
        crit_penalty = min(total_crit * 5.0, 25.0)

        # 4. Refund abuse rate penalty (proportion of refund claims blocked)
        # Represents external attack pressure.
        abuse_penalty = min(snapshot.refund_abuse_rate * 25.0, 25.0)

        # Calculate final health score (0 - 100)
        health = 100.0 - (anom_penalty + rev_penalty + crit_penalty + abuse_penalty)
        return max(0.0, min(100.0, round(health, 1)))

    def generate_report(self, snapshots: list[DailySnapshot], days_ago: int = 7) -> NetworkHealthReport:
        """
        Generates a NetworkHealthReport for the latest snapshot compared to N days ago.
        """
        if not snapshots:
            return NetworkHealthReport(
                today_score=100.0,
                previous_score=100.0,
                change=0.0,
                status="Stable",
                history=[]
            )

        sorted_snaps = sorted(snapshots, key=lambda x: x.day_idx)
        
        # Populate health score for each snapshot dynamically
        history: list[float] = []
        for snap in sorted_snaps:
            h = self.compute_health(snap)
            snap.network_health_score = h
            history.append(h)

        today_score = history[-1]
        
        # Compare with days_ago (default 7 days ago for weekly baseline)
        if len(history) > days_ago:
            prev_score = history[-1 - days_ago]
        else:
            prev_score = history[0]

        change = round(today_score - prev_score, 1)

        if change > 0.5:
            status = "Improving"
        elif change < -0.5:
            status = "Deteriorating"
        else:
            status = "Stable"

        return NetworkHealthReport(
            today_score=today_score,
            previous_score=prev_score,
            change=change,
            status=status,
            history=history
        )
