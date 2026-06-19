"""
scenarios/scenario_simulator.py
===============================
Projects risk scores and platform-wide metrics under hypothetical operational drifts.
"""

from __future__ import annotations

import copy
from datetime import datetime
from typing import Dict, Any, Tuple, List
from models import StoreRiskProfile, PackerRiskProfile, CustomerRiskProfile, RiskLevel
from historical_intelligence.network_health_engine import NetworkHealthEngine
from historical_intelligence.historical_models import DailySnapshot


class ScenarioSimulator:
    """
    Simulates operational drifts and models outcomes:
      1. REFUND_SURGE: Simulates external abuse. Refund claim volumes and values increase.
      2. STORE_CONGESTION: Simulates congestion at a specific store, causing higher packing delay anomalies.
      3. STAFF_FATIGUE: Simulates packer errors/fatigue, increasing anomaly counts across all packers.
    """

    @staticmethod
    def run_what_if(
        store_profiles: Dict[str, StoreRiskProfile],
        packer_profiles: Dict[str, PackerRiskProfile],
        customer_profiles: Dict[str, CustomerRiskProfile],
        scenario_type: str,
        parameter: Any  # e.g., drift percentage (20.0 for 20%) or specific store ID
    ) -> Tuple[Dict[str, StoreRiskProfile], Dict[str, PackerRiskProfile], Dict[str, CustomerRiskProfile], float]:
        """
        Runs the projection and returns a tuple of:
        (projected_stores, projected_packers, projected_customers, projected_network_health)
        """
        # Deep copy to avoid mutating active cache
        stores = copy.deepcopy(store_profiles)
        packers = copy.deepcopy(packer_profiles)
        customers = copy.deepcopy(customer_profiles)

        if scenario_type == "REFUND_SURGE":
            multiplier = 1.0 + (float(parameter) / 100.0)
            
            # Elevate customer claim statistics
            for c in customers.values():
                c.refund_count = int(c.refund_count * multiplier)
                c.high_value_refund_count = int(c.high_value_refund_count * multiplier)
                c.total_claim_value = c.total_claim_value * multiplier
                c.average_claim_value = c.total_claim_value / max(c.refund_count, 1)
                c.recompute()

            # Elevate store risk profiles
            for s in stores.values():
                s.refund_claims = int(s.refund_claims * multiplier)
                s.revenue_at_risk = s.revenue_at_risk * multiplier
                s.recompute()

        elif scenario_type == "STORE_CONGESTION":
            # Target store experiences packing congestion: +80% A/B anomalies, and -20% completed orders
            target_store_id = str(parameter)
            if target_store_id in stores:
                s = stores[target_store_id]
                s.type_a_events = int(s.type_a_events * 1.8)
                s.type_b_events = int(s.type_b_events * 1.8)
                s.orders_processed = max(1, int(s.orders_processed * 0.8))
                s.recompute()

        elif scenario_type == "STAFF_FATIGUE":
            multiplier = 1.0 + (float(parameter) / 100.0)
            
            # Packers have higher fatigue, boosting anomaly counts
            for p in packers.values():
                p.type_a_count = int(p.type_a_count * multiplier)
                p.type_b_count = int(p.type_b_count * multiplier)
                # recompute method matches core config
                p.recompute(
                    type_a_weight=3,
                    type_b_weight=2,
                    critical_threshold=10,
                    high_threshold=5
                )

            # Store profiles register these added packer anomalies
            for s in stores.values():
                s.type_a_events = int(s.type_a_events * multiplier)
                s.type_b_events = int(s.type_b_events * multiplier)
                s.recompute()

        # Compute projected overall Network Health
        # Build mock DailySnapshot to feed into NetworkHealthEngine
        total_anoms = sum(s.type_a_events + s.type_b_events for s in stores.values())
        total_claims = sum(s.refund_claims for s in stores.values())
        total_rev_at_risk = sum(s.revenue_at_risk for s in stores.values())
        
        # Approximate refund abuse rate based on claims blocked vs total claims
        blocked_claims = sum(1 for c in customers.values() if c.risk_level in (RiskLevel.HIGH, RiskLevel.CRITICAL))
        abuse_rate = blocked_claims / max(total_claims, 1)

        # Convert to dictionary representation for metrics
        store_metrics = {
            k: {"risk_score": p.store_risk_score} for k, p in stores.items()
        }
        packer_metrics = {
            k: {"risk_score": float(p.total_score)} for k, p in packers.items()
        }
        customer_metrics = {
            k: {"risk_score": p.risk_score} for k, p in customers.items()
        }

        snap = DailySnapshot(
            day_idx=90,
            date=datetime.utcnow(),
            total_orders=sum(s.orders_processed for s in stores.values()),
            total_anomalies=total_anoms,
            total_refund_claims=total_claims,
            revenue_at_risk=total_rev_at_risk,
            refund_abuse_rate=abuse_rate,
            store_metrics=store_metrics,
            packer_metrics=packer_metrics,
            customer_metrics=customer_metrics
        )

        nhe = NetworkHealthEngine()
        projected_health = nhe.compute_health(snap)

        return stores, packers, customers, projected_health
