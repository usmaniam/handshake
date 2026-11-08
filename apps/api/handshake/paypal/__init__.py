"""PayPal adapter: OAuth, Payouts, webhook verification, status mapping, and a fake rail."""
from __future__ import annotations

import json
import time
import uuid
from typing import Any, Protocol

import httpx

from ..config import Settings, settings


class PayPalError(Exception):
    """Permanent failure (4xx). Do not retry blindly."""
    def __init__(self, msg: str, status: int = 0, body: Any = None):
        super().__init__(msg)
        self.status, self.body = status, body


class PayPalTransient(Exception):
    """Timeout / 5xx. Safe to retry with the same PayPal-Request-Id."""


# PayPal item/batch status -> ledger status
LEDGER_FROM_PAYPAL = {
    "NEW": "RELEASING", "PENDING": "RELEASING", "PROCESSING": "RELEASING",
    "SUCCESS": "PAID", "SUCCEEDED": "PAID",
    "UNCLAIMED": "PAYOUT_UNCLAIMED",
    "ONHOLD": "PAYOUT_HELD", "HELD": "PAYOUT_HELD", "BLOCKED": "PAYOUT_HELD",
    "DENIED": "PAYOUT_FAILED", "FAILED": "PAYOUT_FAILED",
    "RETURNED": "PAYOUT_RETURNED", "REFUNDED": "PAYOUT_RETURNED",
    "REVERSED": "PAYOUT_RETURNED", "CANCELED": "PAYOUT_RETURNED",
}
EVENT_STATUS = {
    "PAYMENT.PAYOUTS-ITEM.SUCCEEDED": "SUCCESS", "PAYMENT.PAYOUTS-ITEM.BLOCKED": "BLOCKED",
    "PAYMENT.PAYOUTS-ITEM.CANCELED": "CANCELED", "PAYMENT.PAYOUTS-ITEM.FAILED": "FAILED",
    "PAYMENT.PAYOUTS-ITEM.HELD": "ONHOLD", "PAYMENT.PAYOUTS-ITEM.REFUNDED": "REFUNDED",
    "PAYMENT.PAYOUTS-ITEM.RETURNED": "RETURNED", "PAYMENT.PAYOUTS-ITEM.UNCLAIMED": "UNCLAIMED",
    "PAYMENT.PAYOUTSBATCH.DENIED": "DENIED",
}


class Rail(Protocol):
    def send_payout(self, *, sender_batch_id: str, receiver: str, recipient_type: str, amount: str,
                    currency: str, note: str, sender_item_id: str) -> dict: ...
    def get_payout(self, batch_id: str) -> dict: ...
    def verify_webhook(self, headers: Any, raw_body: bytes) -> bool: ...


_TOKENS: dict[str, tuple[str, float]] = {}


