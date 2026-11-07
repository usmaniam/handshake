"""Seed / reset. `python -m handshake.seed --reset [--dev-keys]` wipes and reseeds (owner Maya).
--dev-keys makes agent keys predictable (hs_dev_*): local development only."""
from __future__ import annotations

import hashlib
import os
import secrets
import sys

from sqlalchemy.orm import Session

from . import db
from .db.models import Agent, Base, Owner, VendorProfile
from .util import utcnow

VENDOR_EMAIL = os.environ.get("VENDOR_PAYEE_EMAIL", "vendor-sandbox@example.com")
CONTRACTOR_EMAIL = os.environ.get("CONTRACTOR_PAYEE_EMAIL", "contractor-sandbox@example.com")


def hash_key(k: str) -> str:
    return hashlib.sha256(k.encode()).hexdigest()


def seed(s: Session, deterministic_keys: bool = False) -> dict:
    """Returns ids and PLAINTEXT agent keys (shown once). deterministic_keys is for tests/bench only."""
    def key(name: str) -> str:
        return f"hs_dev_{name}" if deterministic_keys else "hs_" + secrets.token_urlsafe(24)

    now = utcnow()
    owner = Owner(name="Maya", email="maya@example.com", budget_total=600, approval_threshold=100,
                  settings={"per_tx_cap": 250, "velocity_per_hour": 5, "budget_period_days": 7,
                            "allowed_categories": ["packaging", "materials", "creative services"]})
    s.add(owner)
    s.flush()
    vendors = {
        "acme": VendorProfile(owner_id=owner.id, name="Acme Packaging", payee_type="EMAIL", payee_value=VENDOR_EMAIL,
                              verified_at=now, category="packaging", trust_level="known"),
        "pixel": VendorProfile(owner_id=owner.id, name="Pixel Freelance", payee_type="EMAIL", payee_value=CONTRACTOR_EMAIL,
                               verified_at=now, category="creative services", trust_level="known"),
        "newco": VendorProfile(owner_id=owner.id, name="Newco Supplies (new)", payee_type="EMAIL",
                               payee_value="newco-sandbox@example.com", verified_at=now, category="materials",
                               trust_level="new"),
    }
    s.add_all(vendors.values())
    s.flush()
    keys, agents = {}, []
    keys["buyer"] = key("buyer")
    agents.append(Agent(owner_id=owner.id, name="Maya's buyer agent", role="buyer", api_key_hash=hash_key(keys["buyer"])))
    for k, v in vendors.items():
        keys[k] = key(k)
        agents.append(Agent(owner_id=owner.id, name=f"{v.name} seller agent", role="seller",
                            api_key_hash=hash_key(keys[k]), vendor_profile_id=v.id))
    s.add_all(agents)
    s.commit()
    return {"owner_id": owner.id, "vendors": {k: v.id for k, v in vendors.items()}, "keys": keys,
            "agents": {a.name: a.id for a in agents}}


def main() -> None:
    engine = db.get_engine()
    if "--reset" in sys.argv:
        Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    s = db.new_session()
    info = seed(s, deterministic_keys="--dev-keys" in sys.argv)
    print("Seeded owner", info["owner_id"])
    print("Vendors:", info["vendors"])
    print("Agent API keys (shown once):")
    for k, v in info["keys"].items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
