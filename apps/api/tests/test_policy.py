from decimal import Decimal as D

import pytest

from handshake.policy import ALLOW, APPROVAL, BLOCK, HOLD, Ctx, apply_judge, evaluate


def base(**kw):
    d = dict(phase="release", amount=D("84"), vendor_verified=True, vendor_category="packaging", has_deal=True,
             terms_amount=D("84"), terms_payee="a@x.com", profile_payee="a@x.com", verdict="PASS")
    d.update(kw)
    return Ctx(**d)


def rules(r):
    return {x.rule: x.outcome for x in r.results}


def test_clean_release_allowed():
    assert evaluate(base()).decision == ALLOW


@pytest.mark.parametrize("kw,rule,decision", [
    (dict(amount=D("300"), terms_amount=D("300")), "per_transaction_cap", BLOCK),
    (dict(vendor_verified=False), "vendor_allowlist", BLOCK),
    (dict(vendor_category="gambling"), "category", BLOCK),
    (dict(recent_payouts=5), "velocity", BLOCK),
    (dict(amount=D("150"), terms_amount=D("150")), "approval_threshold", APPROVAL),
    (dict(terms_payee="evil@x.com"), "payee_change", BLOCK),
    (dict(terms_drift=True), "terms_drift", BLOCK),
    (dict(amount=D("90")), "deal_match", BLOCK),
    (dict(claimed_payee="evil@x.com"), "deal_match", BLOCK),
    (dict(verdict="FAIL"), "delivery_required", HOLD),
    (dict(verdict=None), "delivery_required", HOLD),
    (dict(proof_consumed=True), "proof_consumed", BLOCK),
    (dict(late=True), "deadline", APPROVAL),
    (dict(already_paid=True), "duplicate", BLOCK),
])
def test_rule_triggers(kw, rule, decision):
    r = evaluate(base(**kw))
    assert r.decision == decision and rules(r)[rule] == decision


def test_commit_budget_window_and_new_payee_and_deposit():
    c = dict(phase="commit", committed=D("560"), amount=D("84"), terms_amount=D("84"))
    assert evaluate(base(**c)).decision == BLOCK
    assert evaluate(base(phase="commit", vendor_trust="new")).decision == APPROVAL
    assert evaluate(base(phase="commit", deposit_pressure=True)).decision == APPROVAL
    assert evaluate(base(phase="commit", deposit_pressure=True, foreign_payee=True)).decision == BLOCK


def test_precedence_block_beats_hold_beats_approval():
    r = evaluate(base(verdict="FAIL", amount=D("150"), terms_amount=D("150")))
    assert r.decision == HOLD
    assert evaluate(base(verdict="FAIL", terms_drift=True)).decision == BLOCK


def test_provenance_escalates_one_level_and_injection_blocks():
    assert evaluate(base(source="vendor_email")).decision == APPROVAL
    assert evaluate(base(source="vendor_email", amount=D("150"), terms_amount=D("150"))).decision == BLOCK
    assert evaluate(base(injection_flagged=True)).decision == BLOCK


def test_owner_approval_only_satisfies_approval_rules():
    assert evaluate(base(amount=D("150"), terms_amount=D("150"), owner_approved=True)).decision == ALLOW
    assert evaluate(base(terms_drift=True, owner_approved=True)).decision == BLOCK
    assert evaluate(base(verdict="FAIL", owner_approved=True)).decision == HOLD
    assert evaluate(base(verdict="FAIL", owner_approved=True, owner_override_delivery=True)).decision == ALLOW


def test_judge_only_escalates_allow_to_approval():
    assert apply_judge(ALLOW, "high") == APPROVAL
    assert apply_judge(ALLOW, "low") == ALLOW
    assert apply_judge(BLOCK, "low") == BLOCK and apply_judge(HOLD, "low") == HOLD
    assert apply_judge(APPROVAL, "high") == APPROVAL