class PayPalClient:
    def __init__(self, s: Settings | None = None, http: httpx.Client | None = None):
        self.s = s or settings()
        self.http = http or httpx.Client(timeout=20)

    def _token(self, force: bool = False) -> str:
        key = self.s.paypal_client_id
        tok = _TOKENS.get(key)
        if tok and not force and tok[1] > time.time() + 60:
            return tok[0]
        r = self.http.post(f"{self.s.paypal_base_url}/v1/oauth2/token", data={"grant_type": "client_credentials"},
                           auth=(self.s.paypal_client_id, self.s.paypal_secret))
        if r.status_code != 200:
            raise PayPalError("oauth failed", r.status_code, r.text[:300])
        j = r.json()
        _TOKENS[key] = (j["access_token"], time.time() + int(j.get("expires_in", 3600)))
        return j["access_token"]

    def _req(self, method: str, path: str, *, headers: dict | None = None, **kw) -> dict:
        for attempt in (0, 1):
            h = {"Authorization": f"Bearer {self._token(force=attempt == 1)}", "Content-Type": "application/json",
                 **(headers or {})}
            try:
                r = self.http.request(method, self.s.paypal_base_url + path, headers=h, **kw)
            except httpx.TransportError as e:
                raise PayPalTransient(str(e)) from e
            if r.status_code == 401 and attempt == 0:
                continue  # refresh token once, retry
            if r.status_code >= 500 or r.status_code == 429:
                raise PayPalTransient(f"{r.status_code} {r.text[:200]}")
            if r.status_code >= 400:
                raise PayPalError(f"paypal {r.status_code}", r.status_code, r.text[:500])
            return r.json() if r.content else {}
        raise PayPalError("unauthorized")

    def send_payout(self, *, sender_batch_id, receiver, recipient_type, amount, currency, note, sender_item_id) -> dict:
        body = {"sender_batch_header": {"sender_batch_id": sender_batch_id[:256],
                                        "email_subject": "Payment released by Handshake",
                                        "email_message": "Released after verified delivery."},
                "items": [{"recipient_type": recipient_type, "receiver": receiver,
                           "amount": {"value": amount, "currency": currency},
                           "note": note[:4000], "sender_item_id": sender_item_id[:63]}]}
        j = self._req("POST", "/v1/payments/payouts", json=body, headers={"PayPal-Request-Id": sender_batch_id[:108]})
        bh = j["batch_header"]
        return {"batch_id": bh["payout_batch_id"], "batch_status": bh["batch_status"], "raw": j}

    def get_payout(self, batch_id: str) -> dict:
        j = self._req("GET", f"/v1/payments/payouts/{batch_id}")
        items = [{"item_id": i.get("payout_item_id"), "status": i.get("transaction_status"),
                  "sender_item_id": (i.get("payout_item") or {}).get("sender_item_id"),
                  "errors": i.get("errors")} for i in j.get("items", [])]
        return {"batch_status": j["batch_header"]["batch_status"], "items": items}

    def verify_webhook(self, headers: Any, raw_body: bytes) -> bool:
        """Needs the exact raw bytes; never re-serialize."""
        if not self.s.paypal_webhook_id:
            return False
        h = lambda k: headers.get(k)  # noqa: E731  (starlette headers are case-insensitive)
        try:
            body = {"auth_algo": h("paypal-auth-algo"), "cert_url": h("paypal-cert-url"),
                    "transmission_id": h("paypal-transmission-id"), "transmission_sig": h("paypal-transmission-sig"),
                    "transmission_time": h("paypal-transmission-time"), "webhook_id": self.s.paypal_webhook_id,
                    "webhook_event": json.loads(raw_body)}
            return self._req("POST", "/v1/notifications/verify-webhook-signature", json=body).get(
                "verification_status") == "SUCCESS"
        except (PayPalError, PayPalTransient, ValueError):
            return False


class FakeRail:
    """In-memory rail for tests and the benchmark. auto_settle=True mimics an instant SUCCESS."""
    def __init__(self, auto_settle: bool = True, fail_with: Exception | None = None, webhook_ok: bool = True):
        self.auto_settle, self.fail_with, self.webhook_ok = auto_settle, fail_with, webhook_ok
        self.sent: list[dict] = []
        self.batches: dict[str, dict] = {}
        self.forced_status: str | None = None

    def send_payout(self, **kw) -> dict:
        if self.fail_with:
            raise self.fail_with
        prior = next((b for b in self.sent if b["sender_batch_id"] == kw["sender_batch_id"]), None)
        if prior:  # PayPal-Request-Id idempotency
            return {"batch_id": prior["batch_id"], "batch_status": "PENDING", "raw": {}}
        bid = "FAKEBATCH" + uuid.uuid4().hex[:10].upper()
        self.sent.append({**kw, "batch_id": bid})
        self.batches[bid] = {"item_id": "FAKEITEM" + uuid.uuid4().hex[:8].upper(), "sender_item_id": kw["sender_item_id"]}
        return {"batch_id": bid, "batch_status": "SUCCESS" if self.auto_settle else "PENDING", "raw": {}}

    def get_payout(self, batch_id: str) -> dict:
        b = self.batches[batch_id]
        st = self.forced_status or ("SUCCESS" if self.auto_settle else "PENDING")
        return {"batch_status": st, "items": [{"item_id": b["item_id"], "status": st,
                                               "sender_item_id": b["sender_item_id"], "errors": None}]}

    def verify_webhook(self, headers: Any, raw_body: bytes) -> bool:
        return self.webhook_ok

    @property
    def total_sent(self) -> float:
        return sum(float(x["amount"]) for x in self.sent)


_FAKE: FakeRail | None = None


def get_rail() -> Rail:
    """PAYOUT_RAIL=fake gives a process-wide FakeRail that settles instantly (local demos, no PayPal needed)."""
    global _FAKE
    if settings().payout_rail == "paypal":
        return PayPalClient()
    if _FAKE is None:
        _FAKE = FakeRail(auto_settle=True)
    return _FAKE
