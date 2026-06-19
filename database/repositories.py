"""
database/repositories.py
========================
Repository pattern implementations to persist and fetch domain entities.
"""

from __future__ import annotations

from typing import List, Dict, Optional, Any
from sqlalchemy.orm import Session
from sqlalchemy import delete

from models import (
    ScanEvent, RefundClaim, AuditResult, PackerRiskProfile,
    CustomerRiskProfile, StoreRiskProfile, OperationalAnalytics,
    RiskLevel, RefundVerdict
)
from database.db_models import (
    DBOrder, DBScanEvent, DBRefundClaim, DBAuditResult,
    DBPackerRiskProfile, DBCustomerRiskProfile, DBStoreRiskProfile,
    DBOperationalAnalyticsSnapshot
)


# ── Mappings: Domain <-> DB ───────────────────────────────────────────────────

def to_db_scan_event(domain: ScanEvent) -> DBScanEvent:
    return DBScanEvent(
        log_id=domain.log_id,
        order_id=domain.order_id,
        packer_id=domain.packer_id,
        item_id=domain.item_id,
        shelf_aisle=domain.shelf_aisle,
        shelf_num=domain.shelf_num,
        timestamp=domain.timestamp,
        store_id=domain.store_id,
        anomaly_type=str(domain.anomaly_type) if domain.anomaly_type else None,
        anomaly_detail=domain.anomaly_detail,
        computed_velocity_ms=domain.computed_velocity_ms,
        distance_from_prev_m=domain.distance_from_prev_m,
        speed_flag=domain.speed_flag,
        gap_seconds=domain.gap_seconds,
        hesitation_flag=domain.hesitation_flag,
    )


def to_domain_scan_event(db: DBScanEvent) -> ScanEvent:
    from models import AnomalyType
    # Convert string back to Enum if possible
    anom_type = None
    if db.anomaly_type:
        for t in AnomalyType:
            if t.value == db.anomaly_type:
                anom_type = t
                break
    
    event = ScanEvent(
        log_id=db.log_id,
        order_id=db.order_id,
        packer_id=db.packer_id,
        item_id=db.item_id,
        shelf_aisle=db.shelf_aisle,
        shelf_num=db.shelf_num,
        timestamp=db.timestamp,
        store_id=db.store_id,
        anomaly_type=anom_type,
        anomaly_detail=db.anomaly_detail,
    )
    event.computed_velocity_ms = db.computed_velocity_ms
    event.distance_from_prev_m = db.distance_from_prev_m
    event.speed_flag = db.speed_flag
    event.gap_seconds = db.gap_seconds
    event.hesitation_flag = db.hesitation_flag
    return event


def to_db_refund_claim(domain: RefundClaim) -> DBRefundClaim:
    return DBRefundClaim(
        refund_id=domain.refund_id,
        order_id=domain.order_id,
        customer_id=domain.customer_id,
        item_id=domain.item_id,
        claimed_value_inr=domain.claimed_value_inr,
        claim_reason=domain.claim_reason,
        request_ts=domain.request_ts,
        injected_fraud=domain.injected_fraud,
    )


def to_domain_refund_claim(db: DBRefundClaim) -> RefundClaim:
    return RefundClaim(
        refund_id=db.refund_id,
        order_id=db.order_id,
        customer_id=db.customer_id,
        item_id=db.item_id,
        claimed_value_inr=db.claimed_value_inr,
        claim_reason=db.claim_reason,
        request_ts=db.request_ts,
        injected_fraud=db.injected_fraud,
    )


def to_db_audit_result(domain: AuditResult) -> DBAuditResult:
    return DBAuditResult(
        refund_id=domain.refund_id,
        order_id=domain.order_id,
        item_id=domain.item_id,
        claimed_value_inr=domain.claimed_value_inr,
        verdict=str(domain.verdict),
        audit_reason=domain.audit_reason,
        was_injected_fraud=domain.was_injected_fraud,
    )


def to_domain_audit_result(db: DBAuditResult) -> AuditResult:
    # Match verdict string to Enum
    verdict = RefundVerdict.APPROVE if db.verdict == RefundVerdict.APPROVE.value else RefundVerdict.REJECT
    return AuditResult(
        refund_id=db.refund_id,
        order_id=db.order_id,
        item_id=db.item_id,
        claimed_value_inr=db.claimed_value_inr,
        verdict=verdict,
        audit_reason=db.audit_reason,
        was_injected_fraud=db.was_injected_fraud,
    )


