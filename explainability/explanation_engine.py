"""
explainability/explanation_engine.py
=====================================
Production-grade Explainability & Root Cause Intelligence Layer.

Generates deterministic, fully-typed explanations for every scored entity
in the IVC pipeline. Zero dependency on Streamlit or any UI framework.

Usage:
    engine = ExplainabilityEngine(pipeline_result)
    explanations = engine.explain_all()
"""

from __future__ import annotations

import sys
import os
from collections import Counter, defaultdict
from typing import Optional

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from models import (
    AuditResult,
    CustomerRiskProfile,
    HesitationViolation,
    PackerRiskProfile,
    PipelineResult,
    RefundClaim,
    RefundVerdict,
    RiskLevel,
    ScanEvent,
    SpeedViolation,
    StoreRiskProfile,
)
from explainability.explanation_models import (
    ContributingFactor,
    CustomerExplanation,
    ExecutiveNarrative,
    NetworkRiskDriver,
    PackerExplanation,
    RefundDecisionExplanation,
    RootCauseReport,
    ScoreBreakdown,
    StoreExplanation,
)


# ── Packer Explainer ──────────────────────────────────────────────────────────

class PackerExplainer:
    """
    Generates PackerExplanation for every packer in the risk profiles.

    Scoring decomposition mirrors PackerRiskScorer weights:
        type_a_contribution = type_a_count × type_a_weight (default 3)
        type_b_contribution = type_b_count × type_b_weight (default 2)
    """

    def __init__(
        self,
        packer_profiles:       dict[str, PackerRiskProfile],
        speed_violations:      list[SpeedViolation],
        hesitation_violations: list[HesitationViolation],
        audit_results:         list[AuditResult],
        scan_events:           list[ScanEvent],
        type_a_weight:         int = 3,
        type_b_weight:         int = 2,
    ) -> None:
        self._profiles   = packer_profiles
        self._speed      = speed_violations
        self._hesit      = hesitation_violations
        self._audits     = audit_results
        self._events     = scan_events
        self._wa         = type_a_weight
        self._wb         = type_b_weight

        # Pre-compute refund exposure per packer
        self._packer_refund_exposure = self._compute_refund_exposure()
        # Pre-compute total anomalies across platform
        self._total_anomalies = len(speed_violations) + len(hesitation_violations)

        # Platform averages and rank sorted list
        scores = [p.total_score for p in packer_profiles.values()]
        self._avg_score = sum(scores) / max(len(scores), 1)
        self._all_scores = sorted(scores, reverse=True)

    def _compute_refund_exposure(self) -> dict[str, float]:
        """Map packer_id → total INR of refund claims on their orders."""
        order_packer: dict[str, str] = {}
        for e in self._events:
            order_packer.setdefault(e.order_id, e.packer_id)

        exposure: dict[str, float] = defaultdict(float)
        for audit in self._audits:
            packer = order_packer.get(audit.order_id)
            if packer:
                exposure[packer] += audit.claimed_value_inr
        return dict(exposure)

    def explain_all(self) -> dict[str, PackerExplanation]:
        return {pid: self._explain_one(profile) for pid, profile in self._profiles.items()}

    def _explain_one(self, profile: PackerRiskProfile) -> PackerExplanation:
        a_contrib  = profile.type_a_count * self._wa
        b_contrib  = profile.type_b_count * self._wb
        exposure   = round(self._packer_refund_exposure.get(profile.packer_id, 0.0), 2)
        packer_anomalies = profile.type_a_count + profile.type_b_count
        share_pct = round(
            100 * packer_anomalies / max(self._total_anomalies, 1), 1
        )

        # Determine primary and secondary drivers
        if a_contrib >= b_contrib:
            primary   = "Type-A Speed Violations"
            secondary = f"Type-B hesitation violations ({profile.type_b_count} events)"
        else:
            primary   = "Type-B Hesitation Violations"
            secondary = f"Type-A speed violations ({profile.type_a_count} events)"

        if exposure > 5000:
            secondary = f"High refund exposure (₹{exposure:,.0f}) associated with orders"

        # Platform average compare
        platform_avg = round(self._avg_score, 2)
        diff_pct = round(100.0 * (profile.total_score - platform_avg) / max(platform_avg, 1.0), 1)

        # Percentile Rank
        rank = sum(1 for s in self._all_scores if s > profile.total_score) + 1
        pct = (rank / len(self._all_scores)) * 100 if self._all_scores else 100.0
        percentile_rank = f"Top {max(1, int(pct))}%"

        # Contribution breakdown
        exposure_contrib = min(exposure / 500.0, 20.0)
        total_contrib_pts = max(a_contrib + b_contrib + exposure_contrib, 1.0)
        contrib_breakdown = {
            "Type-A": round(100.0 * a_contrib / total_contrib_pts, 1),
            "Type-B": round(100.0 * b_contrib / total_contrib_pts, 1),
            "Refund Exposure": round(100.0 * exposure_contrib / total_contrib_pts, 1),
        }

        # Recommended Action
        if profile.risk_level.value == "CRITICAL":
            recommended_action = "Restrict packer access and schedule immediate audit"
        elif profile.risk_level.value == "HIGH":
            recommended_action = "Review shift logs and shelf movement records"
        elif profile.risk_level.value == "MEDIUM":
            recommended_action = "Monitor scan velocities and order completion times"
        else:
            recommended_action = "Continue standard monitoring"

        # Build contributing factors
        factors: list[ContributingFactor] = []
        if profile.type_a_count > 0:
            factors.append(ContributingFactor(
                label=f"{profile.type_a_count} Type-A (impossible speed) violations",
                value=str(profile.type_a_count),
                weight=round(100 * a_contrib / max(profile.total_score, 1), 1),
                is_primary=(a_contrib >= b_contrib),
            ))
        if profile.type_b_count > 0:
            factors.append(ContributingFactor(
                label=f"{profile.type_b_count} Type-B (hesitation) violations",
                value=str(profile.type_b_count),
                weight=round(100 * b_contrib / max(profile.total_score, 1), 1),
                is_primary=(b_contrib > a_contrib),
            ))
        if share_pct > 0:
            factors.append(ContributingFactor(
                label=f"{share_pct}% of all platform anomalies on this packer",
                value=f"{share_pct}%",
                weight=share_pct,
                is_primary=False,
            ))
        if exposure > 0:
            factors.append(ContributingFactor(
                label=f"₹{exposure:,.0f} refund exposure from associated orders",
                value=f"₹{exposure:,.0f}",
                weight=min(round(exposure / 500, 1), 20.0),
                is_primary=False,
            ))

        breakdown = ScoreBreakdown(
            total_score=profile.total_score,
            components={
                "Type-A contribution": float(a_contrib),
                "Type-B contribution": float(b_contrib),
            },
        )

        summary = self._generate_summary(profile, share_pct, exposure)
        evidence = {
            "Type-A weight contribution": str(a_contrib),
            "Type-B weight contribution": str(b_contrib),
            "Refund exposure (INR)":       f"₹{exposure:,.0f}",
            "Anomaly share (platform)":   f"{share_pct}%",
            "Risk tier":                   profile.risk_level.value,
        }

        return PackerExplanation(
            packer_id=profile.packer_id,
            risk_score=profile.total_score,
            risk_level=profile.risk_level.value,
            type_a_count=profile.type_a_count,
            type_b_count=profile.type_b_count,
            type_a_contribution=a_contrib,
            type_b_contribution=b_contrib,
            refund_exposure_inr=exposure,
            anomaly_share_pct=share_pct,
            primary_driver=primary,
            secondary_driver=secondary,
            platform_avg_score=platform_avg,
            difference_pct=diff_pct,
            percentile_rank=percentile_rank,
            contribution_breakdown=contrib_breakdown,
            recommended_action=recommended_action,
            contributing_factors=factors,
            score_breakdown=breakdown,
            summary=summary,
            evidence=evidence,
        )

    @staticmethod
    def _generate_summary(
        profile: PackerRiskProfile, share_pct: float, exposure: float
    ) -> str:
        level = profile.risk_level.value
        if level == "CRITICAL":
            severity = "critically elevated"
        elif level == "HIGH":
            severity = "significantly elevated"
        elif level == "MEDIUM":
            severity = "moderately elevated"
        else:
            severity = "low"

        parts = [
            f"Packer {profile.packer_id} demonstrates {severity} operational anomaly activity "
            f"with a composite risk score of {profile.total_score}."
        ]
        if profile.type_a_count > 0:
            parts.append(
                f"{profile.type_a_count} impossible-speed events indicate potential barcode spoofing."
            )
        if profile.type_b_count > 0:
            parts.append(
                f"{profile.type_b_count} hesitation events on high-value items warrant review."
            )
        if share_pct >= 10:
            parts.append(
                f"This packer accounts for {share_pct}% of all detected platform anomalies."
            )
        if exposure > 1000:
            parts.append(
                f"Associated orders carry ₹{exposure:,.0f} in refund exposure."
            )
        return " ".join(parts)


