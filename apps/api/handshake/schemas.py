from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, Field

Source = Literal["owner", "agent_plan", "counterparty_agent", "vendor_email", "web_content"]


class TermsIn(BaseModel):
    item: str = Field(min_length=1, max_length=200)
    quantity: int = Field(gt=0, le=1_000_000)
    unit_price: Decimal = Field(gt=0, max_digits=12, decimal_places=4)
    currency: Literal["USD"] = "USD"
    deadline: date
    deliverable_type: Literal["physical_goods", "digital_work"]
    acceptance_criteria: list[str] = Field(default_factory=list, max_length=20)
    spec: dict[str, Any] = Field(default_factory=dict)
    payee_hint: str | None = Field(default=None, max_length=320)  # ignored for payment; flagged if foreign


class DealCreate(BaseModel):
    vendor_id: str
    terms: TermsIn
    text: str = Field(default="", max_length=4000)


class MessageIn(BaseModel):
    type: Literal["offer", "counter_offer", "accept", "reject", "note"]
    terms: TermsIn | None = None
    text: str = Field(default="", max_length=4000)


class FileIn(BaseModel):
    name: str = Field(max_length=200)
    ref: str | None = None
    size: int = Field(default=0, ge=0)
    content: str | None = Field(default=None, max_length=200_000)
    content_b64: str | None = Field(default=None, max_length=1_500_000)


class DeliveryIn(BaseModel):
    proof_type: Literal["carrier_tracking", "files"]
    tracking_number: str | None = Field(default=None, max_length=60)
    carrier: str | None = None
    claimed_items: list[dict[str, Any]] = Field(default_factory=list, max_length=50)
    files: list[FileIn] = Field(default_factory=list, max_length=50)
    notes: str = Field(default="", max_length=4000)


class ReleaseIn(BaseModel):
    amount: Decimal | None = None
    payee: str | None = None


class PaymentRequestIn(BaseModel):
    amount: Decimal = Field(gt=0)
    currency: Literal["USD"] = "USD"
    payee: str
    deal_id: str | None = None
    memo: str = Field(default="", max_length=1000)
    instruction_source: Source = "agent_plan"
    source_text: str = Field(default="", max_length=4000)


class ApprovalDecision(BaseModel):
    approve: bool
    reason: str = Field(default="", max_length=1000)


class ResolveIn(BaseModel):
    action: Literal["release", "cancel", "retry"]
    reason: str = Field(default="", max_length=1000)


class ShipmentIn(BaseModel):
    tracking: str = Field(max_length=60)
    carrier: str = "MockShip"
    status: Literal["IN_TRANSIT", "DELIVERED", "EXCEPTION"] = "IN_TRANSIT"
    items: list[dict[str, Any]] = Field(default_factory=list)
    delivered_at: str | None = None
    destination: str | None = None
