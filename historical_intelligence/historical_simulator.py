"""
historical_intelligence/historical_simulator.py
===============================================
Generates 90 days of simulated operational risk history with realistic drifts.
"""

from __future__ import annotations

import random
import math
import pandas as pd
from datetime import datetime, timedelta
from typing import Optional, Any

from config import DETECTION_CONFIG, PRODUCTS, PACKER_IDS
from models import PipelineResult, RiskLevel, RefundVerdict
from simulator import DarkStoreSimulator, STORE_IDS
from orchestrator import IVCOrchestrator
from detectors import scan_events_to_dataframe, WalkingSpeedValidator, TimeHesitationDetector
from auditors import PackerRiskScorer, CustomerRefundAuditor
from customer_risk_engine import CustomerRiskEngine
from store_risk_engine import DarkStoreRiskEngine
from analytics_engine import OperationalAnalyticsEngine
from metrics import evaluate
from logging_config import get_logger
from historical_intelligence.historical_models import DailySnapshot

log = get_logger(__name__)


class HistoricalSimulator:
    """
    Simulates 90 days of Dark Store operations.
    Applies systematic operational drifts to demonstrate historical intelligence features:
      - STORE_03 risk increases rapidly over the last 30 days (from low to critical).
      - PKR006 remains in the top 5% risk percentile for multiple weeks.
      - Electronics category anomalies spike in the final 15 days, dragging down Network Health.
    """

    def __init__(self, orders_per_day: int = 40, base_seed: int = 42) -> None:
        self.orders_per_day = orders_per_day
        self.base_seed = base_seed
        self.start_date = datetime(2026, 3, 20, 8, 0, 0) # 90 days before June 18, 2026

    def generate_history(self, progress_callback: Optional[Any] = None) -> list[DailySnapshot]:
        history: list[DailySnapshot] = []
        log.info("Generating 90 days of historical data...", orders_per_day=self.orders_per_day)

        # Pre-generate coordinates and product structures
        sim_init = DarkStoreSimulator(num_orders=10, seed=self.base_seed)
        sim_init._build_shelf_grid()
        sim_init._build_product_catalogue()
        shelf_coords = sim_init._shelf_coords
        products = sim_init._products

        for d in range(90):
            current_date = self.start_date + timedelta(days=d)
            seed = self.base_seed + d
            
            # 1. Run simulator baseline for this day
            sim = DarkStoreSimulator(num_orders=self.orders_per_day, seed=seed)
            # Override shift start to the historical date
            sim._build_shelf_grid()
            sim._build_product_catalogue()
            
            # Run simulation steps manually to control timestamps
            sim._generate_orders()
            # Override order timestamps to match the current day
            for event in sim._scan_events:
                # keep order start delta but offset date
                time_delta = event.timestamp - datetime(2024, 6, 15, 8, 0, 0)
                event.timestamp = current_date + time_delta

            # Inject baseline anomalies
            n_a = max(3, self.orders_per_day // 17)
            n_b = max(3, self.orders_per_day // 20)
            n_c = max(3, self.orders_per_day // 14)

            sim._inject_type_a(n=n_a)
            sim._inject_type_b(n=n_b)
            sim._inject_type_c(n=n_c)

            events = sim._scan_events
            claims = sim._refund_claims
            injected_ids = sim._injected_log_ids

            # 2. Apply Custom Drifts based on day index (0 to 89)
            # Drift A: PKR006 is consistently high risk (top 5% packer).
            # Force PKR006 to have multiple speed anomalies on most days.
            if d % 2 == 0:
                pkr006_orders = [e.order_id for e in events if e.packer_id == "PKR006"]
                if pkr006_orders:
                    # Inject a speed violation on PKR006
                    ord_id = pkr006_orders[0]
                    ord_events = [e for e in events if e.order_id == ord_id]
                    if len(ord_events) >= 2:
                        # Make second event close in time but far in distance to trigger Type-A
                        ev = ord_events[1]
                        ev.timestamp = ord_events[0].timestamp + timedelta(milliseconds=200)
                        ev.shelf_aisle = "E"
                        ev.shelf_num = 9
                        ev.anomaly_detail = "Drift PKR006 TypeA speed flag"
                        injected_ids["A"].append(ev.log_id)

            # Drift B: STORE_03 risk increases rapidly in the last 30 days (day >= 60)
            if d >= 60:
                store_03_orders = [e.order_id for e in events if e.store_id == "STORE_03"]
                # For each order in STORE_03, inject some speed anomalies (Type-A) and hesitations (Type-B)
                for i, ord_id in enumerate(store_03_orders[:4]):
                    ord_events = [e for e in events if e.order_id == ord_id]
                    if len(ord_events) >= 3:
                        if i % 2 == 0:
                            # Speed flag
                            ev = ord_events[1]
                            ev.timestamp = ord_events[0].timestamp + timedelta(milliseconds=150)
                            ev.shelf_aisle = "D"
                            ev.shelf_num = 10
                            ev.anomaly_detail = "Drift STORE_03 TypeA speed flag"
                            injected_ids["A"].append(ev.log_id)
                        else:
                            # Hesitation flag (Dwell time)
                            ev = ord_events[2]
                            ev.timestamp = ev.timestamp + timedelta(seconds=240)
                            ev.anomaly_detail = "Drift STORE_03 TypeB hesitation"
                            injected_ids["B"].append(ev.log_id)

            # Drift C: Electronics anomalies spike in the last 15 days (day >= 75)
            # Dragging network health down
            if d >= 75:
                elec_events = [e for e in events if products[e.item_id].category == "ELECTRONICS"]
                for i, ev in enumerate(elec_events[:5]):
                    # Delay scan to trigger TimeHesitationDetector (Type-B)
                    ev.timestamp = ev.timestamp + timedelta(seconds=280)
                    ev.anomaly_detail = "Drift Electronics TypeB hesitation"
                    injected_ids["B"].append(ev.log_id)

            # 3. Execute IVC pipeline for this day
            df = scan_events_to_dataframe(events)
            store_map = {e.log_id: e.store_id for e in events}
            df["store_id"] = df["log_id"].map(store_map)

            # Detectors
            wsv = WalkingSpeedValidator(df, shelf_coords)
            df = wsv.detect()
            speed_violations = wsv.violations

            thd = TimeHesitationDetector(df, products)
            df = thd.detect()
            hesit_violations = thd.violations

            # Packer Scorer
            scorer = PackerRiskScorer(speed_violations, hesit_violations)
            packer_profiles = scorer.compute()

            # Refund Auditor
            auditor = CustomerRefundAuditor(claims, df, packer_profiles)
            audit_results = auditor.audit()

            # Customer Risk Engine
            cre = CustomerRiskEngine(claims, audit_results)
            customer_profiles = cre.compute()

            # Store Risk Engine
            dsre = DarkStoreRiskEngine(events, speed_violations, hesit_violations, claims)
            store_profiles = dsre.compute()

            # Operational Analytics
            oae = OperationalAnalyticsEngine(
                events, df, speed_violations, hesit_violations,
                claims, audit_results, packer_profiles, products,
            )
            analytics = oae.compute()

            # 4. Extract Daily Metrics for Snapshot
            snap = DailySnapshot(
                day_idx=d,
                date=current_date,
                total_orders=analytics.total_orders if analytics else 0,
                total_anomalies=len(speed_violations) + len(hesit_violations),
                total_refund_claims=len(claims),
                total_revenue=analytics.total_revenue_processed if analytics else 0.0,
                revenue_leakage=analytics.revenue_leakage_estimate if analytics else 0.0,
                revenue_at_risk=sum(p.revenue_at_risk for p in store_profiles.values()),
                refund_abuse_rate=analytics.refund_abuse_rate if analytics else 0.0,
                anomaly_rate=analytics.anomaly_rate_overall if analytics else 0.0,
            )

            # Extract store metrics
            for sid, p in store_profiles.items():
                snap.store_metrics[sid] = {
                    "risk_score": p.store_risk_score,
                    "orders": float(p.orders_processed),
                    "anomalies": float(p.type_a_events + p.type_b_events),
                    "revenue_at_risk": p.revenue_at_risk,
                }

            # Extract packer metrics
            for pid, p in packer_profiles.items():
                snap.packer_metrics[pid] = {
                    "risk_score": float(p.total_score),
                    "anomalies": float(p.type_a_count + p.type_b_count),
                }

            # Extract customer metrics
            for cid, p in customer_profiles.items():
                snap.customer_metrics[cid] = {
                    "risk_score": p.risk_score,
                    "refunds": float(p.refund_count),
                    "claims_value": p.total_claim_value,
                }

            # Extract category & SKU anomaly counts for this day
            cat_counts: dict[str, int] = {}
            for v in hesit_violations:
                cat_counts[v.category] = cat_counts.get(v.category, 0) + 1
            for cat, count in cat_counts.items():
                snap.category_metrics[cat] = {"anomalies": float(count)}

            sku_counts: dict[str, int] = {}
            for v in speed_violations:
                sku_counts[v.item_id] = sku_counts.get(v.item_id, 0) + 1
            for v in hesit_violations:
                sku_counts[v.item_id] = sku_counts.get(v.item_id, 0) + 1
            for sku, count in sku_counts.items():
                snap.sku_metrics[sku] = {"anomalies": float(count)}

            history.append(snap)
            if progress_callback:
                progress_callback(d + 1, 90)

        log.info("Historical data generation complete.", total_days=len(history))
        return history
