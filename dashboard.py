"""
ivc/dashboard.py
================
Executive console dashboard — pure presentation layer.

All formatting logic lives here and nowhere else.
The dashboard has zero knowledge of detection algorithms.
It only renders what the orchestrator passes in.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Optional

from metrics import DetectionMetrics
from models import (
    AuditResult,
    HesitationViolation,
    PackerRiskProfile,
    Product,
    RefundVerdict,
    RiskLevel,
    SpeedViolation,
)

import pandas as pd


# ── ASCII table primitives ────────────────────────────────────────────────────

def _pad(text: str, width: int, align: str = "left") -> str:
    s = str(text)
    if align == "right":  return s.rjust(width)
    if align == "center": return s.center(width)
    return s.ljust(width)

def _row(*cols_widths_aligns: tuple) -> str:
    parts = [f" {_pad(v, w, a)} " for v, w, a in cols_widths_aligns]
    return "│" + "│".join(parts) + "│"

def _top(*widths: int) -> str:
    return "┌" + "┬".join("─" * (w + 2) for w in widths) + "┐"

def _div(*widths: int) -> str:
    return "├" + "┼".join("─" * (w + 2) for w in widths) + "┤"

def _bot(*widths: int) -> str:
    return "└" + "┴".join("─" * (w + 2) for w in widths) + "┘"

_SEP  = "═" * 82
_THIN = "─" * 82

RISK_ICONS = {
    RiskLevel.CRITICAL: "🔴 CRITICAL",
    RiskLevel.HIGH:     "🟠 HIGH",
    RiskLevel.MEDIUM:   "🟡 MEDIUM",
    RiskLevel.LOW:      "🟢 LOW",
}


# ── Dashboard ─────────────────────────────────────────────────────────────────

class IVCDashboard:
    """
    Renders a structured, text-based executive dashboard to stdout.

    All public methods accept typed domain objects — never raw DataFrames
    or dicts.  This makes the renderer independently testable.
    """

    def render(
        self,
        *,
        validated_df:          pd.DataFrame,
        speed_violations:      list[SpeedViolation],
        hesitation_violations: list[HesitationViolation],
        audit_results:         list[AuditResult],
        risk_profiles:         dict[str, PackerRiskProfile],
        detection_metrics:     Optional[dict[str, DetectionMetrics]] = None,
    ) -> None:
        self._header()
        self._kpi_section(validated_df, speed_violations, hesitation_violations, audit_results)
        self._leaderboard_section(risk_profiles)
        self._speed_section(speed_violations)
        self._hesitation_section(hesitation_violations)
        self._refund_section(audit_results)
        if detection_metrics:
            self._metrics_section(detection_metrics)
        self._footer()

    # ── Header / Footer ───────────────────────────────────────────────────────

    @staticmethod
    def _header() -> None:
        print()
        print(_SEP)
        print("║" + "  INVENTORY VELOCITY COLLISION (IVC) — FRAUD INTELLIGENCE DASHBOARD  v2.0.0".center(80) + "║")
        print("║" + f"  Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  |  Platform: Quick-Commerce Dark Store".center(80) + "║")
        print(_SEP)

    @staticmethod
    def _footer() -> None:
        print(_SEP)
        print("║" + "  END OF REPORT — IVC v2.0.0 — CONFIDENTIAL".center(80) + "║")
        print(_SEP)
        print()

    # ── KPI Section ───────────────────────────────────────────────────────────

    @staticmethod
    def _kpi_section(
        df: pd.DataFrame,
        speed: list[SpeedViolation],
        hesit: list[HesitationViolation],
        audit: list[AuditResult],
    ) -> None:
        print()
        print("  ┌─ EXECUTIVE SUMMARY ───────────────────────────────────────────────────────┐")

        blocked       = [r for r in audit if r.verdict == RefundVerdict.REJECT]
        revenue_saved = sum(r.claimed_value_inr for r in blocked)

        rows = [
            ("Total Orders Audited",             f"{df['order_id'].nunique():,}"),
            ("Total Item Scans Processed",        f"{len(df):,}"),
            ("Active Packers Monitored",          f"{df['packer_id'].nunique()}"),
            ("Type-A Violations (Speed)",         f"{len(speed)} events"),
            ("Type-B Violations (Hesitation)",    f"{len(hesit)} events"),
            ("Customer Refund Claims Received",   f"{len(audit)}"),
            ("Fraudulent Refunds BLOCKED",        f"{len(blocked)}  ◀ probable customer fraud"),
            ("Revenue Saved (INR)",               f"₹ {revenue_saved:,.2f}"),
        ]
        for label, value in rows:
            print(f"  │  {label:<44}  {value:<28}│")
        print("  └───────────────────────────────────────────────────────────────────────────┘")

    # ── Leaderboard ───────────────────────────────────────────────────────────

    @staticmethod
    def _leaderboard_section(profiles: dict[str, PackerRiskProfile]) -> None:
        print()
        print("  ┌─ PACKER RISK LEADERBOARD ──────────────────────────────────────────────────┐")

        if not profiles:
            print("  │  No anomalies detected.                                                     │")
            print("  └────────────────────────────────────────────────────────────────────────────┘")
            return

        sorted_profiles = sorted(profiles.values(), key=lambda p: -p.total_score)
        W = (6, 12, 10, 10, 14, 18)

        print("  │  " + _top(*W)[1:])
        print("  │  " + _row(
            ("Rank", W[0], "center"), ("Packer ID", W[1], "center"),
            ("Type-A",  W[2], "center"), ("Type-B", W[3], "center"),
            ("Score",   W[4], "center"), ("Risk Level", W[5], "center"),
        )[1:])
        print("  │  " + _div(*W)[1:])

        for rank, p in enumerate(sorted_profiles, 1):
            print("  │  " + _row(
                (f"#{rank}",             W[0], "center"),
                (p.packer_id,           W[1], "center"),
                (p.type_a_count,        W[2], "center"),
                (p.type_b_count,        W[3], "center"),
                (p.total_score,         W[4], "center"),
                (RISK_ICONS[p.risk_level], W[5], "center"),
            )[1:])

        print("  │  " + _bot(*W)[1:])
        print("  └────────────────────────────────────────────────────────────────────────────┘")

    # ── Speed Violations ─────────────────────────────────────────────────────

    @staticmethod
    def _speed_section(violations: list[SpeedViolation]) -> None:
        print()
        print("  ┌─ TYPE-A SPEED VIOLATIONS (Physically Impossible Scan Velocity) ────────────┐")

        if not violations:
            print("  │  No Type-A violations detected.                                             │")
            print("  └────────────────────────────────────────────────────────────────────────────┘")
            return

        W = (12, 10, 8, 10, 12, 22)
        print("  │  " + _top(*W)[1:])
        print("  │  " + _row(
            ("Order ID", W[0], "center"), ("Packer", W[1], "center"),
            ("Item",     W[2], "center"), ("Dist m", W[3], "center"),
            ("Vel m/s",  W[4], "center"), ("Status", W[5], "center"),
        )[1:])
        print("  │  " + _div(*W)[1:])

        for v in violations[:25]:
            vel_str = "∞" if v.velocity_ms == float("inf") else f"{v.velocity_ms:.2f}"
            print("  │  " + _row(
                (v.order_id,            W[0], "left"),
                (v.packer_id,          W[1], "center"),
                (v.item_id,            W[2], "center"),
                (f"{v.distance_m:.1f}", W[3], "right"),
                (vel_str,              W[4], "right"),
                ("TYPE_A_IMPOSSIBLE",  W[5], "left"),
            )[1:])

        print("  │  " + _bot(*W)[1:])
        if len(violations) > 25:
            print(f"  │  … and {len(violations)-25} more (truncated)                                          │")
        print("  └────────────────────────────────────────────────────────────────────────────┘")

    # ── Hesitation Violations ────────────────────────────────────────────────

    @staticmethod
    def _hesitation_section(violations: list[HesitationViolation]) -> None:
        print()
        print("  ┌─ TYPE-B HESITATION VIOLATIONS (Abnormal Dwell on High-Value Items) ────────┐")

        if not violations:
            print("  │  No Type-B violations detected.                                             │")
            print("  └────────────────────────────────────────────────────────────────────────────┘")
            return

        W = (12, 10, 8, 12, 12, 10)
        print("  │  " + _top(*W)[1:])
        print("  │  " + _row(
            ("Order ID",   W[0], "center"), ("Packer",    W[1], "center"),
            ("Item",       W[2], "center"), ("Gap (s)",   W[3], "center"),
            ("Store Avg",  W[4], "center"), ("Sigma",     W[5], "center"),
        )[1:])
        print("  │  " + _div(*W)[1:])

        for v in violations[:25]:
            print("  │  " + _row(
                (v.order_id,                  W[0], "left"),
                (v.packer_id,                W[1], "center"),
                (v.item_id,                  W[2], "center"),
                (f"{v.gap_seconds:.1f}",      W[3], "right"),
                (f"{v.cat_mean_gap:.1f}",     W[4], "right"),
                (f"{v.sigma_distance:.1f}σ",  W[5], "right"),
            )[1:])

        print("  │  " + _bot(*W)[1:])
        if len(violations) > 25:
            print(f"  │  … and {len(violations)-25} more (truncated)                                          │")
        print("  └────────────────────────────────────────────────────────────────────────────┘")

    # ── Refund Audit ──────────────────────────────────────────────────────────

    @staticmethod
    def _refund_section(results: list[AuditResult]) -> None:
        print()
        print("  ┌─ CUSTOMER REFUND AUDIT VERDICTS ───────────────────────────────────────────┐")

        if not results:
            print("  │  No refund claims received.                                                 │")
            print("  └────────────────────────────────────────────────────────────────────────────┘")
            return

        W = (10, 10, 13, 12, 22)
        print("  │  " + _top(*W)[1:])
        print("  │  " + _row(
            ("Order ID",    W[0], "center"), ("Item ID",  W[1], "center"),
            ("Claim (INR)", W[2], "center"), ("Verdict",  W[3], "center"),
            ("Reason",      W[4], "center"),
        )[1:])
        print("  │  " + _div(*W)[1:])

        for r in results:
            icon   = "✅ BLOCKED" if r.verdict == RefundVerdict.REJECT else "❎ APPROVED"
            reason = r.audit_reason[:22]
            print("  │  " + _row(
                (r.order_id,                          W[0], "left"),
                (r.item_id,                           W[1], "center"),
                (f"₹{r.claimed_value_inr:,.0f}",      W[2], "right"),
                (icon,                                W[3], "center"),
                (reason,                              W[4], "left"),
            )[1:])

        print("  │  " + _bot(*W)[1:])
        blocked  = [r for r in results if r.verdict == RefundVerdict.REJECT]
        rev_save = sum(r.claimed_value_inr for r in blocked)
        print(f"  │  BLOCKED: {len(blocked)} / {len(results)}  |  REVENUE PROTECTED: ₹{rev_save:,.2f}{'':>15}│")
        print("  └────────────────────────────────────────────────────────────────────────────┘")

    # ── Detection Metrics ─────────────────────────────────────────────────────

    @staticmethod
    def _metrics_section(metrics: dict[str, DetectionMetrics]) -> None:
        print()
        print("  ┌─ DETECTION QUALITY METRICS (Simulation Ground Truth) ──────────────────────┐")

        W = (10, 6, 6, 6, 12, 12, 12)
        print("  │  " + _top(*W)[1:])
        print("  │  " + _row(
            ("Detector", W[0], "center"), ("TP",  W[1], "center"),
            ("FP",  W[2], "center"), ("FN",  W[3], "center"),
            ("Precision", W[4], "center"), ("Recall", W[5], "center"),
            ("F1 Score",  W[6], "center"),
        )[1:])
        print("  │  " + _div(*W)[1:])

        for name, m in metrics.items():
            print("  │  " + _row(
                (name.upper(),          W[0], "left"),
                (m.true_positives,     W[1], "center"),
                (m.false_positives,    W[2], "center"),
                (m.false_negatives,    W[3], "center"),
                (f"{m.precision:.3f}", W[4], "center"),
                (f"{m.recall:.3f}",    W[5], "center"),
                (f"{m.f1:.3f}",        W[6], "center"),
            )[1:])

        print("  │  " + _bot(*W)[1:])
        print("  └────────────────────────────────────────────────────────────────────────────┘")
