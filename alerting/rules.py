"""
alerting/rules.py
=================
Configurations and definitions for operational risk alert rules.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Any, Dict


class AlertSeverity:
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    WARNING = "WARNING"
    INFO = "INFO"


@dataclass
class AlertRule:
    rule_id: str
    name: str
    description: str
    severity: str
    threshold: float
    # condition takes the current value and returns True if triggered
    condition: Callable[[float], bool]


# Default system rules configuration
DEFAULT_RULES = [
    AlertRule(
        rule_id="RULE_STORE_RISK_CRITICAL",
        name="Dark Store Risk Critical",
        description="A dark store risk score exceeded the critical threshold (>= 70.0)",
        severity=AlertSeverity.CRITICAL,
        threshold=70.0,
        condition=lambda v: v >= 70.0
    ),
    AlertRule(
        rule_id="RULE_STORE_RISK_HIGH",
        name="Dark Store Risk High",
        description="A dark store risk score exceeded the high warning threshold (>= 45.0)",
        severity=AlertSeverity.HIGH,
        threshold=45.0,
        condition=lambda v: v >= 45.0
    ),
    AlertRule(
        rule_id="RULE_PACKER_RISK_CRITICAL",
        name="Packer Anomaly Score Critical",
        description="A packer's total weighted anomaly score exceeded critical limits (>= 10)",
        severity=AlertSeverity.CRITICAL,
        threshold=10.0,
        condition=lambda v: v >= 10.0
    ),
    AlertRule(
        rule_id="RULE_CUSTOMER_RISK_CRITICAL",
        name="Customer Refund Abuse Critical",
        description="A customer's refund abuse risk score is critical (>= 75.0)",
        severity=AlertSeverity.CRITICAL,
        threshold=75.0,
        condition=lambda v: v >= 75.0
    ),
    AlertRule(
        rule_id="RULE_NETWORK_HEALTH_DROOP",
        name="Network Health Score Droop",
        description="The overall platform network health fell below the SLA threshold (< 80.0)",
        severity=AlertSeverity.HIGH,
        threshold=80.0,
        condition=lambda v: v < 80.0
    ),
    AlertRule(
        rule_id="RULE_REFUND_ABUSE_SPIKE",
        name="Refund Abuse Rate Spike",
        description="The proportion of refund claims rejected as fraudulent exceeds 50%",
        severity=AlertSeverity.HIGH,
        threshold=0.50,
        condition=lambda v: v >= 0.50
    )
]