# ── Customer Explainer ────────────────────────────────────────────────────────

class CustomerExplainer:
    """Generates CustomerExplanation for every customer risk profile."""

    def __init__(
        self,
        customer_profiles: dict[str, CustomerRiskProfile],
    ) -> None:
        self._profiles = customer_profiles
        # Compute platform baseline refund rate
        rates = [p.refund_rate for p in customer_profiles.values()]
        self._avg_rate = sum(rates) / max(len(rates), 1)

        scores = [p.risk_score for p in customer_profiles.values()]
        self._all_scores = sorted(scores, reverse=True)

    def explain_all(self) -> dict[str, CustomerExplanation]:
        return {cid: self._explain_one(p) for cid, p in self._profiles.items()}

    def _explain_one(self, profile: CustomerRiskProfile) -> CustomerExplanation:
        multiplier = round(profile.refund_rate / max(self._avg_rate, 0.001), 1)

        # Score breakdown (mirrors CustomerRiskProfile.recompute weights)
        freq_score  = min(profile.refund_count / 5.0, 1.0) * 100 * 0.30
        rate_score  = min(profile.refund_rate,         1.0) * 100 * 0.25
        hv_score    = min(profile.high_value_refund_count / 3.0, 1.0) * 100 * 0.25
        value_score = min(profile.total_claim_value / 5000.0, 1.0) * 100 * 0.20

        breakdown = ScoreBreakdown(
            total_score=profile.risk_score,
            components={
                "Refund frequency":     round(freq_score, 1),
                "Refund rate":          round(rate_score, 1),
                "High-value claims":    round(hv_score, 1),
                "Cumulative value":     round(value_score, 1),
            },
        )

        # Determine primary driver
        component_scores = {
            "Excessive refund frequency":   freq_score,
            "High refund rate":             rate_score,
            "High-value item claims":       hv_score,
            "High cumulative claim value":  value_score,
        }
        primary_driver = max(component_scores, key=lambda k: component_scores[k])

        # Diff from average rate
        diff_pct = round(100.0 * (profile.refund_rate - self._avg_rate) / max(self._avg_rate, 0.001), 1)

        # Percentile Rank
        rank = sum(1 for s in self._all_scores if s > profile.risk_score) + 1
        pct = (rank / len(self._all_scores)) * 100 if self._all_scores else 100.0
        percentile_rank = f"Top {max(1, int(pct))}%"

        # Recommended Action
        if profile.risk_level.value == "CRITICAL":
            recommended_action = "Suspend refund privileges and blacklist account"
        elif profile.risk_level.value == "HIGH":
            recommended_action = "Flag customer for enhanced verification"
        elif profile.risk_level.value == "MEDIUM":
            recommended_action = "Require photo proof of items for future refund claims"
        else:
            recommended_action = "Continue standard monitoring"

        factors: list[ContributingFactor] = [
            ContributingFactor(
                label=f"{profile.refund_count} refund requests across orders",
                value=str(profile.refund_count),
                weight=round(freq_score, 1),
                is_primary=(primary_driver == "Excessive refund frequency"),
            ),
            ContributingFactor(
                label=f"{round(profile.refund_rate * 100, 1)}% refund rate "
                      f"({multiplier}x platform average)",
                value=f"{round(profile.refund_rate * 100, 1)}%",
                weight=round(rate_score, 1),
                is_primary=(primary_driver == "High refund rate"),
            ),
            ContributingFactor(
                label=f"{profile.high_value_refund_count} high-value item claims",
                value=str(profile.high_value_refund_count),
                weight=round(hv_score, 1),
                is_primary=(primary_driver == "High-value item claims"),
            ),
            ContributingFactor(
                label=f"₹{profile.total_claim_value:,.0f} total claimed value",
                value=f"₹{profile.total_claim_value:,.0f}",
                weight=round(value_score, 1),
                is_primary=(primary_driver == "High cumulative claim value"),
            ),
        ]

        summary = self._generate_summary(profile, multiplier)

        return CustomerExplanation(
            customer_id=profile.customer_id,
            risk_score=profile.risk_score,
            risk_level=profile.risk_level.value,
            refund_count=profile.refund_count,
            high_value_claim_count=profile.high_value_refund_count,
            total_orders=profile.total_orders,
            refund_rate=profile.refund_rate,
            total_claim_value_inr=profile.total_claim_value,
            average_claim_value_inr=profile.average_claim_value,
            platform_avg_refund_rate=round(self._avg_rate, 4),
            refund_rate_multiplier=multiplier,
            difference_pct=diff_pct,
            percentile_rank=percentile_rank,
            primary_driver=primary_driver,
            recommended_action=recommended_action,
            contributing_factors=factors,
            score_breakdown=breakdown,
            summary=summary,
        )

    @staticmethod
    def _generate_summary(profile: CustomerRiskProfile, multiplier: float) -> str:
        level = profile.risk_level.value
        if level == "CRITICAL":
            qualifier = "critically above"
        elif level == "HIGH":
            qualifier = "significantly above"
        elif level == "MEDIUM":
            qualifier = "above"
        else:
            qualifier = "near"

        parts = [
            f"Customer {profile.customer_id} exhibits refund behaviour {qualifier} the "
            f"platform baseline, with a risk score of {profile.risk_score}."
        ]
        if multiplier >= 2.0:
            parts.append(
                f"Their refund rate is {multiplier}x the network average."
            )
        if profile.high_value_refund_count >= 3:
            parts.append(
                f"{profile.high_value_refund_count} high-value claims suggest "
                "systematic targeting of premium SKUs."
            )
        if level in ("HIGH", "CRITICAL"):
            parts.append(
                "Enhanced verification on future orders is recommended."
            )
        return " ".join(parts)


