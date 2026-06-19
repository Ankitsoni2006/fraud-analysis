"""
ivc/auditors.py
===============
Customer refund auditor and packer risk scoring.
"""

from __future__ import annotations

import pandas as pd

from config import DETECTION_CONFIG
from exceptions import ValidationError
from logging_config import get_logger
from models import (
    AuditResult,
    HesitationViolation,
    PackerRiskProfile,
    RefundClaim,
    RefundVerdict,
    RiskLevel,
    SpeedViolation,
)

log = get_logger(__name__)


class PackerRiskScorer:
    """
    Computes and owns packer anomaly scores.

    Single source of truth — no score re-computation elsewhere.
    Scores are weighted:
        Type A (impossible speed) × cfg.type_a_weight  (default 3)
        Type B (hesitation)       × cfg.type_b_weight  (default 2)
    """

    def __init__(
        self,
        speed_violations:      list[SpeedViolation],
        hesitation_violations: list[HesitationViolation],
    ) -> None:
        self._speed      = speed_violations
        self._hesitation = hesitation_violations
        self._profiles:  dict[str, PackerRiskProfile] = {}

    def compute(self) -> dict[str, PackerRiskProfile]:
        cfg = DETECTION_CONFIG
        profiles: dict[str, PackerRiskProfile] = {}

        for v in self._speed:
            p = profiles.setdefault(v.packer_id, PackerRiskProfile(packer_id=v.packer_id))
            p.type_a_count += 1

        for v in self._hesitation:
            p = profiles.setdefault(v.packer_id, PackerRiskProfile(packer_id=v.packer_id))
            p.type_b_count += 1

        for profile in profiles.values():
            profile.recompute(
                type_a_weight      = cfg.type_a_weight,
                type_b_weight      = cfg.type_b_weight,
                critical_threshold = cfg.risk_critical_threshold,
                high_threshold     = cfg.risk_high_threshold,
            )

        self._profiles = profiles
        log.info(
            "Packer risk scoring complete",
            packers_with_violations=len(profiles),
            critical=sum(1 for p in profiles.values() if p.risk_level == RiskLevel.CRITICAL),
            high=sum(1 for p in profiles.values() if p.risk_level == RiskLevel.HIGH),
        )
        return profiles

    @property
    def profiles(self) -> dict[str, PackerRiskProfile]:
        return self._profiles


class CustomerRefundAuditor:
    """
    Audits refund claims against validated fulfilment logs.

    Decision tree (in priority order):
      1. Item scan NOT found in log → APPROVE (probable pick miss).
      2. Scan found, packer has Type-A speed flag → APPROVE (integrity uncertain).
      3. Scan found, packer has Type-B hesitation flag → APPROVE (possible interference).
      4. Scan found, packer is HIGH/CRITICAL risk → APPROVE pending investigation.
      5. All clean → REJECT (high probability of customer fraud).
    """

    def __init__(
        self,
        claims:          list[RefundClaim],
        validated_df:    pd.DataFrame,
        risk_profiles:   dict[str, PackerRiskProfile],
    ) -> None:
        if validated_df.empty and claims:
            raise ValidationError("Cannot audit refund claims against an empty log DataFrame.")
        self._claims   = claims
        self._log_df   = validated_df
        self._profiles = risk_profiles
        self._results: list[AuditResult] = []

    def audit(self) -> list[AuditResult]:
        if not self._claims:
            log.info("No refund claims to audit.")
            return []

        log_index: dict[tuple[str, str], pd.DataFrame] = {}
        for key, grp in self._log_df.groupby(["order_id", "item_id"]):
            log_index[key] = grp

        results: list[AuditResult] = []
        for claim in self._claims:
            result = self._evaluate_claim(claim, log_index)
            results.append(result)

        blocked = sum(1 for r in results if r.verdict == RefundVerdict.REJECT)
        revenue_protected = sum(
            r.claimed_value_inr for r in results if r.verdict == RefundVerdict.REJECT
        )
        log.info(
            "Refund audit complete",
            total_claims=len(results),
            blocked=blocked,
            revenue_protected_inr=round(revenue_protected, 2),
        )
        self._results = results
        return results

    def _evaluate_claim(
        self,
        claim: RefundClaim,
        log_index: dict[tuple[str, str], pd.DataFrame],
    ) -> AuditResult:
        key   = (claim.order_id, claim.item_id)
        match = log_index.get(key)

        # Rule 1 — scan not found
        if match is None or match.empty:
            return AuditResult(
                refund_id         = claim.refund_id,
                order_id          = claim.order_id,
                item_id           = claim.item_id,
                claimed_value_inr = claim.claimed_value_inr,
                verdict           = RefundVerdict.APPROVE,
                audit_reason      = "Item scan not found in fulfilment log — probable pick miss.",
                was_injected_fraud = claim.injected_fraud,
            )

        scan_row  = match.iloc[0]
        packer_id = scan_row["packer_id"]
        profile   = self._profiles.get(packer_id)
        anom_score = profile.total_score if profile else 0

        speed_flag = bool(scan_row.get("speed_flag", False))
        hesit_flag = bool(scan_row.get("hesitation_flag", False))

        # Rule 2 — Type-A flag on this packer
        if speed_flag:
            return AuditResult(
                refund_id         = claim.refund_id,
                order_id          = claim.order_id,
                item_id           = claim.item_id,
                claimed_value_inr = claim.claimed_value_inr,
                verdict           = RefundVerdict.APPROVE,
                audit_reason      = (
                    f"Packer {packer_id} has Type-A speed flag — "
                    "fulfilment integrity uncertain."
                ),
                was_injected_fraud = claim.injected_fraud,
            )

        # Rule 3 — Type-B flag on this packer
        if hesit_flag:
            return AuditResult(
                refund_id         = claim.refund_id,
                order_id          = claim.order_id,
                item_id           = claim.item_id,
                claimed_value_inr = claim.claimed_value_inr,
                verdict           = RefundVerdict.APPROVE,
                audit_reason      = (
                    f"Packer {packer_id} has Type-B hesitation flag — "
                    "possible packer interference."
                ),
                was_injected_fraud = claim.injected_fraud,
            )

        # Rule 4 — packer is HIGH or CRITICAL risk overall
        if profile is not None and profile.risk_level in (RiskLevel.HIGH, RiskLevel.CRITICAL):
            return AuditResult(
                refund_id         = claim.refund_id,
                order_id          = claim.order_id,
                item_id           = claim.item_id,
                claimed_value_inr = claim.claimed_value_inr,
                verdict           = RefundVerdict.APPROVE,
                audit_reason      = (
                    f"Packer {packer_id} is {profile.risk_level.value} risk "
                    f"(score={anom_score}) — refund approved pending investigation."
                ),
                was_injected_fraud = claim.injected_fraud,
            )

        # Rule 5 — clean packer, reject the claim
        return AuditResult(
            refund_id         = claim.refund_id,
            order_id          = claim.order_id,
            item_id           = claim.item_id,
            claimed_value_inr = claim.claimed_value_inr,
            verdict           = RefundVerdict.REJECT,
            audit_reason      = (
                f"Packer {packer_id} scan is clean (no flags, "
                f"score={anom_score}). High probability of customer fraud."
            ),
            was_injected_fraud = claim.injected_fraud,
        )

    @property
    def results(self) -> list[AuditResult]:
        return self._results