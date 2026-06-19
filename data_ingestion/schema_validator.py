"""
data_ingestion/schema_validator.py
==================================
Pydantic schemas to validate data ingested from CSV/JSON logs.
"""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field

class ScanEventSchema(BaseModel):
    log_id: Optional[str] = Field(default=None, description="Unique event identifier")
    order_id: str = Field(..., description="Assigned order identifier")
    packer_id: str = Field(..., description="Identifier of the packer")
    item_id: str = Field(..., description="Item SKU identifier")
    shelf_aisle: str = Field(..., description="Shelf aisle (e.g. A, B, C)")
    shelf_num: int = Field(..., description="Shelf number (e.g. 1-10)")
    timestamp: datetime = Field(..., description="Timestamp of the event")
    store_id: str = Field(default="STORE_01", description="Assigned dark store")

class OrderSchema(BaseModel):
    order_id: str = Field(..., description="Unique order identifier")
    customer_id: str = Field(..., description="Unique customer identifier")
    store_id: str = Field(..., description="Dark store identifier")
    timestamp: datetime = Field(..., description="Timestamp of the order creation")

class RefundClaimSchema(BaseModel):
    refund_id: str = Field(..., description="Unique refund claim identifier")
    order_id: str = Field(..., description="Associated order identifier")
    customer_id: str = Field(..., description="Associated customer identifier")
    item_id: str = Field(..., description="Associated item SKU identifier")
    claimed_value_inr: float = Field(..., description="Value of the claim in INR")
    claim_reason: str = Field(..., description="Reason for the refund claim")
    request_ts: datetime = Field(..., description="Timestamp of the claim request")
