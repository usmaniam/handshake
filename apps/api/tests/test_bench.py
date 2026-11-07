from decimal import Decimal as D

from handshake.bench import run_all


def test_benchmark_results_are_stable_and_honest():
    r = run_all()
    by = {x["id"]: x for x in r["scenarios"]}
    for sid in ["A1", "A2", "A3", "A4", "A5", "A6", "A7", "A8", "A10", "A11"]:
        assert D(by[sid]["guarded"]["mispaid"]) == 0, sid
    # velocity caps the loss at 5 x $30; it does not prevent it
    assert D(by["A9"]["guarded"]["mispaid"]) == D(150)
    assert r["summary"]["guarded"]["false_blocks"] == 0
    assert r["summary"]["guarded"]["legit_completed"] == "3/3"
    assert D(r["summary"]["unguarded"]["mispaid"]) > D(r["summary"]["guarded"]["mispaid"])
