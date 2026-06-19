"""
data_ingestion/csv_loader.py
============================
Parses CSV files, validates schemas with Pydantic, and yields domain models.
"""

from __future__ import annotations

import io
import pandas as pd
from typing import List, Union, Dict, Any
from pydantic import ValidationError as PydanticValidationError

from exceptions import ValidationError
from logging_config import get_logger
from models import ScanEvent, RefundClaim
from data_ingestion.schema_validator import ScanEventSchema, OrderSchema, RefundClaimSchema

log = get_logger(__name__)


def load_scan_events_from_csv(file_source: Union[str, io.BytesIO, io.StringIO]) -> List[ScanEvent]:
    """
    Parses a CSV of scan events, validates using ScanEventSchema, and returns list[ScanEvent].
    Raises ValidationError if validation fails.
    """
    try:
        df = pd.read_csv(file_source)
    except Exception as exc:
        log.error("Failed to parse CSV source", error=str(exc))
        raise ValidationError(f"Invalid CSV structure: {exc}") from exc

    events: List[ScanEvent] = []
    errors = []
    
    for idx, row in df.iterrows():
        # Convert row to dict, filtering out nan
        row_dict = {k: v for k, v in row.to_dict().items() if pd.notna(v)}
        
        # Standardize timestamp format if string
        if "timestamp" in row_dict:
            try:
                row_dict["timestamp"] = pd.to_datetime(row_dict["timestamp"])
            except Exception as exc:
                errors.append(f"Row {idx}: Invalid timestamp '{row_dict['timestamp']}'")
                continue
        
        try:
            validated = ScanEventSchema(**row_dict)
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
            errors.append(f"Row {idx} validation error: {exc}")
            
    if errors:
        log.error("CSV Scan Events validation failed", error_count=len(errors))
        raise ValidationError(f"Scan events ingestion failed with errors: {'; '.join(errors[:5])}")
        
    return events


def load_orders_from_csv(file_source: Union[str, io.BytesIO, io.StringIO]) -> List[Dict[str, Any]]:
    """
    Parses a CSV of orders, validates using OrderSchema, and returns list of dicts.
    """
    try:
        df = pd.read_csv(file_source)
    except Exception as exc:
        log.error("Failed to parse CSV source", error=str(exc))
        raise ValidationError(f"Invalid CSV structure: {exc}") from exc

    orders: List[Dict[str, Any]] = []
    errors = []

    for idx, row in df.iterrows():
        row_dict = {k: v for k, v in row.to_dict().items() if pd.notna(v)}
        if "timestamp" in row_dict:
            try:
                row_dict["timestamp"] = pd.to_datetime(row_dict["timestamp"])
            except Exception as exc:
                errors.append(f"Row {idx}: Invalid timestamp '{row_dict['timestamp']}'")
                continue

        try:
            validated = OrderSchema(**row_dict)
            orders.append(validated.model_dump())
        except PydanticValidationError as exc:
            errors.append(f"Row {idx} validation error: {exc}")

    if errors:
        log.error("CSV Orders validation failed", error_count=len(errors))
        raise ValidationError(f"Orders ingestion failed with errors: {'; '.join(errors[:5])}")

    return orders


def load_refund_claims_from_csv(file_source: Union[str, io.BytesIO, io.StringIO]) -> List[RefundClaim]:
    """
    Parses a CSV of refund claims, validates using RefundClaimSchema, and returns list[RefundClaim].
    """
    try:
        df = pd.read_csv(file_source)
    except Exception as exc:
        log.error("Failed to parse CSV source", error=str(exc))
        raise ValidationError(f"Invalid CSV structure: {exc}") from exc

    claims: List[RefundClaim] = []
    errors = []

    for idx, row in df.iterrows():
        row_dict = {k: v for k, v in row.to_dict().items() if pd.notna(v)}
        if "request_ts" in row_dict:
            try:
                row_dict["request_ts"] = pd.to_datetime(row_dict["request_ts"])
            except Exception as exc:
                errors.append(f"Row {idx}: Invalid request_ts '{row_dict['request_ts']}'")
                continue

        try:
            validated = RefundClaimSchema(**row_dict)
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
            errors.append(f"Row {idx} validation error: {exc}")

    if errors:
        log.error("CSV Refund Claims validation failed", error_count=len(errors))
        raise ValidationError(f"Refund claims ingestion failed with errors: {'; '.join(errors[:5])}")

    return claims
