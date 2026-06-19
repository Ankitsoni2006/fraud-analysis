"""
ivc/metrics.py
==============
Detection quality metrics.

Computes precision and recall for Type-A and Type-B detectors by
comparing flagged log_ids against the simulator's ground-truth labels.

These metrics are:
  - Available in simulation/test environments (where ground truth exists).
  - Omitted in production (injected_log_ids will be an empty dict).
"""

from __future__ import annotations

from dataclasses import dataclass

from logging_config import get_logger
from models import HesitationViolation, SpeedViolation

log = get_logger(__name__)


@dataclass
class DetectionMetrics:
    """Precision / recall for one detector type."""
    true_positives:  int   = 0
    false_positives: int   = 0
    false_negatives: int   = 0
    precision:       float = 0.0
    recall:          float = 0.0
    f1:              float = 0.0

    def compute(self) -> None:
        tp = self.true_positives
        fp = self.false_positives
        fn = self.false_negatives
        self.precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        self.recall    = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        denom = self.precision + self.recall
        self.f1 = 2 * self.precision * self.recall / denom if denom > 0 else 0.0


def evaluate(
    speed_violations:      list[SpeedViolation],
    hesitation_violations: list[HesitationViolation],
    injected_log_ids:      dict[str, list[str]],
) -> dict[str, DetectionMetrics]:
    """
    Returns metrics keyed by "type_a" and "type_b".

    If injected_log_ids is empty (production mode), returns zero-filled
    metrics without raising an error.
    """
    results: dict[str, DetectionMetrics] = {}

    # Type A ─────────────────────────────────────────────────────────────────
    gt_a  = set(injected_log_ids.get("A", []))
    det_a = {v.log_id for v in speed_violations}

    m_a = DetectionMetrics(
        true_positives  = len(gt_a & det_a),
        false_positives = len(det_a - gt_a),
        false_negatives = len(gt_a - det_a),
    )
    m_a.compute()
    results["type_a"] = m_a

    # Type B ─────────────────────────────────────────────────────────────────
    gt_b  = set(injected_log_ids.get("B", []))
    det_b = {v.log_id for v in hesitation_violations}

    m_b = DetectionMetrics(
        true_positives  = len(gt_b & det_b),
        false_positives = len(det_b - gt_b),
        false_negatives = len(gt_b - det_b),
    )
    m_b.compute()
    results["type_b"] = m_b

    log.info(
        "Detection quality metrics computed",
        type_a_precision=round(m_a.precision, 3),
        type_a_recall=round(m_a.recall, 3),
        type_a_f1=round(m_a.f1, 3),
        type_b_precision=round(m_b.precision, 3),
        type_b_recall=round(m_b.recall, 3),
        type_b_f1=round(m_b.f1, 3),
    )
    return results
