from __future__ import annotations

from datetime import date, datetime

import pytest

from handshake import db, service
from handshake.db.models import Agent, Base, Shipment
from handshake.paypal import FakeRail
from handshake.schemas import DeliveryIn, TermsIn
from handshake.seed import seed

NOW = datetime(2026, 11, 10, 12, 0)
DEADLINE = date(2026, 11, 20)


class H:
    """Test harness around the service layer."""
    def __init__(self):
        self.engine = db.configure("sqlite://")
        Base.metadata.drop_all(self.engine)
        Base.metadata.create_all(self.engine)
        self.s = db.new_session()
        self.info = seed(self.s, deterministic_keys=True)
        self.rail = FakeRail(auto_settle=True)
        self.n = 0
        self.buyer = self.agent("buyer")

    def agent(self, k):
        from handshake.seed import hash_key
        from sqlalchemy import select
        return self.s.scalar(select(Agent).where(Agent.api_key_hash == hash_key(self.info["keys"][k])))

    def key(self):
        self.n += 1
        return f"key-{self.n:04d}-xxxx"

    def physical(self, qty=200, price="0.42", vendor="acme", sku="mailer-12x9x3", **kw):
        return TermsIn(item="mailer boxes", quantity=qty, unit_price=price, deadline=kw.get("deadline", DEADLINE),
                       deliverable_type="physical_goods", acceptance_criteria=[f"{qty} units"],
                       spec={"sku": sku}, payee_hint=kw.get("payee_hint"))

    def agree(self, terms=None, vendor="acme", now=NOW):
        terms = terms or self.physical()
        deal = service.create_deal(self.s, self.buyer, self.info["vendors"][vendor], terms, "need boxes", now)
        seller = self.agent(vendor)
        service.post_message(self.s, seller, deal, "accept", None, "deal", now)
        self.s.commit()
        return deal, seller

    def commit(self, deal, now=NOW):
        r = service.commit(self.s, self.buyer, deal, self.key(), now)
        self.s.commit()
        return r

    def ship(self, tracking="TRK-1", qty=200, sku="mailer-12x9x3", status="DELIVERED", at=datetime(2026, 11, 15)):
        self.s.merge(Shipment(tracking=tracking, status=status, items=[{"sku": sku, "qty": qty}], delivered_at=at))
        self.s.commit()

    def deliver(self, deal, seller, tracking="TRK-1", now=NOW):
        r = service.submit_delivery(self.s, seller, deal, DeliveryIn(proof_type="carrier_tracking", tracking_number=tracking), now)
        self.s.commit()
        return r

    def release(self, deal, key=None, amount=None, payee=None, now=NOW):
        r = service.release(self.s, self.buyer, deal, key or self.key(), amount, payee, self.rail, now)
        self.s.commit()
        return r

    def happy(self, **kw):
        deal, seller = self.agree(**kw)
        assert self.commit(deal)["decision"] == "ALLOW"
        self.ship()
        assert self.deliver(deal, seller)["verdict"] == "PASS"
        return deal, seller


@pytest.fixture
def h():
    return H()