def to_db_packer_risk(domain: PackerRiskProfile) -> DBPackerRiskProfile:
    return DBPackerRiskProfile(
        packer_id=domain.packer_id,
        type_a_count=domain.type_a_count,
        type_b_count=domain.type_b_count,
        total_score=domain.total_score,
        risk_level=str(domain.risk_level),
    )


def to_domain_packer_risk(db: DBPackerRiskProfile) -> PackerRiskProfile:
    r_level = RiskLevel.LOW
    for lvl in RiskLevel:
        if lvl.value == db.risk_level:
            r_level = lvl
            break
    return PackerRiskProfile(
        packer_id=db.packer_id,
        type_a_count=db.type_a_count,
        type_b_count=db.type_b_count,
        total_score=db.total_score,
        risk_level=r_level,
    )


def to_db_customer_risk(domain: CustomerRiskProfile) -> DBCustomerRiskProfile:
    return DBCustomerRiskProfile(
        customer_id=domain.customer_id,
        refund_count=domain.refund_count,
        high_value_refund_count=domain.high_value_refund_count,
        total_orders=domain.total_orders,
        refund_rate=domain.refund_rate,
        total_claim_value=domain.total_claim_value,
        average_claim_value=domain.average_claim_value,
        risk_score=domain.risk_score,
        risk_level=str(domain.risk_level),
    )


def to_domain_customer_risk(db: DBCustomerRiskProfile) -> CustomerRiskProfile:
    r_level = RiskLevel.LOW
    for lvl in RiskLevel:
        if lvl.value == db.risk_level:
            r_level = lvl
            break
    return CustomerRiskProfile(
        customer_id=db.customer_id,
        refund_count=db.refund_count,
        high_value_refund_count=db.high_value_refund_count,
        total_orders=db.total_orders,
        refund_rate=db.refund_rate,
        total_claim_value=db.total_claim_value,
        average_claim_value=db.average_claim_value,
        risk_score=db.risk_score,
        risk_level=r_level,
    )


def to_db_store_risk(domain: StoreRiskProfile) -> DBStoreRiskProfile:
    return DBStoreRiskProfile(
        store_id=domain.store_id,
        orders_processed=domain.orders_processed,
        refund_claims=domain.refund_claims,
        type_a_events=domain.type_a_events,
        type_b_events=domain.type_b_events,
        revenue_at_risk=domain.revenue_at_risk,
        store_risk_score=domain.store_risk_score,
        risk_level=str(domain.risk_level),
    )


def to_domain_store_risk(db: DBStoreRiskProfile) -> StoreRiskProfile:
    r_level = RiskLevel.LOW
    for lvl in RiskLevel:
        if lvl.value == db.risk_level:
            r_level = lvl
            break
    return StoreRiskProfile(
        store_id=db.store_id,
        orders_processed=db.orders_processed,
        refund_claims=db.refund_claims,
        type_a_events=db.type_a_events,
        type_b_events=db.type_b_events,
        revenue_at_risk=db.revenue_at_risk,
        store_risk_score=db.store_risk_score,
        risk_level=r_level,
    )


def to_db_analytics(domain: OperationalAnalytics) -> DBOperationalAnalyticsSnapshot:
    return DBOperationalAnalyticsSnapshot(
        total_orders=domain.total_orders,
        total_scans=domain.total_scans,
        total_revenue_processed=domain.total_revenue_processed,
        revenue_leakage_estimate=domain.revenue_leakage_estimate,
        average_order_value=domain.average_order_value,
        average_pack_time_s=domain.average_pack_time_s,
        anomaly_rate_overall=domain.anomaly_rate_overall,
        refund_abuse_rate=domain.refund_abuse_rate,
        high_value_anomaly_rate=domain.high_value_anomaly_rate,
        anomaly_rate_by_store=domain.anomaly_rate_by_store,
        anomaly_rate_by_packer=domain.anomaly_rate_by_packer,
        top_risky_skus=domain.top_risky_skus,
        top_risky_categories=domain.top_risky_categories,
        revenue_by_category=domain.revenue_by_category,
    )


def to_domain_analytics(db: DBOperationalAnalyticsSnapshot) -> OperationalAnalytics:
    return OperationalAnalytics(
        total_orders=db.total_orders,
        total_scans=db.total_scans,
        total_revenue_processed=db.total_revenue_processed,
        revenue_leakage_estimate=db.revenue_leakage_estimate,
        average_order_value=db.average_order_value,
        average_pack_time_s=db.average_pack_time_s,
        anomaly_rate_overall=db.anomaly_rate_overall,
        refund_abuse_rate=db.refund_abuse_rate,
        high_value_anomaly_rate=db.high_value_anomaly_rate,
        anomaly_rate_by_store=db.anomaly_rate_by_store,
        anomaly_rate_by_packer=db.anomaly_rate_by_packer,
        top_risky_skus=[tuple(x) for x in db.top_risky_skus] if db.top_risky_skus else [],
        top_risky_categories=[tuple(x) for x in db.top_risky_categories] if db.top_risky_categories else [],
        revenue_by_category=db.revenue_by_category,
    )