# ── Store Explainer ───────────────────────────────────────────────────────────

class StoreExplainer:
    """Generates StoreExplanation for every dark store risk profile."""

    def __init__(
        self,
        store_profiles:        dict[str, StoreRiskProfile],
        packer_profiles:       dict[str, PackerRiskProfile],
        scan_events:           list[ScanEvent],
        speed_violations:      list[SpeedViolation],
        hesitation_violations: list[HesitationViolation],
    ) -> None:
        self._store_profiles  = store_profiles
        self._packer_profiles = packer_profiles
        self._events          = scan_events
        self._speed           = speed_violations
        self._hesit           = hesitation_violations

        self._total_anomalies = len(speed_violations) + len(hesitation_violations)
        self._network_avg     = (
            sum(p.store_risk_score for p in store_profiles.values())
            / max(len(store_profiles), 1)
        )
        self._all_scores = sorted([p.store_risk_score for p in store_profiles.values()], reverse=True)

        # Build order→store map
        self._order_store: dict[str, str] = {}
        for e in scan_events:
            self._order_store.setdefault(e.order_id, e.store_id)

        # Build store→packer map
        self._store_packers: dict[str, set[str]] = defaultdict(set)
        for e in scan_events:
            self._store_packers[e.store_id].add(e.packer_id)

    def explain_all(self) -> dict[str, StoreExplanation]:
        return {sid: self._explain_one(p) for sid, p in self._store_profiles.items()}

    def _explain_one(self, profile: StoreRiskProfile) -> StoreExplanation:
        store_anomalies = profile.type_a_events + profile.type_b_events
        share_pct = round(100 * store_anomalies / max(self._total_anomalies, 1), 1)

        # Count high-risk packers in this store
        store_packer_ids = self._store_packers.get(profile.store_id, set())
        high_risk_count = sum(
            1 for pid in store_packer_ids
            if pid in self._packer_profiles
            and self._packer_profiles[pid].risk_level in (RiskLevel.HIGH, RiskLevel.CRITICAL)
        )

        # Score breakdown (mirrors StoreRiskProfile.recompute weights)
        refund_rate  = profile.refund_claims / max(profile.orders_processed, 1)
        type_a_rate  = profile.type_a_events / max(profile.orders_processed, 1)
        type_b_rate  = profile.type_b_events / max(profile.orders_processed, 1)

        refund_score = min(refund_rate / 0.20, 1.0) * 100 * 0.30
        type_a_score = min(type_a_rate / 0.10, 1.0) * 100 * 0.30
        type_b_score = min(type_b_rate / 0.10, 1.0) * 100 * 0.20
        rev_score    = min(profile.revenue_at_risk / 50_000.0, 1.0) * 100 * 0.20

        breakdown = ScoreBreakdown(
            total_score=profile.store_risk_score,
            components={
                "Refund rate":       round(refund_score, 1),
                "Type-A rate":       round(type_a_score, 1),
                "Type-B rate":       round(type_b_score, 1),
                "Revenue at risk":   round(rev_score, 1),
            },
        )

        component_scores = {
            "Elevated refund rate":         refund_score,
            "Elevated anomaly concentration": type_a_score,
            "Type-B hesitation activity":   type_b_score,
            "Revenue at risk":              rev_score,
        }
        sorted_components = sorted(component_scores.items(), key=lambda x: -x[1])
        primary_driver = sorted_components[0][0]

        # Determine secondary driver
        if high_risk_count > 0:
            secondary_driver = "Critical-risk packers"
        else:
            secondary_driver = sorted_components[1][0] if len(sorted_components) > 1 else ""

        # Network average compare
        diff_pct = round(100.0 * (profile.store_risk_score - self._network_avg) / max(self._network_avg, 1.0), 1)

        # Percentile Rank
        rank = sum(1 for s in self._all_scores if s > profile.store_risk_score) + 1
        pct = (rank / len(self._all_scores)) * 100 if self._all_scores else 100.0
        percentile_rank = f"Top {max(1, int(pct))}%"

        # Recommended Action
        if profile.risk_level.value == "CRITICAL":
            recommended_action = "Schedule immediate operational audit within 3 days"
        elif profile.risk_level.value == "HIGH":
            recommended_action = "Schedule operational audit within 7 days"
        elif profile.risk_level.value == "MEDIUM":
            recommended_action = "Review store anomaly logs and scan velocities within 14 days"
        else:
            recommended_action = "Continue standard monitoring"

        factors: list[ContributingFactor] = [
            ContributingFactor(
                label=f"{profile.type_a_events} Type-A speed violations",
                value=str(profile.type_a_events),
                weight=round(type_a_score, 1),
                is_primary=(primary_driver == "Elevated anomaly concentration"),
            ),
            ContributingFactor(
                label=f"{profile.type_b_events} Type-B hesitation violations",
                value=str(profile.type_b_events),
                weight=round(type_b_score, 1),
                is_primary=False,
            ),
            ContributingFactor(
                label=f"{profile.refund_claims} refund claims ({round(refund_rate*100,1)}% rate)",
                value=str(profile.refund_claims),
                weight=round(refund_score, 1),
                is_primary=(primary_driver == "Elevated refund rate"),
            ),
            ContributingFactor(
                label=f"₹{profile.revenue_at_risk:,.0f} refund exposure",
                value=f"₹{profile.revenue_at_risk:,.0f}",
                weight=round(rev_score, 1),
                is_primary=(primary_driver == "Revenue at risk"),
            ),
            ContributingFactor(
                label=f"{high_risk_count} high-risk packers operating in store",
                value=str(high_risk_count),
                weight=min(float(high_risk_count * 5), 20.0),
                is_primary=False,
            ),
        ]

        summary = self._generate_summary(profile, share_pct, high_risk_count, primary_driver)

        return StoreExplanation(
            store_id=profile.store_id,
            risk_score=profile.store_risk_score,
            risk_level=profile.risk_level.value,
            orders_processed=profile.orders_processed,
            type_a_events=profile.type_a_events,
            type_b_events=profile.type_b_events,
            refund_claims=profile.refund_claims,
            revenue_at_risk_inr=profile.revenue_at_risk,
            high_risk_packer_count=high_risk_count,
            anomaly_share_pct=share_pct,
            network_avg_score=round(self._network_avg, 2),
            difference_pct=diff_pct,
            percentile_rank=percentile_rank,
            primary_driver=primary_driver,
            secondary_driver=secondary_driver,
            recommended_action=recommended_action,
            contributing_factors=factors,
            score_breakdown=breakdown,
            summary=summary,
        )

    @staticmethod
    def _generate_summary(
        profile: StoreRiskProfile,
        share_pct: float,
        high_risk_count: int,
        primary_driver: str,
    ) -> str:
        level = profile.risk_level.value
        if level == "CRITICAL":
            qualifier = "the highest operational risk in the network"
        elif level == "HIGH":
            qualifier = "significantly elevated operational risk"
        elif level == "MEDIUM":
            qualifier = "moderate operational risk"
        else:
            qualifier = "low operational risk"

        parts = [
            f"Store {profile.store_id} currently represents {qualifier} "
            f"with a score of {profile.store_risk_score}. "
            f"Primary driver: {primary_driver.lower()}."
        ]
        if share_pct >= 15:
            parts.append(
                f"This store contributes {share_pct}% of total platform anomaly volume."
            )
        if high_risk_count >= 2:
            parts.append(
                f"{high_risk_count} high-risk packers are operating in this location."
            )
        return " ".join(parts)


