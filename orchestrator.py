"""
ivc/orchestrator.py
===================
IVC pipeline orchestrator — extended for Phase 1–3 engines.

Wires together all components in the correct order.
Returns a fully-typed PipelineResult including customer, store, and analytics data.
"""

from __future__ import annotations

import time
from typing import Optional

from analytics_engine import OperationalAnalyticsEngine
from auditors import CustomerRefundAuditor, PackerRiskScorer
from customer_risk_engine import CustomerRiskEngine
from dashboard import IVCDashboard
from detectors import TimeHesitationDetector, WalkingSpeedValidator, scan_events_to_dataframe
from exceptions import IVCError
from logging_config import get_logger
from metrics import evaluate
from models import PipelineResult
from simulator import DarkStoreSimulator
from store_risk_engine import DarkStoreRiskEngine

log = get_logger(__name__)


class IVCOrchestrator:
    """
    End-to-end IVC Operational Risk Intelligence pipeline.

    Steps:
      1.  Simulate dark-store data (10 stores, realistic customers).
      2.  Convert to DataFrame once.
      3.  Speed detection (Type A).
      4.  Hesitation detection (Type B).
      5.  Packer risk scoring.
      6.  Refund audit.
      7.  Detection quality metrics.
      8.  Customer Risk Engine (Phase 1).
      9.  Dark Store Risk Engine (Phase 2).
      10. Operational Analytics Engine (Phase 3).
      11. Console dashboard.
      12. Return PipelineResult.
    """

    def __init__(
        self,
        num_orders: int = 200,
        scan_events: list[ScanEvent] | None = None,
        refund_claims: list[RefundClaim] | None = None,
        products: dict[str, Product] | None = None,
        shelf_coords: dict[tuple[str, int], tuple[float, float]] | None = None,
    ) -> None:
        self.num_orders = num_orders
        self._scan_events = scan_events
        self._refund_claims = refund_claims
        self._products = products
        self._shelf_coords = shelf_coords
        self._last_result: Optional[PipelineResult] = None

    def run(self, render_dashboard: bool = True) -> PipelineResult:
        pipeline_start = time.perf_counter()
        log.info("IVC pipeline starting", num_orders=self.num_orders)

        try:
            # ── Step 1: Simulate / Load ──────────────────────────────────────
            t0 = time.perf_counter()
            if self._scan_events is not None:
                log.info("Using provided scan events and refund claims (Real Data mode)")
                scan_events = self._scan_events
                refund_claims = self._refund_claims or []
                
                # Fill/fallback products and shelf_coords if not provided
                if self._products is None or self._shelf_coords is None:
                    # Run a mini-simulator helper to fetch standard product catalog
                    sim_helper = DarkStoreSimulator(num_orders=1, seed=0)
                    sim_helper._build_shelf_grid()
                    sim_helper._build_product_catalogue()
                    self._products = self._products or sim_helper._products
                    self._shelf_coords = self._shelf_coords or sim_helper._shelf_coords
                
                products = self._products
                shelf_coords = self._shelf_coords
                injected_ids = {"A": [], "B": [], "C": []}
            else:
                sim = DarkStoreSimulator(num_orders=self.num_orders)
                scan_events, refund_claims, products, shelf_coords, injected_ids = sim.run()
            log.info(
                "Simulation complete",
                elapsed_ms=round((time.perf_counter() - t0) * 1000),
                scan_events=len(scan_events),
                orders=len({e.order_id for e in scan_events}),
            )

            # ── Step 2: DataFrame ─────────────────────────────────────────────
            t0 = time.perf_counter()
            df = scan_events_to_dataframe(scan_events)
            # Attach store_id from scan events to the dataframe
            store_map = {e.log_id: e.store_id for e in scan_events}
            df["store_id"] = df["log_id"].map(store_map)
            log.info("DataFrame built", rows=len(df), elapsed_ms=round((time.perf_counter() - t0) * 1000))

            # ── Step 3: Speed detection ────────────────────────────────────────
            t0 = time.perf_counter()
            wsv  = WalkingSpeedValidator(df, shelf_coords)
            df   = wsv.detect()
            speed_violations = wsv.violations
            log.info("Speed detection complete", violations=len(speed_violations),
                     elapsed_ms=round((time.perf_counter() - t0) * 1000))

            # ── Step 4: Hesitation detection ───────────────────────────────────
            t0 = time.perf_counter()
            thd  = TimeHesitationDetector(df, products)
            df   = thd.detect()
            hesit_violations = thd.violations
            log.info("Hesitation detection complete", violations=len(hesit_violations),
                     elapsed_ms=round((time.perf_counter() - t0) * 1000))

            # ── Step 5: Packer risk scoring ────────────────────────────────────
            t0 = time.perf_counter()
            scorer        = PackerRiskScorer(speed_violations, hesit_violations)
            risk_profiles = scorer.compute()
            log.info("Risk scoring complete", packers_scored=len(risk_profiles),
                     elapsed_ms=round((time.perf_counter() - t0) * 1000))

            # ── Step 6: Refund audit ───────────────────────────────────────────
            t0 = time.perf_counter()
            auditor      = CustomerRefundAuditor(refund_claims, df, risk_profiles)
            audit_results = auditor.audit()
            log.info("Refund audit complete",
                     elapsed_ms=round((time.perf_counter() - t0) * 1000))

            # ── Step 7: Detection metrics ──────────────────────────────────────
            t0 = time.perf_counter()
            detection_metrics = evaluate(speed_violations, hesit_violations, injected_ids)
            log.info("Metrics computed", elapsed_ms=round((time.perf_counter() - t0) * 1000))

            # ── Step 8: Customer Risk Engine ───────────────────────────────────
            t0 = time.perf_counter()
            cre = CustomerRiskEngine(refund_claims, audit_results)
            customer_profiles = cre.compute()
            log.info("Customer risk engine complete", profiles=len(customer_profiles),
                     elapsed_ms=round((time.perf_counter() - t0) * 1000))

            # ── Step 9: Dark Store Risk Engine ────────────────────────────────
            t0 = time.perf_counter()
            dsre = DarkStoreRiskEngine(scan_events, speed_violations, hesit_violations, refund_claims)
            store_profiles = dsre.compute()
            log.info("Store risk engine complete", stores=len(store_profiles),
                     elapsed_ms=round((time.perf_counter() - t0) * 1000))

            # ── Step 10: Operational Analytics ────────────────────────────────
            t0 = time.perf_counter()
            oae = OperationalAnalyticsEngine(
                scan_events, df, speed_violations, hesit_violations,
                refund_claims, audit_results, risk_profiles, products,
            )
            analytics = oae.compute()
            log.info("Analytics computed", elapsed_ms=round((time.perf_counter() - t0) * 1000))

            # ── Step 11: Console dashboard ────────────────────────────────────
            if render_dashboard:
                dash = IVCDashboard()
                dash.render(
                    validated_df          = df,
                    speed_violations      = speed_violations,
                    hesitation_violations = hesit_violations,
                    audit_results         = audit_results,
                    risk_profiles         = risk_profiles,
                    detection_metrics     = detection_metrics,
                )

            # ── Step 12: Build result ─────────────────────────────────────────
            result = PipelineResult(
                validated_logs          = scan_events,
                speed_violations        = speed_violations,
                hesitation_violations   = hesit_violations,
                audit_results           = audit_results,
                packer_risk_profiles    = risk_profiles,
                precision_type_a        = detection_metrics["type_a"].precision,
                recall_type_a           = detection_metrics["type_a"].recall,
                precision_type_b        = detection_metrics["type_b"].precision,
                recall_type_b           = detection_metrics["type_b"].recall,
                customer_risk_profiles  = customer_profiles,
                store_risk_profiles     = store_profiles,
                operational_analytics   = analytics,
                refund_claims           = refund_claims,
            )

        except IVCError:
            raise
        except Exception as exc:
            log.error("Unexpected pipeline failure", error=str(exc))
            raise IVCError(f"Pipeline failed: {exc}") from exc

        total_ms = round((time.perf_counter() - pipeline_start) * 1000)
        log.info(
            "IVC pipeline complete",
            total_elapsed_ms=total_ms,
            speed_violations=len(result.speed_violations),
            hesitation_violations=len(result.hesitation_violations),
            refunds_blocked=sum(
                1 for r in result.audit_results
                if str(r.verdict) == "REJECT_REFUND"
            ),
        )
        self._last_result = result
        return result