# ── Repositories ──────────────────────────────────────────────────────────────

class IVCRepository:
    """Consolidated repository handling all pipeline saves/loads."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def clear_database(self) -> None:
        """Purges existing data for clean transaction loads."""
        self.db.execute(delete(DBOrder))
        self.db.execute(delete(DBScanEvent))
        self.db.execute(delete(DBRefundClaim))
        self.db.execute(delete(DBAuditResult))
        self.db.execute(delete(DBPackerRiskProfile))
        self.db.execute(delete(DBCustomerRiskProfile))
        self.db.execute(delete(DBStoreRiskProfile))
        self.db.execute(delete(DBOperationalAnalyticsSnapshot))
        self.db.commit()

    def save_pipeline_result(self, result: Any, orders: Optional[List[Dict[str, Any]]] = None) -> None:
        """
        Saves a full PipelineResult run, plus any loaded Order data.
        Performs clearing before saving to ensure state consistency.
        """
        self.clear_database()

        # 1. Save Orders if provided
        if orders:
            for o in orders:
                db_o = DBOrder(
                    order_id=o["order_id"],
                    customer_id=o["customer_id"],
                    store_id=o["store_id"],
                    timestamp=o["timestamp"],
                )
                self.db.add(db_o)

        # 2. Save Scan Events
        for event in result.validated_logs:
            self.db.add(to_db_scan_event(event))

        # 3. Save Refund Claims
        for claim in result.refund_claims:
            self.db.add(to_db_refund_claim(claim))

        # 4. Save Audit Results
        for audit in result.audit_results:
            self.db.add(to_db_audit_result(audit))

        # 5. Save Packer Profiles
        for packer in result.packer_risk_profiles.values():
            self.db.add(to_db_packer_risk(packer))

        # 6. Save Customer Profiles
        for customer in result.customer_risk_profiles.values():
            self.db.add(to_db_customer_risk(customer))

        # 7. Save Store Profiles
        for store in result.store_risk_profiles.values():
            self.db.add(to_db_store_risk(store))

        # 8. Save Operational Analytics
        if result.operational_analytics:
            self.db.add(to_db_analytics(result.operational_analytics))

        self.db.commit()

    def get_orders(self) -> List[Dict[str, Any]]:
        orders = self.db.query(DBOrder).all()
        return [
            {
                "order_id": o.order_id,
                "customer_id": o.customer_id,
                "store_id": o.store_id,
                "timestamp": o.timestamp,
            }
            for o in orders
        ]

    def get_scan_events(self) -> List[ScanEvent]:
        db_events = self.db.query(DBScanEvent).all()
        return [to_domain_scan_event(e) for e in db_events]

    def get_refund_claims(self) -> List[RefundClaim]:
        db_claims = self.db.query(DBRefundClaim).all()
        return [to_domain_refund_claim(c) for c in db_claims]

    def get_audit_results(self) -> List[AuditResult]:
        db_audits = self.db.query(DBAuditResult).all()
        return [to_domain_audit_result(a) for a in db_audits]

    def get_packer_profiles(self) -> Dict[str, PackerRiskProfile]:
        db_profiles = self.db.query(DBPackerRiskProfile).all()
        return {p.packer_id: to_domain_packer_risk(p) for p in db_profiles}

    def get_customer_profiles(self) -> Dict[str, CustomerRiskProfile]:
        db_profiles = self.db.query(DBCustomerRiskProfile).all()
        return {c.customer_id: to_domain_customer_risk(c) for c in db_profiles}

    def get_store_profiles(self) -> Dict[str, StoreRiskProfile]:
        db_profiles = self.db.query(DBStoreRiskProfile).all()
        return {s.store_id: to_domain_store_risk(s) for s in db_profiles}

    def get_latest_analytics(self) -> Optional[OperationalAnalytics]:
        db_analytics = self.db.query(DBOperationalAnalyticsSnapshot).order_by(DBOperationalAnalyticsSnapshot.id.desc()).first()
        if db_analytics:
            return to_domain_analytics(db_analytics)
        return None
