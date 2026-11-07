# 3-minute demo runbook

Setup: `make reset-dev`, API and console running, `make demo` run once so the console has data (use the real PayPal rail
for the paid beat if the smoke test passed; otherwise say clearly that payouts are simulated).

| Time | Show | Say |
|---|---|---|
| 0:00 | Today screen | "Maya runs a small shop. Her agents buy for her, but they never hold her PayPal credentials." |
| 0:20 | Deal: honest supply order (Paid) | "Agreed terms, budget reserved, delivery verified against the carrier, then a PayPal payout. Every step is on the timeline." |
| 0:55 | Deal: wrong item delivered | "The seller shipped the wrong item. The check fails, no money moves, and Maya decides." |
| 1:20 | Deal: hostile deposit (Blocked) | "After agreeing, the seller pushed a deposit to a different account. Handshake refused to commit money." |
| 1:45 | Deal: terms drift | "The seller raised the price after accept. Handshake ignores it; Pay anyway is disabled for this one." |
| 2:10 | Approvals: $210 order | "Over Maya's $100 limit, so she approves from her phone." Approve. |
| 2:30 | Ledger > open a row | "Every decision explains itself, rule by rule." |
| 2:45 | Red-team lab > Run | "14 scenarios: a naive agent loses $1,052, Handshake $150. That $150 is ten small payments to a verified vendor; we cap it, we can't prevent it." |

Be upfront about: sandbox only; conditional release, not escrow; the Gemini checks only make results stricter.