# ── Refund Decision Explainer ─────────────────────────────────────────────────

class RefundDecisionExplainer:
    """Generates RefundDecisionExplanation for every audit result."""

    # Confidence mapping: based on how many risk signals align with the verdict
    _CONFIDENCE_MAP = {
        "REJECT": {0: 60, 1: 72, 2: 84, 3: 92, 4: 97},
        "APPROVE": {0: 55, 1: 68, 2: 80, 3: 88, 4: 95},
    }

    def __init__(
        self,
        audit_results:   list[AuditResult],
        packer_profiles: dict[str, PackerRiskProfile],
        scan_events:     list[ScanEvent],
        customer_profiles: dict[str, CustomerRiskProfile] = None,
        refund_claims:    list[RefundClaim] = None,
    ) -> None:
        self._audits   = audit_results
        self._profiles = packer_profiles
        self._customer_profiles = customer_profiles or {}

        # Build order → packer map
        self._order_packer: dict[str, str] = {}
        for e in scan_events:
            self._order_packer.setdefault(e.order_id, e.packer_id)

        # Build refund_id → customer_id map
        self._refund_customer: dict[str, str] = {}
        if refund_claims:
            for c in refund_claims:
                self._refund_customer[c.refund_id] = c.customer_id

    def explain_all(self) -> list[RefundDecisionExplanation]:
        return [self._explain_one(a) for a in self._audits]

    def _explain_one(self, audit: AuditResult) -> RefundDecisionExplanation:
        is_reject  = str(audit.verdict) == "REJECT_REFUND" or str(audit.verdict) == "RefundVerdict.REJECT"
        verdict    = "REJECT" if is_reject else "APPROVE"
        packer_id  = self._order_packer.get(audit.order_id, "UNKNOWN")
        profile    = self._profiles.get(packer_id)
        cust_id    = self._refund_customer.get(audit.refund_id)
        cust_profile = self._customer_profiles.get(cust_id) if cust_id else None

        reasons: list[str] = []
        signals: dict[str, str] = {}
        signal_count = 0

        # Evidence evaluation
        # 1. Scan presence is the base signal
        scan_missing = "scan not found" in audit.audit_reason.lower()
        if scan_missing:
            reasons.append("Item scan absent from fulfilment log — probable pick miss")
            signals["Scan log"] = "Missing"
            signal_count += 1
        else:
            reasons.append("Item scan confirmed in fulfilment log")
            signals["Scan log"] = "Present"

        # 2. Packer anomaly flags
        has_type_a = "Type-A" in audit.audit_reason or "speed flag" in audit.audit_reason.lower()
        has_type_b = "Type-B" in audit.audit_reason or "hesitation flag" in audit.audit_reason.lower()

        if has_type_a:
            reasons.append("Associated packer carries a Type-A (impossible speed) flag")
            signals["Packer Type-A flag"] = "Present"
            signal_count += 1
        else:
            signals["Packer Type-A flag"] = "Absent"

        if has_type_b:
            reasons.append("Associated packer carries a Type-B (hesitation) flag")
            signals["Packer Type-B flag"] = "Present"
            signal_count += 1
        else:
            signals["Packer Type-B flag"] = "Absent"

        # 3. Packer risk level
        if profile:
            risk_val = profile.risk_level.value
            signals["Packer risk tier"] = risk_val
            if profile.risk_level in (RiskLevel.HIGH, RiskLevel.CRITICAL):
                reasons.append(
                    f"Packer {packer_id} is rated {risk_val} risk "
                    f"(score {profile.total_score})"
                )
                signal_count += 1
            else:
                reasons.append(
                    f"Packer {packer_id} risk score is low (score {profile.total_score})"
                )
        else:
            signals["Packer risk tier"] = "No profile"
            reasons.append("No packer risk profile — fulfilment integrity unverifiable")
            signal_count += 1

        # 4. Customer history
        if cust_profile:
            cust_risk = cust_profile.risk_level.value
            signals["Customer history"] = "Suspicious" if cust_risk in ("HIGH", "CRITICAL") else "Normal"
            if cust_risk in ("HIGH", "CRITICAL"):
                reasons.append(
                    f"Customer has suspicious history (risk level {cust_risk}, score {cust_profile.risk_score})"
                )
                signal_count += 1
        else:
            signals["Customer history"] = "Normal"

        # 5. Is-clean signal for REJECT
        if is_reject and not any([scan_missing, has_type_a, has_type_b]):
            reasons.append(
                "All fulfilment signals are clean — high probability of customer-initiated fraud"
            )

        # Confidence
        bucket = min(signal_count, 4)
        confidence = self._CONFIDENCE_MAP[verdict].get(bucket, 70)

        primary_reason = reasons[0] if reasons else audit.audit_reason

        summary = (
            f"Refund {audit.refund_id[:8]}... for order {audit.order_id} "
            f"{'rejected' if is_reject else 'approved'} with {confidence}% confidence. "
            f"{primary_reason}."
        )

        return RefundDecisionExplanation(
            refund_id=audit.refund_id,
            order_id=audit.order_id,
            item_id=audit.item_id,
            claimed_value_inr=audit.claimed_value_inr,
            verdict=verdict,
            confidence_pct=float(confidence),
            primary_reason=primary_reason,
            reasons=reasons,
            risk_signals=signals,
            was_fraud=audit.was_injected_fraud,
            summary=summary,
        )


