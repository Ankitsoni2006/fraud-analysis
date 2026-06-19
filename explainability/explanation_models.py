"""
explainability/explanation_models.py
=====================================
Typed domain models for every explanation produced by the Explainability Layer.

All models are pure dataclasses — no business logic, no side effects.
The explanation engine populates them; the dashboard consumes them.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


# ── Shared primitives ─────────────────────────────────────────────────────────

@dataclass
class ContributingFactor:
    """A single named driver contributing to a risk score."""
    label:       str
    value:       str
    weight:      float   # 0–100 contribution to total score
    is_primary:  bool = False


@dataclass
class ScoreBreakdown:
    """
    Decomposed view of how a total score was assembled.
    All components should sum to approximately total_score.
    """
    total_score:        float
    components:         dict[str, float] = field(default_factory=dict)

    def top_component(self) -> Optional[str]:
        if not self.components:
            return None
        return max(self.components, key=lambda k: self.components[k])


# ── Phase 1: Packer Explanation ───────────────────────────────────────────────

@dataclass
class PackerExplanation:
    """
    Full explainability record for a single packer's risk score.
    Every field is populated deterministically from pipeline outputs.
    """
    packer_id:              str
    risk_score:             int
    risk_level:             str
    type_a_count:           int
    type_b_count:           int
    type_a_contribution:    int        # score points from Type-A
    type_b_contribution:    int        # score points from Type-B
    refund_exposure_inr:    float      # INR value of refund claims on this packer's orders
    anomaly_share_pct:      float      # % of total platform anomalies this packer accounts for
    primary_driver:         str
    secondary_driver:       str
    platform_avg_score:     float      # platform average packer risk score
    difference_pct:         float      # difference % from platform average
    percentile_rank:        str        # e.g., "Top 10%"
    contribution_breakdown: dict[str, float] = field(default_factory=dict) # e.g. {"Type-A": 67, ...}
    recommended_action:     str = ""
    contributing_factors:   list[ContributingFactor] = field(default_factory=list)
    score_breakdown:        Optional[ScoreBreakdown] = None
    summary:                str = ""
    evidence:               dict[str, str] = field(default_factory=dict)


# ── Phase 2: Customer Explanation ─────────────────────────────────────────────

@dataclass
class CustomerExplanation:
    """
    Full explainability record for a single customer's fraud risk score.
    """
    customer_id:              str
    risk_score:               float
    risk_level:               str
    refund_count:             int
    high_value_claim_count:   int
    total_orders:             int
    refund_rate:              float
    total_claim_value_inr:    float
    average_claim_value_inr:  float
    platform_avg_refund_rate: float    # network baseline for comparison
    refund_rate_multiplier:   float    # how many x above baseline
    difference_pct:           float    # difference % from platform average refund rate
    percentile_rank:          str        # e.g., "Top 3%"
    primary_driver:           str
    recommended_action:       str = ""
    contributing_factors:     list[ContributingFactor] = field(default_factory=list)
    score_breakdown:          Optional[ScoreBreakdown] = None
    summary:                  str = ""


# ── Phase 3: Store Explanation ────────────────────────────────────────────────

@dataclass
class StoreExplanation:
    """
    Full explainability record for a dark store's operational risk score.
    """
    store_id:               str
    risk_score:             float
    risk_level:             str
    orders_processed:       int
    type_a_events:          int
    type_b_events:          int
    refund_claims:          int
    revenue_at_risk_inr:    float
    high_risk_packer_count: int
    anomaly_share_pct:      float      # % of total platform anomalies
    network_avg_score:      float      # mean store risk score across network
    difference_pct:         float      # difference % from network average score
    percentile_rank:        str        # e.g., "Top 10%"
    primary_driver:         str
    secondary_driver:       str = ""
    recommended_action:     str = ""
    contributing_factors:   list[ContributingFactor] = field(default_factory=list)
    score_breakdown:        Optional[ScoreBreakdown] = None
    summary:                str = ""


# ── Phase 4: Refund Decision Explanation ──────────────────────────────────────

@dataclass
class RefundDecisionExplanation:
    """
    Full explainability record for a single refund audit verdict.
    """
    refund_id:          str
    order_id:           str
    item_id:            str
    claimed_value_inr:  float
    verdict:            str           # "APPROVE" | "REJECT"
    confidence_pct:     float         # 0–100
    primary_reason:     str
    reasons:            list[str] = field(default_factory=list)
    risk_signals:       dict[str, str] = field(default_factory=dict)
    was_fraud:          bool = False   # ground-truth label (simulation only)
    summary:            str = ""


# ── Phase 6: Root Cause Intelligence ─────────────────────────────────────────

@dataclass
class NetworkRiskDriver:
    """A single identified root-cause driver across the entire network."""
    rank:         int
    category:     str    # e.g. "SKU", "Store", "Category", "Customer Profile"
    entity:       str    # e.g. "SKU013", "STORE_02", "COSMETICS"
    metric:       str    # e.g. "anomaly_count", "revenue_at_risk"
    value:        float
    share_pct:    float  # % of total platform metric
    narrative:    str    # one-sentence human-readable finding


@dataclass
class RootCauseReport:
    """
    Full root-cause intelligence snapshot for the pipeline run.
    Generated by RootCauseAnalyzer; consumed by the dashboard.
    """
    primary_driver:         NetworkRiskDriver
    secondary_driver:       NetworkRiskDriver
    store_driver:           NetworkRiskDriver
    packer_driver:          NetworkRiskDriver
    drivers:                list[NetworkRiskDriver] = field(default_factory=list)
    top_risky_skus:         list[tuple[str, int]] = field(default_factory=list)
    top_risky_categories:   list[tuple[str, int]] = field(default_factory=list)
    top_risky_stores:       list[tuple[str, float]] = field(default_factory=list)
    top_risky_packers:      list[tuple[str, int]] = field(default_factory=list)
    top_risky_customers:    list[tuple[str, float]] = field(default_factory=list)
    executive_summary:      str = ""
    total_anomalies:        int = 0
    total_revenue_at_risk:  float = 0.0


# ── Phase 8: Executive Narrative ──────────────────────────────────────────────

@dataclass
class ExecutiveNarrative:
    """
    Platform-level executive narrative generated from metrics.
    All strings are programmatically constructed — no hardcoded templates.
    """
    headline:          str
    store_finding:     str
    packer_finding:    str
    customer_finding:  str
    refund_finding:    str
    sku_finding:       str
    recommended_actions: list[str] = field(default_factory=list)