"""
alerting/alert_engine.py
========================
Core alert evaluation engine. Integrates risk profiles and evaluates active alerts.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from dataclasses import dataclass
from typing import List, Set, Dict

from alerting.rules import DEFAULT_RULES, AlertRule, AlertSeverity
from models import PipelineResult

@dataclass
class Alert:
    alert_id: str
    rule_id: str
    title: str
    description: str
    severity: str
    entity_id: str
    value: float
    timestamp: datetime


class AlertEngine:
    """
    Evaluates rule criteria against a PipelineResult run and network metrics.
    Deduplicates alerts to only report the highest severity alert for any given entity.
    """

    def __init__(self, rules: List[AlertRule] | None = None) -> None:
        self.rules = rules or DEFAULT_RULES

    def evaluate(self, result: PipelineResult, network_health: float = 100.0) -> List[Alert]:
        alerts: List[Alert] = []
        now = datetime.utcnow()

        # 1. Evaluate Store Risk Profiles
        for store_id, profile in result.store_risk_profiles.items():
            for rule in self.rules:
                if "STORE_RISK" in rule.rule_id:
                    if rule.condition(profile.store_risk_score):
                        alerts.append(Alert(
                            alert_id=str(uuid.uuid4()),
                            rule_id=rule.rule_id,
                            title=f"{rule.name}: {store_id}",
                            description=f"{rule.description} (value: {profile.store_risk_score})",
                            severity=rule.severity,
                            entity_id=store_id,
                            value=profile.store_risk_score,
                            timestamp=now
                        ))

        # 2. Evaluate Packer Risk Profiles
        for packer_id, profile in result.packer_risk_profiles.items():
            for rule in self.rules:
                if "PACKER_RISK" in rule.rule_id:
                    if rule.condition(profile.total_score):
                        alerts.append(Alert(
                            alert_id=str(uuid.uuid4()),
                            rule_id=rule.rule_id,
                            title=f"{rule.name}: {packer_id}",
                            description=f"{rule.description} (value: {profile.total_score})",
                            severity=rule.severity,
                            entity_id=packer_id,
                            value=float(profile.total_score),
                            timestamp=now
                        ))

        # 3. Evaluate Customer Risk Profiles
        for customer_id, profile in result.customer_risk_profiles.items():
            for rule in self.rules:
                if "CUSTOMER_RISK" in rule.rule_id:
                    if rule.condition(profile.risk_score):
                        alerts.append(Alert(
                            alert_id=str(uuid.uuid4()),
                            rule_id=rule.rule_id,
                            title=f"{rule.name}: {customer_id}",
                            description=f"{rule.description} (value: {profile.risk_score})",
                            severity=rule.severity,
                            entity_id=customer_id,
                            value=profile.risk_score,
                            timestamp=now
                        ))

        # 4. Evaluate Network Health Score
        for rule in self.rules:
            if "NETWORK_HEALTH" in rule.rule_id:
                if rule.condition(network_health):
                    alerts.append(Alert(
                        alert_id=str(uuid.uuid4()),
                        rule_id=rule.rule_id,
                        title=rule.name,
                        description=f"{rule.description} (value: {network_health})",
                        severity=rule.severity,
                        entity_id="NETWORK",
                        value=network_health,
                        timestamp=now
                    ))

        # 5. Evaluate Refund Abuse Rate Spike
        if result.operational_analytics:
            abuse_rate = result.operational_analytics.refund_abuse_rate
            for rule in self.rules:
                if "REFUND_ABUSE" in rule.rule_id:
                    if rule.condition(abuse_rate):
                        alerts.append(Alert(
                            alert_id=str(uuid.uuid4()),
                            rule_id=rule.rule_id,
                            title=rule.name,
                            description=f"{rule.description} (value: {round(abuse_rate * 100, 1)}%)",
                            severity=rule.severity,
                            entity_id="REFUND_SYSTEM",
                            value=abuse_rate,
                            timestamp=now
                        ))

        # Severity priority sort helper
        severity_priority = {
            AlertSeverity.CRITICAL: 0,
            AlertSeverity.HIGH: 1,
            AlertSeverity.WARNING: 2,
            AlertSeverity.INFO: 3
        }

        # Sort alerts so that higher severity items (CRITICAL=0) appear first
        alerts.sort(key=lambda a: (a.entity_id, severity_priority.get(a.severity, 99)))

        # Deduplicate by entity: keep only the most severe alert per entity
        deduped: List[Alert] = []
        seen_entities: Set[str] = set()

        for a in alerts:
            # We want to allow a single entity to have different alert categories (e.g. store risk vs packer risk),
            # but deduplicate multiple levels of the same category.
            # Category can be parsed from rule_id: "RULE_STORE_RISK_CRITICAL" -> "STORE_RISK"
            category = "_".join(a.rule_id.split("_")[1:-1])
            key = f"{a.entity_id}:{category}"

            if key not in seen_entities:
                seen_entities.add(key)
                deduped.append(a)

        return deduped