# ── Root Cause Analyzer ───────────────────────────────────────────────────────

class RootCauseAnalyzer:
    """
    Identifies the dominant risk drivers across the entire network.
    Generates ranked NetworkRiskDrivers and an executive summary.
    """

    def __init__(
        self,
        speed_violations:      list[SpeedViolation],
        hesitation_violations: list[HesitationViolation],
        store_profiles:        dict[str, StoreRiskProfile],
        packer_profiles:       dict[str, PackerRiskProfile],
        customer_profiles:     dict[str, CustomerRiskProfile],
        audit_results:         list[AuditResult],
        scan_events:           list[ScanEvent],
    ) -> None:
        self._speed    = speed_violations
        self._hesit    = hesitation_violations
        self._stores   = store_profiles
        self._packers  = packer_profiles
        self._customers = customer_profiles
        self._audits   = audit_results
        self._events   = scan_events

    def analyze(self) -> RootCauseReport:
        total_anomalies     = len(self._speed) + len(self._hesit)
        total_revenue_risk  = sum(p.revenue_at_risk for p in self._stores.values())

        # Top risky SKUs
        sku_counter: Counter = Counter()
        for v in self._speed:
            sku_counter[v.item_id] += 1
        for v in self._hesit:
            sku_counter[v.item_id] += 1
        top_skus = sku_counter.most_common(10)

        # Top risky categories
        cat_counter: Counter = Counter()
        for v in self._hesit:
            cat_counter[v.category] += 1
        # Backfill categories from items if needed, but products are well-mapped
        top_categories = cat_counter.most_common(10)

        # Top risky stores (by risk score)
        top_stores = sorted(
            [(p.store_id, p.store_risk_score) for p in self._stores.values()],
            key=lambda x: -x[1],
        )[:5]

        # Top risky packers (by total score)
        top_packers = sorted(
            [(p.packer_id, p.total_score) for p in self._packers.values()],
            key=lambda x: -x[1],
        )[:5]

        # Top risky customers (by risk score)
        top_customers = sorted(
            [(p.customer_id, p.risk_score) for p in self._customers.values()],
            key=lambda x: -x[1],
        )[:5]

        # Build Specific NetworkRiskDrivers
        # 1. Primary Network Driver (Category)
        if top_categories:
            cat, count = top_categories[0]
            share = round(100 * count / max(total_anomalies, 1), 1)
            primary = NetworkRiskDriver(
                rank=1, category="Product category", entity=cat,
                metric="anomaly_count", value=float(count), share_pct=share,
                narrative=f"{cat} category contributes {share}% of total anomalies."
            )
        else:
            primary = _null_driver(1)

        # 2. Secondary Driver (SKU)
        if top_skus:
            sku, count = top_skus[0]
            share = round(100 * count / max(total_anomalies, 1), 1)
            secondary = NetworkRiskDriver(
                rank=2, category="SKU", entity=sku,
                metric="anomaly_count", value=float(count), share_pct=share,
                narrative=f"{sku} contributes {share}%."
            )
        else:
            secondary = _null_driver(2)

        # 3. Store Driver (Store)
        if top_stores:
            sid, score = top_stores[0]
            store_anomalies = (
                self._stores[sid].type_a_events + self._stores[sid].type_b_events
            )
            share = round(100 * store_anomalies / max(total_anomalies, 1), 1)
            store_driver = NetworkRiskDriver(
                rank=3, category="Dark store", entity=sid,
                metric="anomaly_share", value=float(store_anomalies), share_pct=share,
                narrative=f"{sid} contributes {share}%."
            )
        else:
            store_driver = _null_driver(3)

        # 4. Packer Driver (Packer)
        if top_packers:
            pid, score = top_packers[0]
            p = self._packers[pid]
            packer_anomalies = p.type_a_count + p.type_b_count
            share = round(100 * packer_anomalies / max(total_anomalies, 1), 1)
            packer_driver = NetworkRiskDriver(
                rank=4, category="Packer", entity=pid,
                metric="anomaly_share", value=float(packer_anomalies), share_pct=share,
                narrative=f"{pid} contributes {share}%."
            )
        else:
            packer_driver = _null_driver(4)

        drivers = [primary, secondary, store_driver, packer_driver]

        # Driver 5: Refund fraud signal
        fraud_approved = sum(
            1 for a in self._audits if a.was_injected_fraud and str(a.verdict) != "REJECT_REFUND"
        )
        if fraud_approved > 0:
            share = round(100 * fraud_approved / max(len(self._audits), 1), 1)
            drivers.append(NetworkRiskDriver(
                rank=5, category="Refund fraud", entity="Platform-wide",
                metric="approved_fraud_count", value=float(fraud_approved), share_pct=share,
                narrative=(
                    f"{fraud_approved} fraudulent refund claims were approved ({share}% of all claims), "
                    "representing direct revenue leakage."
                ),
            ))

        executive_summary = self._build_executive_summary(
            primary, secondary, store_driver, packer_driver, total_anomalies, total_revenue_risk
        )

        return RootCauseReport(
            primary_driver=primary,
            secondary_driver=secondary,
            store_driver=store_driver,
            packer_driver=packer_driver,
            drivers=drivers,
            top_risky_skus=top_skus,
            top_risky_categories=top_categories,
            top_risky_stores=top_stores,
            top_risky_packers=top_packers,
            top_risky_customers=top_customers,
            executive_summary=executive_summary,
            total_anomalies=total_anomalies,
            total_revenue_at_risk=round(total_revenue_risk, 2),
        )

    @staticmethod
    def _build_executive_summary(
        primary: NetworkRiskDriver,
        secondary: NetworkRiskDriver,
        store_driver: NetworkRiskDriver,
        packer_driver: NetworkRiskDriver,
        total_anomalies: int,
        total_revenue_risk: float,
    ) -> str:
        return (
            f"Primary Network Driver: {primary.narrative} "
            f"Secondary Driver: {secondary.narrative} "
            f"Store Driver: {store_driver.narrative} "
            f"Packer Driver: {packer_driver.narrative} "
            f"Across {total_anomalies} total detected anomalies, "
            f"cumulative revenue at risk is ₹{total_revenue_risk:,.0f}."
        )


