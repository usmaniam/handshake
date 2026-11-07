"""Mock carrier. Writes need the admin token: the scenario runner / console plays the carrier,
so a seller agent can never self-report delivery. Stands in for a real carrier API."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..db import get_session
from ..db.models import Owner, Shipment
from ..schemas import ShipmentIn
from ..service import DomainError
from .deps import owner_auth

router = APIRouter(tags=["mock carrier"])


@router.post("/mock-carrier")
def register(body: ShipmentIn, o: Owner = Depends(owner_auth), s: Session = Depends(get_session)):
    s.merge(Shipment(tracking=body.tracking.strip().upper(), carrier=body.carrier, status=body.status, items=body.items,
                     delivered_at=datetime.fromisoformat(body.delivered_at) if body.delivered_at else None,
                     destination=body.destination, registered_by="carrier"))
    s.commit()
    return {"ok": True}


@router.get("/mock-carrier/{tracking}")
def lookup(tracking: str, s: Session = Depends(get_session)):
    sh = s.get(Shipment, tracking.strip().upper())
    if not sh:
        raise DomainError("tracking number not found", 404)
    return {"tracking": sh.tracking, "carrier": sh.carrier, "status": sh.status, "items": sh.items,
            "delivered_at": sh.delivered_at.isoformat() if sh.delivered_at else None, "destination": sh.destination}
