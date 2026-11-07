from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (JSON, Boolean, Date, DateTime, ForeignKey, Integer, Numeric, String,
                        Text, UniqueConstraint)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from ..util import utcnow


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def _pk(prefix: str):
    return mapped_column(String(40), primary_key=True, default=lambda: new_id(prefix))


class Base(DeclarativeBase):
    pass


class Owner(Base):
    __tablename__ = "owners"
    id: Mapped[str] = _pk("own")
    name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(320))
    budget_total: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("600"))
    approval_threshold: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("100"))
    settings: Mapped[dict] = mapped_column(JSON, default=dict)


class VendorProfile(Base):
    __tablename__ = "vendor_profiles"
    id: Mapped[str] = _pk("ven")
    owner_id: Mapped[str] = mapped_column(ForeignKey("owners.id"))
    name: Mapped[str] = mapped_column(String(120))
    payee_type: Mapped[str] = mapped_column(String(20), default="EMAIL")  # EMAIL | PAYPAL_ID
    payee_value: Mapped[str] = mapped_column(String(320))
    verified_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    category: Mapped[str] = mapped_column(String(60))
    trust_level: Mapped[str] = mapped_column(String(20), default="known")  # new|known|trusted


class Agent(Base):
    __tablename__ = "agents"
    id: Mapped[str] = _pk("agt")
    owner_id: Mapped[str] = mapped_column(ForeignKey("owners.id"))
    name: Mapped[str] = mapped_column(String(120))
    role: Mapped[str] = mapped_column(String(10))  # buyer | seller
    api_key_hash: Mapped[str] = mapped_column(String(64), unique=True)
    status: Mapped[str] = mapped_column(String(20), default="active")
    vendor_profile_id: Mapped[str | None] = mapped_column(ForeignKey("vendor_profiles.id"), nullable=True)
    limits: Mapped[dict] = mapped_column(JSON, default=dict)