def _null_driver(rank: int) -> NetworkRiskDriver:
    return NetworkRiskDriver(
        rank=rank, category="N/A", entity="N/A",
        metric="N/A", value=0.0, share_pct=0.0, narrative="Insufficient data.",
    )


# ── Executive Narrative Engine ────────────────────────────────────────────────

class ExecutiveNarrativeEngine:
    """
    Generates human-readable platform-level executive narratives from metrics.
    All output is programmatically constructed — no hardcoded strings.
    """

    def __init__(
        self,
        packer_explanations:   dict[str, PackerExplanation],
        customer_explanations: dict[str, CustomerExplanation],
        store_explanations:    dict[str, StoreExplanation],
        refund_explanations:   list[RefundDecisionExplanation],
        root_cause:            RootCauseReport,
    ) -> None:
        self._packers   = packer_explanations
        self._customers = customer_explanations
        self._stores    = store_explanations
        self._refunds   = refund_explanations
        self._root      = root_cause

    def generate(self) -> ExecutiveNarrative:
        # Headline
        headline = (
            f"IVC detected {self._root.total_anomalies} anomalies across the network. "
            f"Estimated revenue at risk: ₹{self._root.total_revenue_at_risk:,.0f}."
        )

        # Store finding
        top_store = self._root.top_risky_stores[0] if self._root.top_risky_stores else None
        if top_store:
            sid, score = top_store
            exp = self._stores.get(sid)
            store_finding = (
                f"{sid} currently represents the highest operational risk in the network "
                f"(score {round(score, 1)}"
                + (f", {exp.anomaly_share_pct}% of platform anomalies" if exp else "")
                + ")."
            )
        else:
            store_finding = "No store risk data available."

        # Packer finding
        top_packer = self._root.top_risky_packers[0] if self._root.top_risky_packers else None
        if top_packer:
            pid, score = top_packer
            exp = self._packers.get(pid)
            packer_finding = (
                f"Packer {pid} contributes "
                + (f"{exp.anomaly_share_pct}% of total detected anomalies" if exp else f"the most anomalies (score {score})")
                + "."
            )
        else:
            packer_finding = "No packer risk data available."

        # Customer finding
        top_cust = self._root.top_risky_customers[0] if self._root.top_risky_customers else None
        if top_cust:
            cid, score = top_cust
            exp = self._customers.get(cid)
            cust_finding = (
                f"Customer {cid} exhibits refund behaviour "
                + (f"{exp.refund_rate_multiplier}x above the platform average" if exp else f"at risk score {round(score, 1)}")
                + "."
            )
        else:
            cust_finding = "No customer risk data available."

        # Refund finding
        rejects = [r for r in self._refunds if r.verdict == "REJECT"]
        approves = [r for r in self._refunds if r.verdict == "APPROVE"]
        blocked_value = sum(r.claimed_value_inr for r in rejects)
        refund_finding = (
            f"{len(rejects)} fraudulent refund claims blocked, "
            f"protecting ₹{blocked_value:,.0f}. "
            f"{len(approves)} claims approved."
        )

        # SKU finding
        top_sku = self._root.top_risky_skus[0] if self._root.top_risky_skus else None
        sku_finding = (
            f"SKU {top_sku[0]} is the most frequently flagged product "
            f"({top_sku[1]} violations)."
            if top_sku else "No SKU risk data available."
        )

        # Recommended actions
        actions: list[str] = []
        for sid, score in self._root.top_risky_stores[:2]:
            exp = self._stores.get(sid)
            if exp and exp.risk_level in ("HIGH", "CRITICAL"):
                actions.append(f"Schedule audit for {sid} (risk score {round(score, 1)})")
        for pid, score in self._root.top_risky_packers[:2]:
            exp = self._packers.get(pid)
            if exp and exp.risk_level in ("HIGH", "CRITICAL"):
                actions.append(f"Review packer {pid} shift logs (score {score})")
        for cid, score in self._root.top_risky_customers[:1]:
            exp = self._customers.get(cid)
            if exp and exp.risk_level in ("HIGH", "CRITICAL"):
                actions.append(f"Flag customer {cid} for enhanced verification (score {round(score,1)})")

        return ExecutiveNarrative(
            headline=headline,
            store_finding=store_finding,
            packer_finding=packer_finding,
            customer_finding=cust_finding,
            refund_finding=refund_finding,
            sku_finding=sku_finding,
            recommended_actions=actions,
        )


