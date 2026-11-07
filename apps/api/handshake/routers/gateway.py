from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import service
from ..db import get_session
from ..db.models import Agent, Deal, Message
from ..schemas import DealCreate, DeliveryIn, MessageIn, PaymentRequestIn, ReleaseIn
from .deps import agent_auth, idem_key, idem_run, llm_dep, rail_dep

router = APIRouter(prefix="/v1", tags=["agent gateway"])


def _deal(s: Session, agent: Agent, deal_id: str) -> Deal:
    d = s.get(Deal, deal_id)
    if not d:
        raise service.DomainError("deal not found", 404)
    service._party(agent, d)  # 403 for non-parties
    return d


@router.post("/deals")
def open_deal(body: DealCreate, agent: Agent = Depends(agent_auth), key: str = Depends(idem_key), s: Session = Depends(get_session)):
    def go():
        d = service.create_deal(s, agent, body.vendor_id, body.terms, body.text)
        return service.deal_view(s, d)
    return idem_run(s, f"{agent.id}:open", key, go)


@router.post("/deals/{deal_id}/messages")
def send_message(deal_id: str, body: MessageIn, agent: Agent = Depends(agent_auth), key: str = Depends(idem_key),
                 s: Session = Depends(get_session)):
    d = _deal(s, agent, deal_id)

    def go():
        m = service.post_message(s, agent, d, body.type, body.terms, body.text)
        return {"message_id": m.id, "flags": m.flags, **service.deal_view(s, d)}
    return idem_run(s, f"{agent.id}:msg:{deal_id}", key, go)


@router.get("/deals/{deal_id}")
def get_deal(deal_id: str, agent: Agent = Depends(agent_auth), s: Session = Depends(get_session)):
    d = _deal(s, agent, deal_id)
    out = service.deal_view(s, d)
    out["messages"] = [{"id": m.id, "from": m.from_agent, "type": m.type, "text": m.content, "flags": m.flags}
                       for m in s.scalars(select(Message).where(Message.deal_id == d.id).order_by(Message.ts))]
    return out


@router.post("/deals/{deal_id}/commit")
def commit_deal(deal_id: str, agent: Agent = Depends(agent_auth), key: str = Depends(idem_key),
                s: Session = Depends(get_session), llm=Depends(llm_dep)):
    d = _deal(s, agent, deal_id)
    return idem_run(s, f"{agent.id}:commit:{deal_id}", key, lambda: service.commit(s, agent, d, key, llm=llm))


@router.post("/deals/{deal_id}/delivery")
def submit_delivery(deal_id: str, body: DeliveryIn, agent: Agent = Depends(agent_auth), key: str = Depends(idem_key),
                    s: Session = Depends(get_session), llm=Depends(llm_dep)):
    d = _deal(s, agent, deal_id)
    return idem_run(s, f"{agent.id}:delivery:{deal_id}", key, lambda: service.submit_delivery(s, agent, d, body, llm=llm))


@router.post("/deals/{deal_id}/release")
def release(deal_id: str, body: ReleaseIn | None = None, agent: Agent = Depends(agent_auth), key: str = Depends(idem_key),
            s: Session = Depends(get_session), rail=Depends(rail_dep), llm=Depends(llm_dep)):
    d = _deal(s, agent, deal_id)
    body = body or ReleaseIn()
    return idem_run(s, f"{agent.id}:release:{deal_id}", key,
                    lambda: service.release(s, agent, d, key, body.amount, body.payee, rail, llm=llm))


@router.post("/payment-requests")
def payment_request(body: PaymentRequestIn, agent: Agent = Depends(agent_auth), key: str = Depends(idem_key),
                    s: Session = Depends(get_session), rail=Depends(rail_dep), llm=Depends(llm_dep)):
    return idem_run(s, f"{agent.id}:pay", key, lambda: service.payment_request(s, agent, body, key, rail, llm=llm))
