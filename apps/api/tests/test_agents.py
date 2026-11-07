from datetime import date

import pytest

from handshake import agents
from handshake.flags import scan


class Fake:
    def __init__(self, out=None, boom=False):
        self.out, self.boom = out, boom

    def json(self, system, user, schema):
        if self.boom:
            raise RuntimeError("quota")
        return self.out


def test_phrase_falls_back_without_llm_or_on_failure():
    for mode in agents.MODES:
        assert agents.phrase(None, mode) == agents.CANNED[mode]
        assert agents.phrase(Fake(boom=True), mode) == agents.CANNED[mode]


def test_phrase_uses_llm_text_and_trims():
    assert agents.phrase(Fake(agents.Phrase(text="  Ship it.  ")), "honest") == "Ship it."


def test_canned_red_team_messages_trip_the_scanner_and_honest_does_not():
    assert "deposit_pressure" in scan(agents.CANNED["hostile_deposit"])
    assert "foreign_payee" in scan(agents.CANNED["hostile_deposit"], "vendor@x.com")
    assert "prompt_injection" in scan(agents.CANNED["injection"])
    assert scan(agents.CANNED["honest"]) == []


def test_buyer_terms_validates_model_output():
    plan = agents.BuyerPlan(item="mailer boxes", quantity=200, max_unit_price=0.45, deliverable_type="physical_goods", sku="mailer-12x9x3")
    t = agents.buyer_terms(Fake(plan), "200 mailer boxes under 45 cents", today=date(2026, 11, 10))
    assert t.quantity == 200 and t.spec == {"sku": "mailer-12x9x3"} and t.deadline == date(2026, 11, 20)


def test_buyer_terms_rejects_unusable_plans_and_missing_llm():
    with pytest.raises(ValueError):
        agents.buyer_terms(None, "anything")
    with pytest.raises(ValueError):
        agents.buyer_terms(Fake(boom=True), "anything")