class Deal(Base):
    __tablename__ = "deals"
    id: Mapped[str] = _pk("deal")
    owner_id: Mapped[str] = mapped_column(ForeignKey("owners.id"))
    vendor_profile_id: Mapped[str] = mapped_column(ForeignKey("vendor_profiles.id"))
    buyer_agent_id: Mapped[str] = mapped_column(ForeignKey("agents.id"))
    state: Mapped[str] = mapped_column(String(30), default="DRAFT")
    current_terms_version: Mapped[int] = mapped_column(Integer, default=0)
    accepted_terms_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reserved_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0"))
    paid_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0"))
    deadline: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class DealTerms(Base):
    __tablename__ = "deal_terms"
    __table_args__ = (UniqueConstraint("deal_id", "version"),)
    id: Mapped[str] = _pk("trm")
    deal_id: Mapped[str] = mapped_column(ForeignKey("deals.id"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    item: Mapped[str] = mapped_column(String(200))
    quantity: Mapped[int] = mapped_column(Integer)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(12, 4))
    total: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    payee_ref: Mapped[str] = mapped_column(String(320))  # from verified vendor profile, never a message
    payee_hint: Mapped[str | None] = mapped_column(String(320), nullable=True)
    acceptance_criteria: Mapped[list] = mapped_column(JSON, default=list)
    spec: Mapped[dict] = mapped_column(JSON, default=dict)
    deliverable_type: Mapped[str] = mapped_column(String(20))
    deadline: Mapped[date] = mapped_column(Date)
    proposed_by: Mapped[str] = mapped_column(String(40))
    fingerprint: Mapped[str] = mapped_column(String(64))
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class Message(Base):
    __tablename__ = "messages"
    id: Mapped[str] = _pk("msg")
    deal_id: Mapped[str] = mapped_column(ForeignKey("deals.id"), index=True)
    from_agent: Mapped[str] = mapped_column(String(40))
    type: Mapped[str] = mapped_column(String(20))
    content: Mapped[str] = mapped_column(Text, default="")
    terms_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    provenance: Mapped[str] = mapped_column(String(30))
    flagged: Mapped[bool] = mapped_column(Boolean, default=False)
    flags: Mapped[list] = mapped_column(JSON, default=list)
    ts: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Delivery(Base):
    __tablename__ = "deliveries"
    id: Mapped[str] = _pk("dlv")
    deal_id: Mapped[str] = mapped_column(ForeignKey("deals.id"), index=True)
    submitted_by: Mapped[str] = mapped_column(String(40))
    proof_type: Mapped[str] = mapped_column(String(30))
    proof_json: Mapped[dict] = mapped_column(JSON)
    proof_key: Mapped[str] = mapped_column(String(80), index=True)
    consumed: Mapped[bool] = mapped_column(Boolean, default=False)  # proof already used in another deal
    ts: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Verification(Base):
    __tablename__ = "verifications"
    id: Mapped[str] = _pk("ver")
    delivery_id: Mapped[str] = mapped_column(ForeignKey("deliveries.id"), index=True)
    deal_id: Mapped[str] = mapped_column(ForeignKey("deals.id"), index=True)
    deterministic: Mapped[dict] = mapped_column(JSON)
    llm: Mapped[dict] = mapped_column(JSON)
    verdict: Mapped[str] = mapped_column(String(20))
    reasons: Mapped[list] = mapped_column(JSON, default=list)
    late: Mapped[bool] = mapped_column(Boolean, default=False)
    ts: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class PaymentRequest(Base):
    __tablename__ = "payment_requests"
    id: Mapped[str] = _pk("pr")
    owner_id: Mapped[str] = mapped_column(ForeignKey("owners.id"))
    deal_id: Mapped[str | None] = mapped_column(ForeignKey("deals.id"), nullable=True, index=True)
    phase: Mapped[str] = mapped_column(String(10))  # commit | release | direct
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    payee_ref: Mapped[str | None] = mapped_column(String(320), nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(200), unique=True)
    provenance_json: Mapped[dict] = mapped_column(JSON, default=dict)
    ts: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class DecisionRow(Base):
    __tablename__ = "decisions"
    id: Mapped[str] = _pk("dec")
    payment_request_id: Mapped[str] = mapped_column(ForeignKey("payment_requests.id"), unique=True)
    rule_results: Mapped[list] = mapped_column(JSON)
    ai_result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    decision: Mapped[str] = mapped_column(String(20))
    explanation: Mapped[str] = mapped_column(Text)
    ts: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Approval(Base):
    __tablename__ = "approvals"
    id: Mapped[str] = _pk("apr")
    decision_id: Mapped[str] = mapped_column(ForeignKey("decisions.id"))
    payment_request_id: Mapped[str] = mapped_column(ForeignKey("payment_requests.id"))
    deal_id: Mapped[str | None] = mapped_column(ForeignKey("deals.id"), nullable=True)
    kind: Mapped[str] = mapped_column(String(10))  # commit | release | direct
    status: Mapped[str] = mapped_column(String(12), default="pending")  # pending|approved|denied
    decided_by: Mapped[str | None] = mapped_column(String(80), nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    ts: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Payout(Base):
    __tablename__ = "payouts"
    id: Mapped[str] = _pk("pay")
    owner_id: Mapped[str] = mapped_column(ForeignKey("owners.id"), index=True)
    deal_id: Mapped[str | None] = mapped_column(ForeignKey("deals.id"), nullable=True, index=True)
    payment_request_id: Mapped[str] = mapped_column(ForeignKey("payment_requests.id"))
    sender_batch_id: Mapped[str] = mapped_column(String(256), unique=True)
    paypal_batch_id: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    paypal_item_id: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    paypal_status: Mapped[str] = mapped_column(String(30), default="PENDING_SEND")
    status: Mapped[str] = mapped_column(String(30), default="RELEASING")
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    receiver: Mapped[str] = mapped_column(String(320))
    recipient_type: Mapped[str] = mapped_column(String(20), default="EMAIL")
    raw: Mapped[dict] = mapped_column(JSON, default=dict)
    ts: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class WebhookEvent(Base):
    __tablename__ = "webhook_events"
    id: Mapped[str] = _pk("whe")
    paypal_event_id: Mapped[str] = mapped_column(String(80), unique=True)
    event_type: Mapped[str] = mapped_column(String(80))
    verified: Mapped[bool] = mapped_column(Boolean, default=False)
    payload: Mapped[dict] = mapped_column(JSON)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class AuditLog(Base):
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ts: Mapped[str] = mapped_column(String(40))
    actor: Mapped[str] = mapped_column(String(80))
    event: Mapped[str] = mapped_column(String(80))
    ref_type: Mapped[str] = mapped_column(String(30))
    ref_id: Mapped[str] = mapped_column(String(60))
    payload: Mapped[dict] = mapped_column(JSON)
    prev_hash: Mapped[str] = mapped_column(String(64))
    hash: Mapped[str] = mapped_column(String(64))


class Shipment(Base):
    """Mock carrier."""
    __tablename__ = "shipments"
    tracking: Mapped[str] = mapped_column(String(60), primary_key=True)
    carrier: Mapped[str] = mapped_column(String(40), default="MockShip")
    status: Mapped[str] = mapped_column(String(20), default="IN_TRANSIT")
    items: Mapped[list] = mapped_column(JSON, default=list)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    destination: Mapped[str | None] = mapped_column(String(200), nullable=True)
    registered_by: Mapped[str | None] = mapped_column(String(40), nullable=True)


class IdemRecord(Base):
    __tablename__ = "idempotency_records"
    __table_args__ = (UniqueConstraint("scope", "key"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    scope: Mapped[str] = mapped_column(String(120))
    key: Mapped[str] = mapped_column(String(128))
    response: Mapped[dict] = mapped_column(JSON)


class BenchRun(Base):
    __tablename__ = "bench_runs"
    id: Mapped[str] = _pk("bch")
    ts: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    results: Mapped[dict] = mapped_column(JSON)