# ── Unified Engine ────────────────────────────────────────────────────────────

class AllExplanations:
    """Container for all explanation outputs produced by ExplainabilityEngine."""
    __slots__ = (
        "packer", "customer", "store",
        "refund", "root_cause", "narrative",
    )

    def __init__(
        self,
        packer:     dict[str, PackerExplanation],
        customer:   dict[str, CustomerExplanation],
        store:      dict[str, StoreExplanation],
        refund:     list[RefundDecisionExplanation],
        root_cause: RootCauseReport,
        narrative:  ExecutiveNarrative,
    ) -> None:
        self.packer     = packer
        self.customer   = customer
        self.store      = store
        self.refund     = refund
        self.root_cause = root_cause
        self.narrative  = narrative


class ExplainabilityEngine:
    """
    Unified entry point for the IVC Explainability Layer.

    Accepts a PipelineResult and produces AllExplanations —
    a single object containing every explanation type.

    Usage:
        engine = ExplainabilityEngine(result)
        explanations = engine.explain_all()
    """

    def __init__(self, result: PipelineResult) -> None:
        self._result = result

    def explain_all(self) -> AllExplanations:
        r = self._result

        packer_exp = PackerExplainer(
            packer_profiles=r.packer_risk_profiles,
            speed_violations=r.speed_violations,
            hesitation_violations=r.hesitation_violations,
            audit_results=r.audit_results,
            scan_events=r.validated_logs,
        ).explain_all()

        customer_exp = CustomerExplainer(
            customer_profiles=r.customer_risk_profiles,
        ).explain_all()

        store_exp = StoreExplainer(
            store_profiles=r.store_risk_profiles,
            packer_profiles=r.packer_risk_profiles,
            scan_events=r.validated_logs,
            speed_violations=r.speed_violations,
            hesitation_violations=r.hesitation_violations,
        ).explain_all()

        refund_exp = RefundDecisionExplainer(
            audit_results=r.audit_results,
            packer_profiles=r.packer_risk_profiles,
            scan_events=r.validated_logs,
            customer_profiles=r.customer_risk_profiles,
            refund_claims=r.refund_claims,
        ).explain_all()

        root_cause = RootCauseAnalyzer(
            speed_violations=r.speed_violations,
            hesitation_violations=r.hesitation_violations,
            store_profiles=r.store_risk_profiles,
            packer_profiles=r.packer_risk_profiles,
            customer_profiles=r.customer_risk_profiles,
            audit_results=r.audit_results,
            scan_events=r.validated_logs,
        ).analyze()

        narrative = ExecutiveNarrativeEngine(
            packer_explanations=packer_exp,
            customer_explanations=customer_exp,
            store_explanations=store_exp,
            refund_explanations=refund_exp,
            root_cause=root_cause,
        ).generate()

        return AllExplanations(
            packer=packer_exp,
            customer=customer_exp,
            store=store_exp,
            refund=refund_exp,
            root_cause=root_cause,
            narrative=narrative,
        )