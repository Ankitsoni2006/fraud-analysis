"""
data_ingestion/json_loader.py
=============================
Parses JSON payloads, validates schemas with Pydantic, and returns domain models.
"""

from __future__ import annotations

import json
from typing import List, Dict, Any, Union
from pydantic import ValidationError as PydanticValidationError

from exceptions import ValidationError
from logging_config import get_logger
from models import ScanEvent, RefundClaim
from data_ingestion.schema_validator import ScanEventSchema, OrderSchema, RefundClaimSchema

log = get_logger(__name__)


def _parse_json_data(file_source: Union[str, bytes]) -> Any:
    """Helper to parse JSON string or bytes."""
    try:
        return json.loads(file_source)
    except Exception as exc:
        log.error("Failed to parse JSON string/bytes", error=str(exc))
        raise ValidationError(f"Invalid JSON format: {exc}") from exc


def load_scan_events_from_json(data: Union[str, bytes, List[Dict[str, Any]]]) -> List[ScanEvent]:
    """
    Validates a list of JSON dictionaries against ScanEventSchema.
    """
    raw_list = _parse_json_data(data) if isinstance(data, (str, bytes)) else data
    if not isinstance(raw_list, list):
        raise ValidationError("Expected a list of scan events in JSON.")

    events: List[ScanEvent] = []
    errors = []

    for idx, item in enumerate(raw_list):
        try:
            validated = ScanEventSchema(**item)
            events.append(ScanEvent(
                log_id=validated.log_id or ScanEvent.new_id(),
                order_id=validated.order_id,
                packer_id=validated.packer_id,
                item_id=validated.item_id,
                shelf_aisle=validated.shelf_aisle,
                shelf_num=validated.shelf_num,
                timestamp=validated.timestamp,
                store_id=validated.store_id,
            ))
        except PydanticValidationError as exc:
            errors.append(f"Index {idx} validation error: {exc}")

    if errors:
        log.error("JSON Scan Events validation failed", error_count=len(errors))
        raise ValidationError(f"Scan events JSON ingestion failed: {'; '.join(errors[:5])}")

    return events


def load_orders_from_json(data: Union[str, bytes, List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    """
    Validates a list of JSON dictionaries against OrderSchema.
    """
    raw_list = _parse_json_data(data) if isinstance(data, (str, bytes)) else data
    if not isinstance(raw_list, list):
        raise ValidationError("Expected a list of orders in JSON.")

    orders: List[Dict[str, Any]] = []
    errors = []

    for idx, item in enumerate(raw_list):
        try:
            validated = OrderSchema(**item)
            orders.append(validated.model_dump())
        except PydanticValidationError as exc:
            errors.append(f"Index {idx} validation error: {exc}")

    if errors:
        log.error("JSON Orders validation failed", error_count=len(errors))
        raise ValidationError(f"Orders JSON ingestion failed: {'; '.join(errors[:5])}")

    return orders


def load_refund_claims_from_json(data: Union[str, bytes, List[Dict[str, Any]]]) -> List[RefundClaim]:
    """
    Validates a list of JSON dictionaries against RefundClaimSchema.
    """
    raw_list = _parse_json_data(data) if isinstance(data, (str, bytes)) else data
    if not isinstance(raw_list, list):
        raise ValidationError("Expected a list of refund claims in JSON.")

    claims: List[RefundClaim] = []
    errors = []

    for idx, item in enumerate(raw_list):
        try:
            validated = RefundClaimSchema(**item)
            claims.append(RefundClaim(
                refund_id=validated.refund_id,
                order_id=validated.order_id,
                customer_id=validated.customer_id,
                item_id=validated.item_id,
                claimed_value_inr=validated.claimed_value_inr,
                claim_reason=validated.claim_reason,
                request_ts=validated.request_ts,
                injected_fraud=False,
            ))
        except PydanticValidationError as exc:
            errors.append(f"Index {idx} validation error: {exc}")

    if errors:
        log.error("JSON Refund Claims validation failed", error_count=len(errors))
        raise ValidationError(f"Refund claims JSON ingestion failed: {'; '.join(errors[:5])}")

    return claims


def load_combined_payload_from_json(data: Union[str, bytes]) -> Dict[str, Any]:
    """
    Parses a single combined JSON dictionary containing 'scan_events', 'orders', and 'refund_claims'.
    """
    parsed = _parse_json_data(data)
    if not isinstance(parsed, dict):
        raise ValidationError("Expected a dictionary containing combined lists.")

    result = {}
    if "scan_events" in parsed:
        result["scan_events"] = load_scan_events_from_json(parsed["scan_events"])
    if "orders" in parsed:
        result["orders"] = load_orders_from_json(parsed["orders"])
    if "refund_claims" in parsed:
        result["refund_claims"] = load_refund_claims_from_json(parsed["refund_claims"])

    return result
