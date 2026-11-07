# Threat model (short form)

**In scope:** hostile/dishonest counterparty agents; prompt injection via messages, vendor emails and deliverables;
terms drift; payee swap; fake or replayed delivery proof; structuring; duplicate releases; runaway agent loops.
**Out of scope:** compromised owner accounts, PayPal-side vulnerabilities, production key management, host
compromise, real-world fraud rings.
**Assumptions:** agents never hold PayPal credentials; payees are verified at vendor setup; the mock carrier stands in
for a real carrier API (writes require the admin token so sellers cannot self-report delivery); sandbox only.

| Threat | Control | Test |
|---|---|---|
| Deposit pressure to a new account | message scan + `deposit_pressure`/`vendor_allowlist` rules | S5, A1 |
| Terms drift / payee swap | immutable accepted terms; `terms_drift`, `deal_match`, `payee_change` | S6, A2, A3, A11 |
| Payee redirected via a request | payee only ever read from the verified vendor profile | `test_payee_in_release_request...` |
| Wrong / partial delivery | deterministic verifier vs carrier data | S3, S10 |
| Replayed proof | proof key unique across deals | S9 |
| Injection in deliverable | untrusted-data prompt, local pattern scan, LLM can only downgrade | S7, A7 |
| Injection in vendor email | provenance rule (blocks flagged, escalates untrusted) | A8 |
| Duplicate release | idempotency keys, compare-and-set into RELEASING, `duplicate` rule | A10 |
| LLM outage / safety block | verifier fails closed to NEEDS_REVIEW | `test_llm_failure_fails_closed` |
| Structuring | velocity + budget window (bounds loss, does not prevent it: see benchmark A9) | A9 |
| Log tampering | hash-chained audit log | `test_audit_chain...` |
