"""
ivc/models.py
=============
Typed domain models for every data structure in the IVC pipeline.
Extended for Phase 1 (CustomerRiskEngine) and Phase 2 (DarkStoreRiskEngine).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import Optional


# ── Enumerations ─────────────────────────────────────────────────────────────

class AnomalyType(str, Enum):
    TYPE_A_SPEED       = "TYPE_A_IMPOSSIBLE_SPEED"
    TYPE_B_HESITATION  = "TYPE_B_HESITATION"

    def __str__(self) -> str:
        return self.value


class RefundVerdict(str, Enum):
    REJECT  = "REJECT_REFUND"
    APPROVE = "APPROVE_REFUND"

    def __str__(self) -> str:
        return self.value


class RiskLevel(str, Enum):
    CRITICAL = "CRITICAL"
    HIGH     = "HIGH"
    MEDIUM   = "MEDIUM"
    LOW      = "LOW"

    def __str__(self) -> str:
        return self.value


# ── Core data classes ─────────────────────────────────────────────────────────

@dataclass
class ShelfLocation:
    aisle: str
    shelf_num: int
    coord_x: float = 0.0
    coord_y: float = 0.0

    def __hash__(self) -> int:
        return hash((self.aisle, self.shelf_num))

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, ShelfLocation):
            return NotImplemented
        return self.aisle == other.aisle and self.shelf_num == other.shelf_num


@dataclass
class Product:
    item_id:       str
    item_name:     str
    category:      str
    value_inr:     float
    shelf:         ShelfLocation
    is_high_value: bool = False

    def __post_init__(self) -> None:
        from config import DETECTION_CONFIG
        self.is_high_value = self.value_inr >= DETECTION_CONFIG.high_value_threshold_inr


@dataclass
class ScanEvent:
    log_id:         str
    order_id:       str
    packer_id:      str
    item_id:        str
    shelf_aisle:    str
    shelf_num:      int
    timestamp:      datetime
    store_id:       str = "STORE_01"           # NEW: dark store assignment
    anomaly_type:   Optional[AnomalyType] = None
    anomaly_detail: Optional[str]         = None

    computed_velocity_ms:    Optional[float] = None
    distance_from_prev_m:    Optional[float] = None
    speed_flag:              bool             = False
    gap_seconds:             Optional[float] = None
    hesitation_flag:         bool             = False

    @staticmethod
    def new_id() -> str:
        return str(uuid.uuid4())


@dataclass
class SpeedViolation:
    log_id:       str
    order_id:     str
    packer_id:    str
    item_id:      str
    distance_m:   float
    delta_s:      float
    velocity_ms:  float
    detection:    AnomalyType = AnomalyType.TYPE_A_SPEED


@dataclass
class HesitationViolation:
    log_id:          str
    order_id:        str
    packer_id:       str
    item_id:         str
    category:        str
    gap_seconds:     float
    cat_mean_gap:    float
    sigma_distance:  float
    value_inr:       float
    detection:       AnomalyType = AnomalyType.TYPE_B_HESITATION


@dataclass
class RefundClaim:
    refund_id:         str
    order_id:          str
    customer_id:       str
    item_id:           str
    claimed_value_inr: float
    claim_reason:      str
    request_ts:        datetime
    injected_fraud:    bool = False


@dataclass
class AuditResult:
    refund_id:          str
    order_id:           str
    item_id:            str
    claimed_value_inr:  float
    verdict:            RefundVerdict
    audit_reason:       str
    was_injected_fraud: bool = False


@dataclass
class PackerRiskProfile:
    packer_id:    str
    type_a_count: int   = 0
    type_b_count: int   = 0
    total_score:  int   = 0
    risk_level:   RiskLevel = RiskLevel.LOW

    def recompute(self, type_a_weight: int, type_b_weight: int,
                  critical_threshold: int, high_threshold: int) -> None:
        self.total_score = (
            self.type_a_count * type_a_weight +
            self.type_b_count * type_b_weight
        )
        if self.total_score >= critical_threshold:
            self.risk_level = RiskLevel.CRITICAL
        elif self.total_score >= high_threshold:
            self.risk_level = RiskLevel.HIGH
        elif self.total_score > 0:
            self.risk_level = RiskLevel.MEDIUM
        else:
            self.risk_level = RiskLevel.LOW


# ── Phase 1: Customer Risk Engine ─────────────────────────────────────────────

@dataclass
class CustomerRiskProfile:
    """Aggregated risk profile for a single customer."""
    customer_id:             str
    refund_count:            int   = 0
    high_value_refund_count: int   = 0
    total_orders:            int   = 0
    refund_rate:             float = 0.0
    total_claim_value:       float = 0.0
    average_claim_value:     float = 0.0
    risk_score:              float = 0.0
    risk_level:              RiskLevel = RiskLevel.LOW

    def recompute(
        self,
        freq_weight:       float = 0.30,
        rate_weight:       float = 0.25,
        hv_weight:         float = 0.25,
        value_weight:      float = 0.20,
        critical_threshold: float = 75.0,
        high_threshold:     float = 50.0,
        medium_threshold:   float = 25.0,
    ) -> None:
        """Weighted scoring — each component normalised 0-100."""
        freq_score  = min(self.refund_count / 5.0,  1.0) * 100
        rate_score  = min(self.refund_rate,          1.0) * 100
        hv_score    = min(self.high_value_refund_count / 3.0, 1.0) * 100
        value_cap   = 5000.0
        value_score = min(self.total_claim_value / value_cap, 1.0) * 100

        self.risk_score = round(
            freq_score  * freq_weight +
            rate_score  * rate_weight +
            hv_score    * hv_weight   +
            value_score * value_weight,
            2,
        )

        if self.risk_score >= critical_threshold:
            self.risk_level = RiskLevel.CRITICAL
        elif self.risk_score >= high_threshold:
            self.risk_level = RiskLevel.HIGH
        elif self.risk_score >= medium_threshold:
            self.risk_level = RiskLevel.MEDIUM
        else:
            self.risk_level = RiskLevel.LOW


# ── Phase 2: Dark Store Risk Engine ──────────────────────────────────────────

@dataclass
class StoreRiskProfile:
    """Aggregated risk profile for a single dark store."""
    store_id:          str
    orders_processed:  int   = 0
    refund_claims:     int   = 0
    type_a_events:     int   = 0
    type_b_events:     int   = 0
    revenue_at_risk:   float = 0.0
    store_risk_score:  float = 0.0
    risk_level:        RiskLevel = RiskLevel.LOW

    def recompute(
        self,
        refund_rate_weight:  float = 0.30,
        type_a_weight:       float = 0.30,
        type_b_weight:       float = 0.20,
        revenue_weight:      float = 0.20,
        critical_threshold:  float = 70.0,
        high_threshold:      float = 45.0,
        medium_threshold:    float = 20.0,
    ) -> None:
        refund_rate  = self.refund_claims / max(self.orders_processed, 1)
        refund_score = min(refund_rate / 0.20, 1.0) * 100

        type_a_rate  = self.type_a_events / max(self.orders_processed, 1)
        type_a_score = min(type_a_rate / 0.10, 1.0) * 100

        type_b_rate  = self.type_b_events / max(self.orders_processed, 1)
        type_b_score = min(type_b_rate / 0.10, 1.0) * 100

        rev_cap      = 50_000.0
        rev_score    = min(self.revenue_at_risk / rev_cap, 1.0) * 100

        self.store_risk_score = round(
            refund_score * refund_rate_weight +
            type_a_score * type_a_weight      +
            type_b_score * type_b_weight      +
            rev_score    * revenue_weight,
            2,
        )

        if self.store_risk_score >= critical_threshold:
            self.risk_level = RiskLevel.CRITICAL
        elif self.store_risk_score >= high_threshold:
            self.risk_level = RiskLevel.HIGH
        elif self.store_risk_score >= medium_threshold:
            self.risk_level = RiskLevel.MEDIUM
        else:
            self.risk_level = RiskLevel.LOW


# ── Phase 3: Operational Analytics ───────────────────────────────────────────

@dataclass
class OperationalAnalytics:
    """Structured analytics snapshot produced by OperationalAnalyticsEngine."""
    total_orders:             int   = 0
    total_scans:              int   = 0
    total_revenue_processed:  float = 0.0
    revenue_leakage_estimate: float = 0.0
    average_order_value:      float = 0.0
    average_pack_time_s:      float = 0.0
    anomaly_rate_overall:     float = 0.0
    refund_abuse_rate:        float = 0.0
    high_value_anomaly_rate:  float = 0.0

    anomaly_rate_by_store:    dict[str, float]       = field(default_factory=dict)
    anomaly_rate_by_packer:   dict[str, float]       = field(default_factory=dict)
    top_risky_skus:           list[tuple[str, int]]  = field(default_factory=list)
    top_risky_categories:     list[tuple[str, int]]  = field(default_factory=list)
    revenue_by_category:      dict[str, float]       = field(default_factory=dict)


# ── Pipeline Result ──────────────────────────────────────────────────────────

@dataclass
class PipelineResult:
    """Unified output returned by IVCOrchestrator.run()."""
    validated_logs:          list[ScanEvent]
    speed_violations:        list[SpeedViolation]
    hesitation_violations:   list[HesitationViolation]
    audit_results:           list[AuditResult]
    packer_risk_profiles:    dict[str, PackerRiskProfile]
    precision_type_a:        float = 0.0
    recall_type_a:           float = 0.0
    precision_type_b:        float = 0.0
    recall_type_b:           float = 0.0

    # New Phase 1-3 outputs
    customer_risk_profiles:  dict[str, CustomerRiskProfile] = field(default_factory=dict)
    store_risk_profiles:     dict[str, StoreRiskProfile]    = field(default_factory=dict)
    operational_analytics:   Optional[OperationalAnalytics] = None
    refund_claims:           list[RefundClaim]              = field(default_factory=list)