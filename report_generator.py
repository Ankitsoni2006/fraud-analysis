"""
ivc/report_generator.py
=======================
Phase 6 — Professional Report Generator.

Exports structured CSV and JSON reports for all pipeline outputs.
All methods are safe to call even with empty inputs.
"""

from __future__ import annotations

import csv
import json
import os
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

from logging_config import get_logger
from models import (
    AuditResult,
    CustomerRiskProfile,
    OperationalAnalytics,
    PackerRiskProfile,
    PipelineResult,
    SpeedViolation,
    HesitationViolation,
    StoreRiskProfile,
)

log = get_logger(__name__)

_DEFAULT_OUTPUT_DIR = Path("reports")


def _ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def _ts() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


class ReportGenerator:
    """
    Exports IVC pipeline results to CSV and JSON.

    Usage:
        gen = ReportGenerator(result, output_dir="reports")
        paths = gen.export_all()
    """

    def __init__(
        self,
        result:     PipelineResult,
        output_dir: str | Path = _DEFAULT_OUTPUT_DIR,
    ) -> None:
        self._result     = result
        self._output_dir = Path(output_dir)
        _ensure_dir(self._output_dir)
        self._ts = _ts()

    def export_all(self) -> dict[str, str]:
        """
        Exports all report types.
        Returns a dict of report_name → file_path.
        """
        paths: dict[str, str] = {}

        paths.update(self._export_packer_profiles())
        paths.update(self._export_customer_profiles())
        paths.update(self._export_store_profiles())
        paths.update(self._export_refund_findings())
        paths.update(self._export_operational_metrics())
        paths.update(self._export_full_json())

        log.info("Report export complete", files=len(paths), output_dir=str(self._output_dir))
        return paths

    # ── Packer Profiles ───────────────────────────────────────────────────────

    def _export_packer_profiles(self) -> dict[str, str]:
        rows = [
            {
                "packer_id":    p.packer_id,
                "type_a_count": p.type_a_count,
                "type_b_count": p.type_b_count,
                "total_score":  p.total_score,
                "risk_level":   p.risk_level.value,
            }
            for p in sorted(
                self._result.packer_risk_profiles.values(),
                key=lambda x: -x.total_score,
            )
        ]
        csv_path = self._output_dir / f"packer_profiles_{self._ts}.csv"
        json_path = self._output_dir / f"packer_profiles_{self._ts}.json"
        self._write_csv(csv_path, rows, ["packer_id", "type_a_count", "type_b_count", "total_score", "risk_level"])
        self._write_json(json_path, rows)
        return {"packer_profiles_csv": str(csv_path), "packer_profiles_json": str(json_path)}

    # ── Customer Profiles ─────────────────────────────────────────────────────

    def _export_customer_profiles(self) -> dict[str, str]:
        rows = [
            {
                "customer_id":             p.customer_id,
                "refund_count":            p.refund_count,
                "high_value_refund_count": p.high_value_refund_count,
                "total_orders":            p.total_orders,
                "refund_rate":             round(p.refund_rate, 4),
                "total_claim_value_inr":   round(p.total_claim_value, 2),
                "average_claim_value_inr": round(p.average_claim_value, 2),
                "risk_score":              p.risk_score,
                "risk_level":              p.risk_level.value,
            }
            for p in sorted(
                self._result.customer_risk_profiles.values(),
                key=lambda x: -x.risk_score,
            )
        ]
        fields = list(rows[0].keys()) if rows else []
        csv_path  = self._output_dir / f"customer_profiles_{self._ts}.csv"
        json_path = self._output_dir / f"customer_profiles_{self._ts}.json"
        self._write_csv(csv_path, rows, fields)
        self._write_json(json_path, rows)
        return {"customer_profiles_csv": str(csv_path), "customer_profiles_json": str(json_path)}

    # ── Store Profiles ────────────────────────────────────────────────────────

    def _export_store_profiles(self) -> dict[str, str]:
        rows = [
            {
                "store_id":          p.store_id,
                "orders_processed":  p.orders_processed,
                "refund_claims":     p.refund_claims,
                "type_a_events":     p.type_a_events,
                "type_b_events":     p.type_b_events,
                "revenue_at_risk":   round(p.revenue_at_risk, 2),
                "store_risk_score":  p.store_risk_score,
                "risk_level":        p.risk_level.value,
            }
            for p in sorted(
                self._result.store_risk_profiles.values(),
                key=lambda x: -x.store_risk_score,
            )
        ]
        fields = list(rows[0].keys()) if rows else []
        csv_path  = self._output_dir / f"store_profiles_{self._ts}.csv"
        json_path = self._output_dir / f"store_profiles_{self._ts}.json"
        self._write_csv(csv_path, rows, fields)
        self._write_json(json_path, rows)
        return {"store_profiles_csv": str(csv_path), "store_profiles_json": str(json_path)}

    # ── Refund Findings ───────────────────────────────────────────────────────

    def _export_refund_findings(self) -> dict[str, str]:
        rows = [
            {
                "refund_id":           r.refund_id,
                "order_id":            r.order_id,
                "item_id":             r.item_id,
                "claimed_value_inr":   r.claimed_value_inr,
                "verdict":             r.verdict.value,
                "audit_reason":        r.audit_reason,
                "was_injected_fraud":  r.was_injected_fraud,
            }
            for r in self._result.audit_results
        ]
        fields = list(rows[0].keys()) if rows else []
        csv_path  = self._output_dir / f"refund_findings_{self._ts}.csv"
        json_path = self._output_dir / f"refund_findings_{self._ts}.json"
        self._write_csv(csv_path, rows, fields)
        self._write_json(json_path, rows)
        return {"refund_findings_csv": str(csv_path), "refund_findings_json": str(json_path)}

    # ── Operational Metrics ───────────────────────────────────────────────────

    def _export_operational_metrics(self) -> dict[str, str]:
        a = self._result.operational_analytics
        if a is None:
            return {}

        summary = {
            "total_orders":              a.total_orders,
            "total_scans":               a.total_scans,
            "total_revenue_processed":   a.total_revenue_processed,
            "revenue_leakage_estimate":  a.revenue_leakage_estimate,
            "average_order_value":       a.average_order_value,
            "average_pack_time_s":       a.average_pack_time_s,
            "anomaly_rate_overall":      a.anomaly_rate_overall,
            "refund_abuse_rate":         a.refund_abuse_rate,
            "high_value_anomaly_rate":   a.high_value_anomaly_rate,
            "type_a_precision":          round(self._result.precision_type_a, 4),
            "type_a_recall":             round(self._result.recall_type_a, 4),
            "type_b_precision":          round(self._result.precision_type_b, 4),
            "type_b_recall":             round(self._result.recall_type_b, 4),
        }

        csv_path  = self._output_dir / f"operational_metrics_{self._ts}.csv"
        json_path = self._output_dir / f"operational_metrics_{self._ts}.json"
        self._write_csv(csv_path, [summary], list(summary.keys()))
        self._write_json(json_path, summary)
        return {"operational_metrics_csv": str(csv_path), "operational_metrics_json": str(json_path)}

    # ── Full JSON dump ────────────────────────────────────────────────────────

    def _export_full_json(self) -> dict[str, str]:
        a = self._result.operational_analytics

        payload: dict[str, Any] = {
            "generated_at": datetime.now().isoformat(),
            "summary": {
                "total_orders":        self._result.operational_analytics.total_orders if a else 0,
                "speed_violations":    len(self._result.speed_violations),
                "hesit_violations":    len(self._result.hesitation_violations),
                "refunds_blocked":     sum(1 for r in self._result.audit_results if str(r.verdict) == "REJECT_REFUND"),
                "revenue_protected":   sum(r.claimed_value_inr for r in self._result.audit_results if str(r.verdict) == "REJECT_REFUND"),
                "type_a_precision":    round(self._result.precision_type_a, 4),
                "type_a_recall":       round(self._result.recall_type_a, 4),
            },
            "packer_profiles": [
                {
                    "packer_id": p.packer_id,
                    "type_a_count": p.type_a_count,
                    "type_b_count": p.type_b_count,
                    "total_score": p.total_score,
                    "risk_level": p.risk_level.value,
                }
                for p in sorted(self._result.packer_risk_profiles.values(), key=lambda x: -x.total_score)
            ],
            "customer_profiles": [
                {
                    "customer_id": p.customer_id,
                    "refund_count": p.refund_count,
                    "risk_score": p.risk_score,
                    "risk_level": p.risk_level.value,
                }
                for p in sorted(self._result.customer_risk_profiles.values(), key=lambda x: -x.risk_score)
            ],
            "store_profiles": [
                {
                    "store_id": p.store_id,
                    "orders_processed": p.orders_processed,
                    "store_risk_score": p.store_risk_score,
                    "risk_level": p.risk_level.value,
                }
                for p in sorted(self._result.store_risk_profiles.values(), key=lambda x: -x.store_risk_score)
            ],
        }

        json_path = self._output_dir / f"full_report_{self._ts}.json"
        self._write_json(json_path, payload)
        return {"full_report_json": str(json_path)}

    # ── IO helpers ────────────────────────────────────────────────────────────

    @staticmethod
    def _write_csv(path: Path, rows: list[dict], fieldnames: list[str]) -> None:
        if not rows:
            return
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

    @staticmethod
    def _write_json(path: Path, data: Any) -> None:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, default=str)